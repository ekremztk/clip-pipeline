"""
Step 8.5: Landscape upscale gate.

S08 exports short 16:9 clips. Before S09 reframe, this step upgrades only
sub-1080p landscape clips to 1920x1080 so the existing reframe path keeps its
stable 1080p assumptions without upscaling the full source video.
"""
from __future__ import annotations

import json
import os
import subprocess
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from app.config import settings
from app.ffmpeg_encode import append_pipeline_video_encode_args
from app.services.r2_client import get_r2_client
from app.services.supabase_client import get_client


TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080


def _download_temp(url: str) -> str:
    upload_dir = str(settings.UPLOAD_DIR)
    os.makedirs(upload_dir, exist_ok=True)
    temp_path = os.path.join(upload_dir, f"s08_5_dl_{uuid.uuid4().hex}.mp4")
    try:
        response = requests.get(url, stream=True, timeout=120)
        response.raise_for_status()
        with open(temp_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
        return temp_path
    except Exception as exc:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise RuntimeError(f"[S08.5] Download failed for {url}: {exc}") from exc


def _probe_video(path: str) -> dict:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,avg_frame_rate",
        "-of",
        "json",
        path,
    ]
    result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    streams = (json.loads(result.stdout or "{}").get("streams") or [])
    if not streams:
        raise RuntimeError("No video stream found")
    stream = streams[0]
    return {
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "avg_frame_rate": stream.get("avg_frame_rate"),
    }


def _needs_upscale(metadata: dict) -> bool:
    width = int(metadata.get("width") or 0)
    height = int(metadata.get("height") or 0)
    return width < TARGET_WIDTH or height < TARGET_HEIGHT


def _upscale_clip(input_path: str, output_path: str) -> None:
    filter_graph = (
        f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:flags=lanczos,"
        "unsharp=5:5:0.45:3:3:0.25,"
        "setsar=1"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-vf",
        filter_graph,
    ]
    append_pipeline_video_encode_args(cmd)
    cmd.extend([
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        output_path,
    ])
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def _upload_to_r2(local_path: str, job_id: str, clip_index: int) -> str:
    key = f"upscale/{job_id}/clip_{clip_index:02d}_1080p_{uuid.uuid4().hex}.mp4"
    r2 = get_r2_client()
    with open(local_path, "rb") as f:
        r2.put_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=key,
            Body=f,
            ContentType="video/mp4",
        )
    return f"{settings.R2_PUBLIC_URL.rstrip('/')}/{key}"


def _update_clip_landscape_url(clip_id: str | None, url: str) -> None:
    if not clip_id:
        return
    try:
        get_client().table("clips").update({
            "video_landscape_path": url,
            "file_url": url,
        }).eq("id", str(clip_id)).execute()
    except Exception as exc:
        print(f"[S08.5] DB update failed for clip {clip_id}: {exc}")


def _process_clip(index: int, clip: dict, job_id: str) -> dict | None:
    clip_id = clip.get("id")
    landscape_url = clip.get("video_landscape_path") or clip.get("file_url")
    if not landscape_url:
        print(f"[S08.5] Clip {index+1}: no landscape URL. Skipping.")
        return clip

    local_path = None
    output_path = None
    try:
        local_path = _download_temp(landscape_url)
        metadata = _probe_video(local_path)
        width = metadata["width"]
        height = metadata["height"]

        if not _needs_upscale(metadata):
            print(f"[S08.5] Clip {index+1}: {width}x{height}, upscale skipped.")
            return {
                **clip,
                "s08_5_checked": True,
                "s08_5_upscaled": False,
                "s08_5_source_width": width,
                "s08_5_source_height": height,
            }

        output_path = os.path.join(
            str(settings.UPLOAD_DIR),
            f"s08_5_upscaled_{uuid.uuid4().hex}.mp4",
        )
        print(f"[S08.5] Clip {index+1}: {width}x{height} → {TARGET_WIDTH}x{TARGET_HEIGHT} upscale starting.")
        _upscale_clip(local_path, output_path)
        upscaled_meta = _probe_video(output_path)
        if upscaled_meta["width"] != TARGET_WIDTH or upscaled_meta["height"] != TARGET_HEIGHT:
            raise RuntimeError(
                f"Upscale output dimensions invalid: {upscaled_meta['width']}x{upscaled_meta['height']}"
            )

        upscaled_url = _upload_to_r2(output_path, job_id, index)
        _update_clip_landscape_url(clip_id, upscaled_url)
        print(f"[S08.5] Clip {index+1}: upscaled and uploaded: {upscaled_url}")
        return {
            **clip,
            "video_landscape_path": upscaled_url,
            "file_url": upscaled_url,
            "s08_5_checked": True,
            "s08_5_upscaled": True,
            "s08_5_source_width": width,
            "s08_5_source_height": height,
            "s08_5_target_width": TARGET_WIDTH,
            "s08_5_target_height": TARGET_HEIGHT,
        }

    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else str(exc.stderr or "")
        print(f"[S08.5] Clip {index+1}: FFmpeg/ffprobe failed: {stderr[-2000:]}")
        return None
    except Exception as exc:
        print(f"[S08.5] Clip {index+1}: upscale gate failed: {exc}")
        traceback.print_exc()
        return None
    finally:
        for path in [local_path, output_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass


def run(exported_clips: list, job_id: str, channel_id: str) -> list:
    print(f"[S08.5] Starting upscale gate for {len(exported_clips)} clips. Job: {job_id}")
    if not exported_clips:
        return []

    processed: list[tuple[int, dict]] = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(_process_clip, index, clip, job_id): index
            for index, clip in enumerate(exported_clips)
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                result = future.result()
                if result:
                    processed.append((index, result))
            except Exception as exc:
                print(f"[S08.5] Thread error for clip {index+1}: {exc}")

    processed.sort(key=lambda item: item[0])
    clips = [clip for _, clip in processed]
    upscaled = sum(1 for clip in clips if clip.get("s08_5_upscaled"))
    skipped = sum(1 for clip in clips if clip.get("s08_5_checked") and not clip.get("s08_5_upscaled"))
    print(f"[S08.5] Complete. {upscaled} upscaled, {skipped} skipped, {len(clips)}/{len(exported_clips)} passed.")
    return clips
