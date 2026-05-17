from __future__ import annotations

import os
import json
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any

from app.config import settings
from app.ffmpeg_encode import append_pipeline_audio_encode_args, append_pipeline_video_encode_args
from app.services.r2_client import get_r2_client


def _segments_from_plan(plan: dict[str, Any], duration_s: float) -> list[tuple[float, float]]:
    start_s = float(plan.get("recommended_start_s") or 0)
    end_s = float(plan.get("recommended_end_s") or duration_s or 0)
    if duration_s > 0:
        start_s = max(0.0, min(start_s, duration_s))
        end_s = max(start_s, min(end_s, duration_s))

    cuts = []
    for cut in plan.get("internal_cuts") or []:
        if not isinstance(cut, dict):
            continue
        cut_start = max(start_s, min(float(cut.get("start_s") or 0), end_s))
        cut_end = max(cut_start, min(float(cut.get("end_s") or 0), end_s))
        if cut_end - cut_start >= 0.18:
            cuts.append((cut_start, cut_end))
    cuts.sort(key=lambda item: item[0])

    segments: list[tuple[float, float]] = []
    cursor = start_s
    for cut_start, cut_end in cuts:
        if cut_start - cursor >= 0.12:
            segments.append((cursor, cut_start))
        cursor = max(cursor, cut_end)
    if end_s - cursor >= 0.12:
        segments.append((cursor, end_s))

    if not segments and end_s > start_s:
        segments.append((start_s, end_s))
    return [(round(a, 3), round(b, 3)) for a, b in segments if b > a]


def _probe_video_info(path: str) -> tuple[float, float, float]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            "-select_streams",
            "v:0",
            path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout or "{}")
    stream = (data.get("streams") or [{}])[0]
    duration_s = float((data.get("format") or {}).get("duration") or stream.get("duration") or 0)
    rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "30/1"
    try:
        numerator, denominator = rate.split("/", 1)
        fps = float(numerator) / float(denominator)
    except Exception:
        fps = 30.0
    return duration_s, fps, _get_start_pts(path)


def _probe_duration(path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True,
        text=True,
        check=True,
    )
    return float((result.stdout or "0").strip() or 0)


def _get_start_pts(video_path: str) -> float:
    """Match the S09 guard: get first decoded frame PTS from FFmpeg's filter graph."""
    cmd = [
        "ffmpeg",
        "-i",
        video_path,
        "-frames:v",
        "1",
        "-vf",
        "showinfo",
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        match = re.search(r"pts_time:([\d.]+)", result.stderr)
        if match:
            return float(match.group(1))
    except Exception as exc:
        print(f"[Provision/P04] First-frame pts probe failed ({exc}); assuming 0.0")
    return 0.0


def _snap_segments_to_frames(
    segments: list[tuple[float, float]],
    fps: float,
    start_pts_s: float,
    duration_s: float,
) -> list[dict[str, Any]]:
    snapped: list[dict[str, Any]] = []
    for start_s, end_s in segments:
        start_frame = max(0, round((start_s - start_pts_s) * fps))
        end_frame = max(start_frame + 1, round((end_s - start_pts_s) * fps))
        actual_start = max(0.0, start_pts_s + (start_frame / fps))
        actual_end = min(duration_s, start_pts_s + (end_frame / fps))
        if actual_end <= actual_start:
            continue
        snapped.append(
            {
                "start_frame": start_frame,
                "end_frame": end_frame,
                "start_s": round(actual_start, 6),
                "end_s": round(actual_end, 6),
            }
        )
    return snapped


def _build_single_pass_filter(snapped_segments: list[dict[str, Any]]) -> str:
    parts = []
    labels = []
    for index, segment in enumerate(snapped_segments):
        parts.append(
            f"[0:v]trim=start_frame={segment['start_frame']}:end_frame={segment['end_frame']},"
            f"setpts=PTS-STARTPTS[v{index}];"
            f"[0:a]atrim=start={segment['start_s']}:end={segment['end_s']},"
            f"asetpts=PTS-STARTPTS[a{index}]"
        )
        labels.append(f"[v{index}][a{index}]")
    return (
        ";".join(parts)
        + ";"
        + "".join(labels)
        + f"concat=n={len(snapped_segments)}:v=1:a=1[vcat][acat];"
        + "[acat]aresample=async=1:first_pts=0[outa];"
        + "[vcat]setpts=PTS-STARTPTS[outv]"
    )


def _upload_to_r2(local_path: str, key: str) -> str:
    s3 = get_r2_client()
    with open(local_path, "rb") as handle:
        s3.put_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=key,
            Body=handle,
            ContentType="video/mp4",
        )
    return f"{settings.R2_PUBLIC_URL.rstrip('/')}/{key}"


def run(input_path: str, plan: dict[str, Any], variant_id: str) -> dict[str, Any]:
    """Render one provision variant from an edit plan and upload it to R2."""
    duration_s, fps, start_pts_s = _probe_video_info(input_path)
    segments = _segments_from_plan(plan, duration_s)
    if not segments:
        raise RuntimeError("Edit plan produced no renderable segments")
    snapped_segments = _snap_segments_to_frames(segments, fps, start_pts_s, duration_s)
    if not snapped_segments:
        raise RuntimeError("Edit plan produced no frame-snapped renderable segments")

    output_dir = Path(settings.UPLOAD_DIR) / "provision"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(output_dir / f"{variant_id}_render.mp4")
    filter_complex = _build_single_pass_filter(snapped_segments)

    cmd = ["ffmpeg", "-y", "-i", input_path, "-filter_complex", filter_complex, "-map", "[outv]", "-map", "[outa]"]
    # Provision currently runs on Railway CPU, so force libx264 while keeping the
    # shared pipeline CRF/preset/audio contract.
    append_pipeline_video_encode_args(cmd, codec="libx264")
    append_pipeline_audio_encode_args(cmd, has_audio=True)
    cmd.extend(["-movflags", "+faststart", "-avoid_negative_ts", "make_zero", output_path])

    print(
        f"[Provision/P04] Rendering variant={variant_id} segments={segments} "
        f"snapped={snapped_segments} fps={fps:.3f} start_pts={start_pts_s:.4f}"
    )
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Provision single-pass render failed:\n{result.stderr[-3000:]}")
        if not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
            raise RuntimeError("Provision render output is empty")

        output_duration_s = _probe_duration(output_path)
        r2_key = f"provision/{variant_id}_{uuid.uuid4().hex}.mp4"
        output_url = _upload_to_r2(output_path, r2_key)

        return {
            "output_video_url": output_url,
            "duration_s": round(output_duration_s, 3),
            "segments": [{"start_s": start, "end_s": end} for start, end in segments],
            "snapped_segments": snapped_segments,
            "fps": round(fps, 4),
            "start_pts_s": round(start_pts_s, 6),
        }
    finally:
        for path in [output_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
