"""Shared FFmpeg encoding arguments for pipeline renders.

S08, S09, and S10 should use the same video/audio encode contract. Stage-specific
code owns filters, timing, crop, and overlay logic; this module owns codec
selection and encode quality.
"""
from __future__ import annotations

from app.config import settings

NVENC_CODECS = {"av1_nvenc", "hevc_nvenc", "h264_nvenc"}
H264_CODECS = {"libx264", "h264_nvenc"}


def pipeline_video_codec() -> str:
    """Return the configured pipeline video codec."""
    return settings.FFMPEG_VIDEO_CODEC


def pipeline_video_preset(codec: str | None = None) -> str:
    """Return the preset that matches the configured codec family."""
    selected = codec or pipeline_video_codec()
    if selected in NVENC_CODECS:
        return settings.FFMPEG_ENCODE_PRESET
    return settings.FFMPEG_PRESET


def describe_pipeline_encode_profile() -> str:
    """Human-readable encode profile for logs."""
    codec = pipeline_video_codec()
    preset = pipeline_video_preset(codec)
    if codec in NVENC_CODECS:
        return f"codec={codec}, preset={preset}, rc=vbr, cq={settings.FFMPEG_CRF}"
    return f"codec={codec}, preset={preset}, crf={settings.FFMPEG_CRF}"


def append_pipeline_video_encode_args(
    cmd: list[str],
    *,
    codec: str | None = None,
    pix_fmt: str = "yuv420p",
) -> str:
    """Append the shared S08/S09/S10 video encode args and return the codec."""
    selected = codec or pipeline_video_codec()
    preset = pipeline_video_preset(selected)

    cmd.extend(["-c:v", selected])
    if selected in NVENC_CODECS:
        cmd.extend(["-preset", preset, "-rc", "vbr", "-cq", str(settings.FFMPEG_CRF)])
    else:
        cmd.extend(["-preset", preset, "-crf", str(settings.FFMPEG_CRF)])

    if selected in H264_CODECS:
        cmd.extend(["-profile:v", "high"])

    if pix_fmt:
        cmd.extend(["-pix_fmt", pix_fmt])

    return selected


def append_pipeline_audio_encode_args(cmd: list[str], *, has_audio: bool = True) -> None:
    """Append the shared audio encode args."""
    if has_audio:
        cmd.extend(["-c:a", "aac", "-b:a", "320k", "-ar", "48000"])
    else:
        cmd.append("-an")

