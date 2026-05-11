"""
Final MP4 packaging for S10 outputs.

The target is the DaVinci Resolve export fingerprint used by the channel:
HEVC Main 10, hvc1, 10-bit 4:2:0, AAC 48 kHz, timecode track, and DaVinci
tool metadata. Outputs that do not match the fingerprint should not be uploaded.
"""
import json
import os
import shutil
import struct
import subprocess
from typing import Any


DAVINCI_ENCODER = "Blackmagic Design DaVinci Resolve"
VIDEO_ENCODER = "H.265 10-bit"
TIMECODE = "01:00:00:00"
BAD_FINGERPRINT_STRINGS = ("Lavf", "Lavc", "ffmpeg", "x264", "x265")


def finalize_davinci_mp4(path: str) -> dict[str, Any]:
    """Patch and validate a final S10 MP4 in-place."""
    try:
        _set_encoding_tool(path)
        _patch_timecode_handler(path)
        return validate_davinci_mp4(path, strict=True)
    except Exception as e:
        print(f"[Finalizer] Error finalizing MP4: {e}")
        raise


def validate_davinci_mp4(path: str, strict: bool = True) -> dict[str, Any]:
    """Return validation details and optionally raise if the fingerprint fails."""
    try:
        probe = _ffprobe(path)
        strings_found = _scan_bad_strings(path)

        fmt = probe.get("format", {})
        streams = probe.get("streams", [])
        video = _first_stream(streams, "video")
        audio = _first_stream(streams, "audio")
        timecode = _first_stream(streams, "data", codec_tag="tmcd")

        checks = {
            "format_encoder": fmt.get("tags", {}).get("encoder") == DAVINCI_ENCODER,
            "major_brand": fmt.get("tags", {}).get("major_brand") == "isom",
            "compatible_brands": fmt.get("tags", {}).get("compatible_brands") == "isomiso2mp41",
            "video_codec": video.get("codec_name") == "hevc",
            "video_profile": video.get("profile") == "Main 10",
            "video_tag": video.get("codec_tag_string") == "hvc1",
            "video_size": video.get("width") == 1080 and video.get("height") == 1920,
            "video_aspect": video.get("sample_aspect_ratio") == "1:1"
            and video.get("display_aspect_ratio") == "9:16",
            "video_pix_fmt": video.get("pix_fmt") == "yuv420p10le",
            "video_color_range": video.get("color_range") == "tv",
            "video_color_space": video.get("color_space") == "bt709",
            "video_color_transfer": video.get("color_transfer") == "bt709",
            "video_color_primaries": video.get("color_primaries") == "bt709",
            "video_handler": video.get("tags", {}).get("handler_name") == "VideoHandler",
            "video_encoder": video.get("tags", {}).get("encoder") == VIDEO_ENCODER,
            "video_timecode": video.get("tags", {}).get("timecode") == TIMECODE,
            "audio_codec": audio.get("codec_name") == "aac",
            "audio_sample_rate": audio.get("sample_rate") == "48000",
            "audio_handler": audio.get("tags", {}).get("handler_name") == "SoundHandler",
            "timecode_track": timecode.get("codec_tag_string") == "tmcd",
            "timecode_handler": timecode.get("tags", {}).get("handler_name") == "TimeCodeHandler",
            "timecode_value": timecode.get("tags", {}).get("timecode") == TIMECODE,
            "no_bad_strings": not strings_found,
        }

        failed = [name for name, ok in checks.items() if not ok]
        result = {
            "ok": not failed,
            "failed": failed,
            "bad_strings": strings_found,
            "format": fmt.get("tags", {}),
            "video": _stream_summary(video),
            "audio": _stream_summary(audio),
            "timecode": _stream_summary(timecode),
        }
        if strict and failed:
            raise RuntimeError(f"DaVinci fingerprint validation failed: {failed}")
        return result
    except Exception as e:
        print(f"[Finalizer] Validation error: {e}")
        raise


def _set_encoding_tool(path: str) -> None:
    try:
        binary = shutil.which("AtomicParsley")
        if not binary:
            raise RuntimeError("AtomicParsley not found")
        result = subprocess.run(
            [binary, path, "--encodingTool", DAVINCI_ENCODER, "--overWrite"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"AtomicParsley failed: {result.stderr[-800:]}")
    except Exception as e:
        print(f"[Finalizer] Encoding tool patch failed: {e}")
        raise


def _patch_timecode_handler(path: str) -> None:
    try:
        with open(path, "rb") as f:
            data = f.read()

        patched, changed = _patch_top_level_boxes(data)
        if not changed:
            raise RuntimeError("No tmcd handler found to patch")

        tmp_path = f"{path}.finalizer.tmp"
        try:
            with open(tmp_path, "wb") as f:
                f.write(patched)
            os.replace(tmp_path, path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except Exception as e:
        print(f"[Finalizer] Timecode handler patch failed: {e}")
        raise


def _patch_top_level_boxes(data: bytes) -> tuple[bytes, bool]:
    changed = False
    growth_to_absorb = 0
    pos = 0
    out = bytearray()

    try:
        while pos + 8 <= len(data):
            size, typ, box_end = _read_box_header(data, pos, len(data))
            box = data[pos:box_end]

            if typ == b"moov":
                new_payload, child_changed = _patch_child_boxes(box[8:])
                new_box = struct.pack(">I", 8 + len(new_payload)) + typ + new_payload
                growth_to_absorb = len(new_box) - len(box)
                changed = changed or child_changed
                out.extend(new_box)
            elif typ == b"free" and growth_to_absorb > 0:
                new_size = size - growth_to_absorb
                if new_size < 8:
                    raise RuntimeError("free atom too small to absorb handler growth")
                out.extend(struct.pack(">I", new_size) + typ + box[8:new_size])
                growth_to_absorb = 0
            else:
                out.extend(box)

            pos = box_end

        if pos < len(data):
            out.extend(data[pos:])
        if growth_to_absorb:
            raise RuntimeError("No free atom after moov to preserve chunk offsets")
        return bytes(out), changed
    except Exception as e:
        print(f"[Finalizer] Top-level atom patch error: {e}")
        raise


def _patch_child_boxes(data: bytes) -> tuple[bytes, bool]:
    container_types = {b"moov", b"trak", b"mdia"}
    changed = False
    pos = 0
    out = bytearray()

    try:
        while pos + 8 <= len(data):
            size, typ, box_end = _read_box_header(data, pos, len(data))
            box = data[pos:box_end]
            payload = box[8:]

            if typ == b"hdlr" and len(payload) >= 24:
                handler_type = payload[8:12]
                if handler_type == b"tmcd":
                    name_start = 24
                    new_payload = payload[:name_start] + b"TimeCodeHandler\0"
                    out.extend(struct.pack(">I", 8 + len(new_payload)) + typ + new_payload)
                    changed = True
                else:
                    out.extend(box)
            elif typ in container_types:
                new_payload, child_changed = _patch_child_boxes(payload)
                out.extend(struct.pack(">I", 8 + len(new_payload)) + typ + new_payload)
                changed = changed or child_changed
            else:
                out.extend(box)

            pos = box_end

        if pos < len(data):
            out.extend(data[pos:])
        return bytes(out), changed
    except Exception as e:
        print(f"[Finalizer] Child atom patch error: {e}")
        raise


def _read_box_header(data: bytes, pos: int, end: int) -> tuple[int, bytes, int]:
    try:
        size = struct.unpack(">I", data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        if size == 0:
            box_end = end
        elif size == 1:
            raise RuntimeError("Extended-size MP4 atom is not supported")
        else:
            box_end = pos + size
        if size < 8 or box_end > end:
            raise RuntimeError(f"Invalid MP4 atom {typ!r} at offset {pos}")
        return size, typ, box_end
    except Exception as e:
        print(f"[Finalizer] Atom header read error: {e}")
        raise


def _ffprobe(path: str) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr[-800:]}")
        return json.loads(result.stdout)
    except Exception as e:
        print(f"[Finalizer] ffprobe error: {e}")
        raise


def _scan_bad_strings(path: str) -> list[str]:
    try:
        with open(path, "rb") as f:
            data = f.read()
        found = []
        for needle in BAD_FINGERPRINT_STRINGS:
            if needle.encode("utf-8") in data:
                found.append(needle)
        return found
    except Exception as e:
        print(f"[Finalizer] String scan error: {e}")
        raise


def _first_stream(streams: list[dict[str, Any]], codec_type: str, codec_tag: str | None = None) -> dict[str, Any]:
    try:
        for stream in streams:
            if stream.get("codec_type") != codec_type:
                continue
            if codec_tag and stream.get("codec_tag_string") != codec_tag:
                continue
            return stream
        return {}
    except Exception as e:
        print(f"[Finalizer] Stream lookup error: {e}")
        raise


def _stream_summary(stream: dict[str, Any]) -> dict[str, Any]:
    try:
        return {
            "codec_type": stream.get("codec_type"),
            "codec_name": stream.get("codec_name"),
            "profile": stream.get("profile"),
            "codec_tag_string": stream.get("codec_tag_string"),
            "width": stream.get("width"),
            "height": stream.get("height"),
            "pix_fmt": stream.get("pix_fmt"),
            "sample_rate": stream.get("sample_rate"),
            "handler_name": stream.get("tags", {}).get("handler_name"),
            "encoder": stream.get("tags", {}).get("encoder"),
            "timecode": stream.get("tags", {}).get("timecode"),
        }
    except Exception as e:
        print(f"[Finalizer] Stream summary error: {e}")
        raise
