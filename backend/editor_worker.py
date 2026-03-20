# EDITOR MODULE — Isolated module, no dependencies on other project files

# RAILWAY DEPLOYMENT:
# 1. Add a Redis plugin in Railway dashboard → copy REDIS_URL as EDITOR_REDIS_URL
# 2. Add a new Railway service pointing to the same repo
#    Start command: celery -A editor_celery worker --loglevel=info -Q editor --concurrency=2
# 3. Required env vars: EDITOR_REDIS_URL, DEEPGRAM_API_KEY, R2_*, GCS_*, SUPABASE_URL, SUPABASE_SERVICE_KEY
# 4. Required OS packages: ffmpeg
#    Add to nixpacks.toml: [phases.setup] nixPkgs = ['ffmpeg']
# SMART REFRAME DEPENDENCIES:
# pip install mediapipe opencv-python-headless
# Note: Use opencv-python-headless (NOT opencv-python) on Railway
# opencv-python requires a display server; headless version does not
# nixpacks.toml: nixPkgs = ['ffmpeg', 'libglib2.0-0', 'libsm6', 'libxrender1', 'libxext6']

import os
import asyncio
import logging
import subprocess
import json
import boto3
import librosa
from deepgram import DeepgramClient, PrerecordedOptions

from editor_celery import editor_celery_app
from editor_database import get_editor_job, update_editor_job
from editor_config import (
    R2_ENDPOINT_URL,
    R2_ACCESS_KEY_ID,
    R2_SECRET_ACCESS_KEY,
    R2_EDITOR_BUCKET_NAME,
    DEEPGRAM_API_KEY
)
from editor_storage import upload_local_to_gcs

logger = logging.getLogger("editor.worker")

@editor_celery_app.task(bind=True, name="editor.pre_process_video")
def pre_process_video(self, job_id: str) -> None:
    """
    Celery task to pre-process a video for the editor module.
    Steps:
    1. Update status
    2. Download from R2
    2.5 Extract audio
    3. Extract metadata
    4. Deepgram transcription
    5. Librosa silence detection
    6. Upload to GCS
    7. Finalize
    """
    source_path = f"/tmp/editor_{job_id}_source.mp4"
    audio_path = f"/tmp/editor_{job_id}_audio.wav"
    
    try:
        # Step 1
        asyncio.run(update_editor_job(job_id, status='processing', progress=5))
        
        # Step 2
        job = asyncio.run(get_editor_job(job_id))
        if not job:
            raise ValueError(f"Job {job_id} not found in database")
            
        source_r2_key = job.get('source_r2_key')
        if not source_r2_key:
            raise ValueError(f"Job {job_id} missing source_r2_key")
            
        s3_client = boto3.client(
            's3',
            endpoint_url=R2_ENDPOINT_URL,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY
        )
        s3_client.download_file(R2_EDITOR_BUCKET_NAME, source_r2_key, source_path)
        
        # Step 2.1 — Normalize to CFR 30fps (Variable Frame Rate fix)
        # CRITICAL: Zoom recordings, iPhone screen recordings, and many mobile videos
        # use Variable Frame Rate (VFR). VFR causes progressive A/V sync drift when
        # processed by FFmpeg and Remotion — subtitles that are correct at 0:00 drift
        # by several seconds at 1:00. Normalizing to CFR 30fps fixes this permanently.
        normalized_path = f"/tmp/editor_{job_id}_cfr.mp4"
        normalize_cmd = [
            "ffmpeg", "-y",
            "-i", source_path,
            "-vsync", "1",           # Force constant frame rate
            "-r", "30",              # Target 30fps
            "-c:v", "libx264",       # Re-encode video
            "-c:a", "copy",          # Keep audio as-is
            "-preset", "ultrafast",  # Fast re-encode
            normalized_path
        ]
        result = subprocess.run(normalize_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning(f"VFR normalization failed for job {job_id}, using original: {result.stderr}")
            # Non-fatal: continue with original file
        else:
            source_path = normalized_path  # Use normalized file for all subsequent steps
            logger.info(f"VFR normalization complete for job {job_id}")

        # Step 2.5 - Extract lightweight audio with FFmpeg
        cmd_extract = [
            "ffmpeg", "-y", "-i", source_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            audio_path
        ]
        subprocess.run(cmd_extract, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        asyncio.run(update_editor_job(job_id, progress=15))
        
        # Step 3 - Extract video metadata with FFprobe
        cmd_probe = [
            "ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams",
            source_path
        ]
        probe_result = subprocess.run(cmd_probe, capture_output=True, text=True, check=True)
        probe_data = json.loads(probe_result.stdout)
        
        video_stream = next((s for s in probe_data.get("streams", []) if s.get("codec_type") == "video"), None)
        metadata = {}
        if video_stream:
            duration = float(video_stream.get("duration", 0))
            fps_str = video_stream.get("avg_frame_rate", "0/1")
            if "/" in fps_str:
                num, den = fps_str.split("/")
                fps = float(num) / float(den) if float(den) != 0 else 0
            else:
                fps = float(fps_str)
                
            metadata = {
                "duration": duration,
                "fps": fps,
                "width": int(video_stream.get("width", 0)),
                "height": int(video_stream.get("height", 0)),
                "codec": video_stream.get("codec_name", "")
            }
        asyncio.run(update_editor_job(job_id, video_metadata=metadata, progress=25))
        
        # Step 4 - Deepgram transcription with diarization
        if not DEEPGRAM_API_KEY:
            raise ValueError("DEEPGRAM_API_KEY not configured")
            
        dg_client = DeepgramClient(DEEPGRAM_API_KEY)
        with open(audio_path, "rb") as f:
            buffer_data = f.read()
            
        payload = {"buffer": buffer_data}
        options = PrerecordedOptions(
            model="nova-2",
            diarize=True,
            punctuate=True,
            utterances=True,
            smart_format=True,
        )
        
        response = dg_client.listen.prerecorded.v("1").transcribe_file(payload, options)
        
        try:
            words = response.results.channels[0].alternatives[0].words
        except (KeyError, IndexError, AttributeError):
            words = []
            
        transcript = []
        for w in words:
            transcript.append({
                "word": getattr(w, "word", ""),
                "start": getattr(w, "start", 0.0),
                "end": getattr(w, "end", 0.0),
                "speaker": getattr(w, "speaker", 0),
                "confidence": getattr(w, "confidence", 0.0)
            })
            
        speaker_segments = []
        current_seg = None
        for w in transcript:
            spk = w["speaker"]
            if current_seg is None:
                current_seg = {"start": w["start"], "end": w["end"], "speaker_id": spk}
            elif current_seg["speaker_id"] == spk:
                current_seg["end"] = w["end"]
            else:
                speaker_segments.append(current_seg)
                current_seg = {"start": w["start"], "end": w["end"], "speaker_id": spk}
        if current_seg:
            speaker_segments.append(current_seg)
            
        asyncio.run(update_editor_job(job_id, transcript=transcript, speaker_segments=speaker_segments, progress=60))
        
        # Step 5 - Silence detection with Librosa
        y, sr = librosa.load(audio_path, sr=16000)
        non_silent_intervals_frames = librosa.effects.split(y, top_db=40)
        
        speech_intervals = []
        for interval in non_silent_intervals_frames:
            start_sec = float(librosa.frames_to_time(interval[0], sr=sr))
            end_sec = float(librosa.frames_to_time(interval[1], sr=sr))
            speech_intervals.append({"start": start_sec, "end": end_sec})
            
        silent_intervals = []
        duration_sec = float(librosa.get_duration(y=y, sr=sr))
        
        prev_end = 0.0
        for sp in speech_intervals:
            if sp["start"] - prev_end > 0.3:
                silent_intervals.append({"start": prev_end, "end": sp["start"]})
            prev_end = sp["end"]
            
        if duration_sec - prev_end > 0.3:
            silent_intervals.append({"start": prev_end, "end": duration_sec})
            
        silence_map = {
            "silent_intervals": silent_intervals,
            "speech_intervals": speech_intervals
        }
        
        asyncio.run(update_editor_job(job_id, silence_map=silence_map, progress=80))
        
        # Step 5.5 — Smart Reframe (Face Detection + Speaker Mapping)
        asyncio.run(update_editor_job(job_id, progress=82))
        try:
            from editor_reframe import run_smart_reframe
            crop_segments = run_smart_reframe(
                job_id=job_id,
                video_path=source_path,
                speaker_segments=speaker_segments,
                video_metadata=metadata
            )
            # Store crop_segments in DB
            asyncio.run(update_editor_job(
                job_id,
                crop_segments=crop_segments,
                progress=88
            ))
            logger.info(f"Smart reframe complete for job {job_id}: {len(crop_segments)} segments")
        except Exception as e:
            # Smart reframe failure is NON-FATAL
            # Log error but continue pipeline — fallback to center crop
            logger.warning(f"Smart reframe failed for job {job_id}, using center crop: {e}")
            asyncio.run(update_editor_job(job_id, crop_segments=[], progress=88))
            
        # Step 6 - Upload video to GCS for AI processing
        gcs_key = f"editor_jobs/{job_id}/source.mp4"
        upload_local_to_gcs(source_path, gcs_key)
        asyncio.run(update_editor_job(job_id, progress=95))
        
        # Step 7 - Finalize
        asyncio.run(update_editor_job(job_id, status='completed', progress=100))
        
    except Exception as e:
        logger.exception(f"pre_process_video failed for job {job_id}")
        try:
            asyncio.run(update_editor_job(job_id, status='failed', error_message=str(e)))
        except Exception as inner_e:
            logger.error(f"Failed to update job {job_id} to failed status: {inner_e}")
    finally:
        normalized_path = f"/tmp/editor_{job_id}_cfr.mp4"
        for path in [source_path, audio_path, normalized_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError as e:
                    logger.warning(f"Failed to remove temp file {path}: {e}")

@editor_celery_app.task(bind=True, name="editor.auto_edit_task")
def auto_edit_task(self, job_id: str) -> None:
    try:
        asyncio.run(update_editor_job(job_id, status='processing', progress=10))

        job = asyncio.run(get_editor_job(job_id))
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if not job.get('transcript'):
            raise ValueError("Job has no transcript — run pre_process_video first")
        if not job.get('speaker_segments'):
            raise ValueError("Job has no speaker segments")
        if not job.get('silence_map'):
            raise ValueError("Job has no silence map")

        asyncio.run(update_editor_job(job_id, progress=20))

        from editor_gemini import generate_edit_decisions, validate_edit_decisions

        raw_decisions = generate_edit_decisions(
            transcript=job['transcript'],
            speaker_segments=job['speaker_segments'],
            silence_map=job['silence_map'],
            video_metadata=job['video_metadata'],
            target_max_duration=35.0
        )

        asyncio.run(update_editor_job(job_id, progress=80))

        video_duration = job['video_metadata']['duration']
        decisions = validate_edit_decisions(raw_decisions, video_duration)

        # Log reasoning for quality monitoring
        if decisions.get('_reasoning'):
            logger.info(f"Gemini reasoning for job {job_id}: {decisions['_reasoning']}")

        asyncio.run(update_editor_job(
            job_id,
            edit_spec=decisions,
            status='completed',
            progress=100
        ))

        logger.info(f"auto_edit_task completed for job {job_id}. Hook score: {decisions.get('hook_score')}")

    except Exception as e:
        asyncio.run(update_editor_job(
            job_id,
            status='failed',
            error_message=str(e)
        ))
        logger.exception(f"auto_edit_task failed for job {job_id}")

@editor_celery_app.task(bind=True, name="editor.render_video_task")
def render_video_task(self, job_id: str, edit_spec: dict) -> None:
    source_path = f"/tmp/editor_{job_id}_source.mp4"
    output_path = f"/tmp/editor_{job_id}_output.mp4"
    r2_output_key = f"outputs/{job_id}/final.mp4"
    try:
        asyncio.run(update_editor_job(job_id, status='processing', progress=5))

        # Download source from R2 if not already in /tmp
        if not os.path.exists(source_path):
            job = asyncio.run(get_editor_job(job_id))
            if not job:
                raise ValueError("Job not found")
            source_r2_key = job.get('source_r2_key')
            if not source_r2_key:
                raise ValueError("source_r2_key missing from job")
            s3_client = boto3.client(
                's3',
                endpoint_url=R2_ENDPOINT_URL,
                aws_access_key_id=R2_ACCESS_KEY_ID,
                aws_secret_access_key=R2_SECRET_ACCESS_KEY
            )
            s3_client.download_file(R2_EDITOR_BUCKET_NAME, source_r2_key, source_path)

        asyncio.run(update_editor_job(job_id, progress=10))

        # Run two-pass render
        job_data = asyncio.run(get_editor_job(job_id))
        crop_segments = job_data.get('crop_segments') or []
        
        from editor_ffmpeg import render_video
        render_video(
            job_id=job_id,
            edit_spec=edit_spec,
            source_path=source_path,
            output_path=output_path,
            crop_segments=crop_segments if crop_segments else None
        )

        asyncio.run(update_editor_job(job_id, progress=85))

        # Upload output to R2
        s3_client = boto3.client(
            's3',
            endpoint_url=R2_ENDPOINT_URL,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY
        )
        s3_client.upload_file(output_path, R2_EDITOR_BUCKET_NAME, r2_output_key)

        # Generate download URL
        from editor_storage import generate_download_presigned_url
        download_url = asyncio.run(generate_download_presigned_url(r2_output_key))

        asyncio.run(update_editor_job(
            job_id,
            status='completed',
            progress=100,
            output_r2_key=r2_output_key,
            edit_spec=edit_spec
        ))
        logger.info(f"render_video_task completed for job {job_id}")

    except Exception as e:
        try:
            asyncio.run(update_editor_job(job_id, status='failed', error_message=str(e)))
        except Exception:
            pass
        logger.exception(f"render_video_task failed for job {job_id}")
    finally:
        for path in [source_path, output_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
