"""
Separate Modal renderer for Provision / Last Editor P04.

Deploy from repo root with the Modal credentials for the Provision account:
  modal deploy provision_modal_app.py

Required Modal secret in that account:
  provision-renderer-secrets

The secret must include the R2 env vars used by app.services.r2_client.
"""

from __future__ import annotations

import os
from pathlib import Path

import modal


SECRET_NAME = os.environ.get("PROVISION_MODAL_SECRET_NAME", "provision-renderer-secrets")
APP_NAME = os.environ.get("PROVISION_MODAL_APP_NAME", "provision-renderer")


renderer_image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.4.1-devel-ubuntu22.04",
        add_python="3.11",
    )
    .apt_install(
        "curl",
        "git",
        "pkg-config",
        "build-essential",
        "xz-utils",
        "nasm",
        "libfdk-aac-dev",
        "libx264-dev",
        "libx265-dev",
        "libfontconfig1",
    )
    .run_commands(
        "git clone --depth 1 https://git.videolan.org/git/ffmpeg/nv-codec-headers.git /tmp/nv-codec-headers",
        "cd /tmp/nv-codec-headers && make install",
        'curl -fsSL "https://ffmpeg.org/releases/ffmpeg-7.1.tar.xz" -o /tmp/ffmpeg-7.1.tar.xz',
        "tar -xf /tmp/ffmpeg-7.1.tar.xz -C /tmp",
        "cd /tmp/ffmpeg-7.1 && ./configure --enable-gpl --enable-nonfree --enable-nvenc "
        "--enable-libfdk-aac --enable-libx264 --enable-libx265 --prefix=/usr/local && "
        "make -j$(nproc) && make install",
        "rm -rf /tmp/ffmpeg-7.1* /tmp/nv-codec-headers",
        "ldconfig",
        "mkdir -p /app/temp_uploads /app/output && chmod 777 /app/temp_uploads /app/output",
    )
    .pip_install(
        "boto3",
        "requests",
        "pydantic",
        "python-dotenv",
    )
    .add_local_dir(
        Path(__file__).parent / "backend" / "app",
        remote_path="/app/app",
    )
)


app = modal.App(APP_NAME, image=renderer_image)


@app.function(
    gpu=["A10G", "T4"],
    memory=8192,
    cpu=4,
    timeout=600,
    scaledown_window=10,
    secrets=[modal.Secret.from_name(SECRET_NAME)],
)
def render_variant(input_video_url: str, plan: dict, variant_id: str) -> dict:
    import os
    import sys
    import uuid
    import requests

    sys.path.insert(0, "/app")

    os.environ["FFMPEG_VIDEO_CODEC"] = os.environ.get("PROVISION_RENDER_VIDEO_CODEC", "h264_nvenc")
    os.environ["FFMPEG_ENCODE_PRESET"] = os.environ.get("PROVISION_RENDER_ENCODE_PRESET", "p4")
    os.environ["FFMPEG_HWACCEL"] = os.environ.get("PROVISION_RENDER_HWACCEL", "cuda")

    local_path = f"/app/temp_uploads/provision_{uuid.uuid4().hex}.mp4"
    try:
        print(f"[ProvisionModal] Downloading input variant={variant_id}")
        with requests.get(input_video_url, stream=True, timeout=300) as response:
            response.raise_for_status()
            with open(local_path, "wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)

        size_mb = os.path.getsize(local_path) / 1024 / 1024
        print(f"[ProvisionModal] Input downloaded: {size_mb:.1f}MB")

        from app.provision.steps import p04_render_variant

        result = p04_render_variant.run(
            local_path,
            plan,
            variant_id,
            video_codec=os.environ["FFMPEG_VIDEO_CODEC"],
        )
        print(f"[ProvisionModal] Render complete variant={variant_id} duration={result.get('duration_s')}")
        return {"status": "completed", **result}
    except Exception as exc:
        print(f"[ProvisionModal] Render failed variant={variant_id}: {exc}")
        return {"status": "failed", "error": str(exc)}
    finally:
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass

