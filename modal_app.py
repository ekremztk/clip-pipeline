"""
Modal GPU service for S08 (export) + S09 (reframe) + S10 (captions).
Deploy: modal deploy modal_app.py
Called by Railway orchestrator after S07 completes.
"""
import os
import modal

MODAL_GPU_APP_NAME = os.getenv("MODAL_GPU_APP_NAME", "gpu-pipeline")
MODAL_GPU_SECRET_NAME = os.getenv("MODAL_GPU_SECRET_NAME", "gpu-pipeline-secrets")

# --- Image ---
gpu_image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.4.1-devel-ubuntu22.04",
        add_python="3.11",
    )
    .apt_install(
        "libsndfile1",
        "libfreetype6-dev",
        "libjpeg-dev",
        "zlib1g-dev",
        "libglib2.0-0",
        "libgl1",
        "curl",
        "git",
        "pkg-config",
        "build-essential",
        "xz-utils",
        "nasm",
        "libass-dev",
        "libfdk-aac-dev",
        "libx264-dev",
        "libx265-dev",
        "fontconfig",
        "atomicparsley",
    )
    .run_commands(
        # Build FFmpeg 7.1 with NVENC (av1_nvenc, hevc_nvenc, h264_nvenc)
        "git clone --depth 1 https://git.videolan.org/git/ffmpeg/nv-codec-headers.git /tmp/nv-codec-headers",
        "cd /tmp/nv-codec-headers && make install",
        'curl -fsSL "https://ffmpeg.org/releases/ffmpeg-7.1.tar.xz" -o /tmp/ffmpeg-7.1.tar.xz',
        "tar -xf /tmp/ffmpeg-7.1.tar.xz -C /tmp",
        "cd /tmp/ffmpeg-7.1 && ./configure --enable-gpl --enable-nonfree --enable-cuda-nvcc "
        "--enable-libnpp --enable-nvenc --enable-libass --enable-libfdk-aac "
        "--enable-libx264 --enable-libx265 --extra-cflags=-I/usr/local/cuda/include "
        "--extra-ldflags=-L/usr/local/cuda/lib64 --prefix=/usr/local && "
        "make -j$(nproc) && make install",
        "rm -rf /tmp/ffmpeg-7.1* /tmp/nv-codec-headers",
        "ldconfig",
    )
    .run_commands(
        "mkdir -p /usr/share/fonts/truetype/montserrat /root/.fonts",
        'curl -fsSL -o /usr/share/fonts/truetype/montserrat/Montserrat-Bold.ttf "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-Bold.ttf"',
        'curl -fsSL -o /usr/share/fonts/truetype/montserrat/Montserrat-Regular.ttf "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-Regular.ttf"',
        "cp /usr/share/fonts/truetype/montserrat/*.ttf /root/.fonts/",
        "fc-cache -fv",
    )
    .pip_install(
        "torch==2.4.0",
        "torchvision==0.19.0",
        "torchaudio==2.4.0",
        extra_index_url="https://download.pytorch.org/whl/cu124",
    )
    .pip_install(
        "fastapi==0.135.1",
        "uvicorn==0.41.0",
        "ultralytics>=8.1.0",
        "Pillow",
        "opencv-python-headless",
        "google-genai",
        "google-cloud-storage",
        "google-auth",
        "deepgram-sdk==3.2.7",
        "anthropic",
        "supabase",
        "boto3",
        "httpx>=0.27.0",
        "requests",
        "numpy",
        "python-dotenv",
        "pydantic",
        "aiohttp",
        "soundfile",
        "librosa",
        "huggingface_hub==0.25.2",
        "speechbrain==1.0.2",
    )
    .run_commands(
        "mkdir -p /app/models",
        'curl -fsSL -o /app/models/yolov8l-face.pt "https://huggingface.co/arnabdhar/YOLOv8-Face-Detection/resolve/main/model.pt"',
        "mkdir -p /app/output /app/temp_uploads && chmod 777 /app/output /app/temp_uploads",
        # Pre-download SpeechBrain ECAPA-TDNN (VoxCeleb1-O EER 0.80%, 192-dim)
        'python -c "from speechbrain.inference.speaker import EncoderClassifier; EncoderClassifier.from_hparams(source=\'speechbrain/spkrec-ecapa-voxceleb\', savedir=\'/app/models/ecapa\')"',
    )
    .add_local_dir(
        "/Users/ekrem/prognot/backend/app",
        remote_path="/app/app",
    )
)

app = modal.App(MODAL_GPU_APP_NAME, image=gpu_image)


def _configure_pipeline_encode() -> None:
    """
    Pin the encode profile every step renders with.

    The secret still carries FFMPEG_VIDEO_CODEC=hevc_nvenc from an old metadata
    experiment, so anything that reads the environment as it finds it encodes
    HEVC — and HEVC here comes out around 0.3 Mbps against h264's 10, because
    the shared args pass `-rc vbr -cq` with no `-b:v 0` and the encoder falls
    back to a low target bitrate instead of treating cq as the quality it asks
    for. Every entry point must call this before running a step; the captions
    endpoint did not, and shipped a clip at a thirtieth of the right bitrate.
    """
    pipeline_codec = os.environ.get("FFMPEG_PIPELINE_VIDEO_CODEC", "h264_nvenc")
    if pipeline_codec == "hevc_nvenc" and os.environ.get("ALLOW_HEVC_PIPELINE", "").lower() not in {"1", "true", "yes"}:
        pipeline_codec = "h264_nvenc"
    os.environ["FFMPEG_VIDEO_CODEC"] = pipeline_codec
    os.environ["FFMPEG_ENCODE_PRESET"] = os.environ.get("FFMPEG_PIPELINE_ENCODE_PRESET", "p4")
    os.environ["FFMPEG_HWACCEL"] = os.environ.get("FFMPEG_PIPELINE_HWACCEL", "cuda")
    os.environ["FFMPEG_MIN_ACCEPTABLE_VIDEO_BITRATE"] = os.environ.get(
        "FFMPEG_PIPELINE_FINAL_MIN_ACCEPTABLE_VIDEO_BITRATE",
        "5000000",
    )


@app.function(
    gpu="L40S",
    memory=16384,
    cpu=4,
    timeout=2400,
    scaledown_window=10,
    secrets=[modal.Secret.from_name(MODAL_GPU_SECRET_NAME)],
)
def process_clips(
    job_id: str,
    channel_id: str,
    user_id: str | None,
    video_title: str,
    source_video_url: str,
    clips: list[dict],
    transcript_data: dict | None,
    reframe_content_type: str,
    caption_template: str,
) -> dict:
    """
    Runs S08 → S09 → S10 on GPU.
    Called from Railway orchestrator after S07.
    Returns dict with exported_clips, reframed_clips, captioned_clips.
    """
    import sys
    import time
    import uuid
    import requests
    import traceback
    import json
    import tempfile

    sys.path.insert(0, "/app")

    _configure_pipeline_encode()

    # Write GCP credentials to a temp file so all google-auth code paths
    # (including implicit ADC fallback) find credentials without needing
    # explicit credential passing.
    gcp_json = os.environ.get("GCP_CREDENTIALS_JSON", "")
    if gcp_json and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        try:
            _cred_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            )
            _cred_file.write(gcp_json)
            _cred_file.flush()
            _cred_file.close()
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _cred_file.name
            print(f"[Modal] GCP ADC credentials written to {_cred_file.name}")
        except Exception as _e:
            print(f"[Modal] Warning: could not write GCP credentials file: {_e}")

    start = time.time()
    print(f"[Modal] Job {job_id}: {len(clips)} clips, reframe={reframe_content_type}, template={caption_template}")

    # Download source video
    local_video = f"/app/temp_uploads/src_{uuid.uuid4().hex}.mp4"
    try:
        print("[Modal] Downloading source video...")
        resp = requests.get(source_video_url, stream=True, timeout=300)
        resp.raise_for_status()
        with open(local_video, "wb") as f:
            for chunk in resp.iter_content(chunk_size=131072):
                if chunk:
                    f.write(chunk)
        size_mb = os.path.getsize(local_video) / 1024 / 1024
        print(f"[Modal] Downloaded {size_mb:.1f}MB")
    except Exception as e:
        return {"status": "failed", "error": f"Video download failed: {e}", "clips": []}

    try:
        # S08: Export
        print("[Modal] S08 starting...")
        from app.pipeline.steps import s08_export
        exported_clips = s08_export.run(
            cut_results=clips,
            job_id=job_id,
            channel_id=channel_id,
            video_path=local_video,
            video_title=video_title,
            user_id=user_id,
            transcript_data=transcript_data,
        )
        print(f"[Modal] S08 done: {len(exported_clips)} clips exported")

        if not exported_clips:
            return {"status": "failed", "error": "S08 exported 0 clips", "clips": []}

        # S08.5: Upscale short landscape clips only when S08 produced sub-1080p output.
        print("[Modal] S08.5 starting...")
        from app.pipeline.steps import s08_5_upscale
        exported_clips = s08_5_upscale.run(
            exported_clips=exported_clips,
            job_id=job_id,
            channel_id=channel_id,
        )
        upscaled_count = sum(1 for c in exported_clips if c.get("s08_5_upscaled"))
        print(f"[Modal] S08.5 done: {upscaled_count}/{len(exported_clips)} clips upscaled")

        if not exported_clips:
            return {"status": "failed", "error": "S08.5 passed 0 clips", "clips": []}

        # S09: Reframe
        print("[Modal] S09 starting...")
        from app.pipeline.steps import s09_reframe
        reframed_clips = s09_reframe.run(
            exported_clips=exported_clips,
            job_id=job_id,
            channel_id=channel_id,
            reframe_content_type=reframe_content_type,
        )
        reframed_count = sum(1 for c in reframed_clips if c.get("video_reframed_path"))
        print(f"[Modal] S09 done: {reframed_count}/{len(reframed_clips)} reframed")

        # S10: Captions
        source_clips = reframed_clips if reframed_clips else exported_clips
        print("[Modal] S10 starting...")
        from app.pipeline.steps import s10_captions
        captioned_clips = s10_captions.run(
            reframed_clips=source_clips,
            job_id=job_id,
            channel_id=channel_id,
            caption_template=caption_template,
        )
        captioned_count = sum(1 for c in captioned_clips if c.get("video_captioned_path"))
        print(f"[Modal] S10 done: {captioned_count}/{len(captioned_clips)} captioned")

        total = time.time() - start
        print(f"[Modal] Job {job_id} complete in {total:.1f}s")

        return {
            "status": "completed",
            "duration_s": round(total, 1),
            "exported_clips": exported_clips,
            "reframed_clips": reframed_clips,
            "captioned_clips": captioned_clips,
        }

    except Exception as e:
        traceback.print_exc()
        return {"status": "failed", "error": str(e), "clips": []}

    finally:
        if os.path.exists(local_video):
            try:
                os.remove(local_video)
            except Exception:
                pass


@app.function(
    gpu="T4",
    memory=8192,
    cpu=2,
    timeout=300,
    scaledown_window=10,
    secrets=[modal.Secret.from_name(MODAL_GPU_SECRET_NAME)],
)
def compute_voice_embedding(audio_bytes: bytes, filename: str) -> dict:
    """
    Extract a speaker embedding from an audio file using SpeechBrain ECAPA-TDNN.
    Returns {"embedding": [192 floats], "duration_sec": float}.
    VoxCeleb1-O EER 0.80%. Used by Voice Library for voice fingerprints.
    """
    import sys
    import time
    import tempfile
    import traceback

    sys.path.insert(0, "/app")

    start = time.time()
    print(f"[Modal/voice] Computing embedding for {filename} ({len(audio_bytes)} bytes)")

    tmp = tempfile.NamedTemporaryFile(
        mode="wb", suffix=os.path.splitext(filename)[1] or ".wav", delete=False
    )
    tmp.write(audio_bytes)
    tmp.flush()
    tmp.close()
    audio_path = tmp.name
    wav_path = audio_path.rsplit(".", 1)[0] + "_16k.wav"

    try:
        import subprocess
        import soundfile as sf
        import torch
        import torchaudio
        from speechbrain.inference.speaker import EncoderClassifier

        # Resample to 16kHz mono WAV (ECAPA expects 16kHz)
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", audio_path,
                "-ac", "1", "-ar", "16000",
                "-c:a", "pcm_s16le", wav_path,
            ],
            check=True,
            capture_output=True,
        )

        info = sf.info(wav_path)
        duration = float(info.frames) / float(info.samplerate)

        classifier = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="/app/models/ecapa",
            run_opts={"device": "cuda"},
        )

        signal, _ = torchaudio.load(wav_path)
        embedding = classifier.encode_batch(signal.to("cuda"))
        emb_tensor = embedding.squeeze().detach().cpu()
        emb_list = [float(x) for x in emb_tensor.tolist()]

        elapsed = time.time() - start
        print(f"[Modal/voice] Done in {elapsed:.1f}s — duration={duration:.1f}s, dim={len(emb_list)}")

        return {
            "embedding": emb_list,
            "duration_sec": duration,
        }

    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}
    finally:
        for p in [audio_path, wav_path]:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass


@app.function(
    # A T4, not the L40S that process_clips needs. Captioning is a Deepgram
    # call, Pillow drawing one frame at a time, and a single nvenc encode —
    # none of which needs a large card. Asking for one only lengthens the wait
    # for a free GPU, which is where the time actually went: startup measured
    # 2-4s while one request sat in the queue for five and a half minutes.
    gpu="T4",
    memory=8192,
    cpu=4,
    timeout=900,
    scaledown_window=10,
    secrets=[modal.Secret.from_name(MODAL_GPU_SECRET_NAME)],
)
def caption_clip(
    video_url: str,
    request_id: str,
    template_key: str = "clean",
    channel_id: str | None = None,
) -> dict:
    """
    Burn captions onto one already-vertical clip and return its URL.

    The standalone counterpart to what S10 does inside a pipeline run: you have
    a 9:16 cut from somewhere else and want this channel's caption style and
    watermark on it, without a job, a source video or the nine steps before it.

    S10 needs no transcript handed to it — it transcribes the clip it is given,
    which is what makes this step isolatable at all. The clip dict deliberately
    carries no "id", so S10 writes nothing to the clips table: an API call is
    not a pipeline run and must not leave rows behind.
    """
    import sys
    sys.path.insert(0, "/app")

    _configure_pipeline_encode()

    from app.pipeline.steps import s10_captions

    results = s10_captions.run(
        reframed_clips=[{"video_reframed_path": video_url}],
        # No job exists, but the id still names R2 keys, so it has to be
        # unique or two calls would overwrite each other's output. The caller
        # passes one per request, under an "api/" prefix that keeps API output
        # separable from pipeline output in the bucket.
        job_id=f"api/{request_id}",
        channel_id=channel_id or "",
        caption_template=template_key,
    )

    if not results or not results[0].get("video_captioned_path"):
        raise RuntimeError("Captioning produced no output")

    out = results[0]
    meta = out.get("caption_metadata") or {}
    return {
        "captioned_url": out["video_captioned_path"],
        "word_count": meta.get("word_count"),
        "language": meta.get("language"),
        "template": meta.get("template"),
        "thumbnail_url": out.get("thumbnail_path"),
        "video_bitrate_bps": meta.get("video_bitrate_bps"),
    }
