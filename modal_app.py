"""
Modal GPU service for S08 (export) + S09 (reframe) + S10 (captions).
Deploy: modal deploy modal_app.py
Called by Railway orchestrator after S07 completes.
"""
import os
import modal

# --- Image ---
gpu_image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.4.1-runtime-ubuntu22.04",
        add_python="3.11",
    )
    .apt_install(
        "ffmpeg",
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

app = modal.App("gpu-pipeline", image=gpu_image)


@app.function(
    gpu="A10G",
    memory=16384,
    cpu=4,
    timeout=900,
    scaledown_window=10,
    secrets=[modal.Secret.from_name("gpu-pipeline-secrets")],
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
    gpu="A10G",
    memory=8192,
    cpu=2,
    timeout=300,
    scaledown_window=10,
    secrets=[modal.Secret.from_name("gpu-pipeline-secrets")],
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
