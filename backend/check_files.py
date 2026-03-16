import sys
import os

files = [
    "backend/app/config.py",
    "backend/app/main.py",
    "backend/app/models/enums.py",
    "backend/app/models/schemas.py",
    "backend/app/services/supabase_client.py",
    "backend/app/services/storage.py",
    "backend/app/services/gemini_client.py",
    "backend/app/services/deepgram_client.py",
    "backend/app/pipeline/orchestrator.py",
    "backend/app/pipeline/steps/s01_audio_extract.py",
    "backend/app/pipeline/steps/s02_transcribe.py",
    "backend/app/pipeline/steps/s03_speaker_id.py",
    "backend/app/pipeline/steps/s04_labeled_transcript.py",
    "backend/app/pipeline/steps/s05_energy_map.py",
    "backend/app/pipeline/steps/s06_video_analysis.py",
    "backend/app/pipeline/steps/s07_context_build.py",
    "backend/app/pipeline/steps/s07b_humor_map.py",
    "backend/app/pipeline/steps/s07c_signal_fusion.py",
    "backend/app/pipeline/steps/s08_clip_finder.py",
    "backend/app/pipeline/steps/s09_quality_gate.py",
    "backend/app/pipeline/steps/s09b_clip_strategy.py",
    "backend/app/pipeline/steps/s10_precision_cut.py",
    "backend/app/pipeline/steps/s11_export.py",
    "backend/app/api/routes/jobs.py",
    "backend/app/api/routes/clips.py",
    "backend/app/api/routes/channels.py",
    "backend/app/api/routes/speakers.py",
    "backend/app/api/routes/downloads.py",
    "backend/app/api/routes/feedback.py",
    "backend/app/api/websocket/progress.py",
    "backend/app/memory/rag.py",
    "backend/app/memory/dynamic_context.py",
    "backend/app/memory/feedback_processor.py",
    "backend/workers/video_worker.py"
]

import json

for i, f in enumerate(files):
    if not os.path.exists(f):
        print(f"File {f} not found!")
    else:
        with open(f, 'r') as fp:
            content = fp.read()
        print(f"==================== {f} ====================")
        print(content)
        print(f"==================== END {f} ====================\n")
