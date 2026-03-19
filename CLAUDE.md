# PROGNOT CLIP PIPELINE — CLAUDE.md
> Read this before touching any file.

---

## DEPLOYMENT
- Backend → Railway (Docker, CPU only, 8GB RAM)
- Frontend → Vercel (Next.js)
- Database → Supabase (PostgreSQL + pgvector)
- CI/CD → `git push` to main → auto deploy

## PIPELINE STRUCTURE (V4 — 8 Steps)
```
S01 Audio Extract (FFmpeg)
S02 Transcribe (Deepgram)
S03 Speaker ID (Deepgram diarization + user confirm)
S04 Labeled Transcript
S05 Unified Discovery (Gemini Pro + Video — finds clip candidates)
S06 Batch Evaluation (Gemini Pro + Text — scores, quality gate, strategy)
S07 Precision Cut (FFmpeg + word boundary snap)
S08 Export (FFmpeg re-encode + R2 upload + DB write)
```

## ABSOLUTE RULES

### Gemini model usage
- S05 Unified Discovery: `gemini-2.5-pro` (video + text, critical)
- S06 Batch Evaluation: `gemini-2.5-pro` (text only, critical)
- All other Gemini calls (guest research, channel DNA generation, etc.): `gemini-2.5-flash`
- Config keys: `settings.GEMINI_MODEL_PRO` and `settings.GEMINI_MODEL_FLASH`
- Never change models without being asked

### No GPU libraries — ever
Railway has no GPU. These will crash the build:
- PyTorch, TensorFlow, transformers, WhisperX (local), MediaPipe
- Any local AI model

### No Turkish in code
- Variable names, function names, comments, prompts, string literals → English only
- Exception: user-facing UI text in frontend

### Supabase connection
- Port MUST be `6543` (Connection Pooler), never `5432`
- `5432` is unreachable from Railway/Docker

### FFmpeg encoding
- S07 (precision cut): `-c copy` (lossless stream copy, fast)
- S08 (export): `-c:v libx264 -preset slow -crf 18 -c:a aac -b:a 320k`
- Only ONE re-encode per clip (in S08). S07 does lossless copy.

### pgvector embedding size
- clips.clip_summary_embedding → `vector(768)` — do NOT change
- reference_clips.clip_summary_embedding → `vector(768)`

### Temp file cleanup — always use finally
```python
finally:
    for path in [audio_path, video_path]:
        if os.path.exists(path):
            os.remove(path)
```

### Error handling — every function needs try/except
```python
try:
    result = operation()
except Exception as e:
    print(f"[ModuleName] Error: {e}")
    result = fallback_value
```

### Gemini prompt — never use .format() on prompts with JSON
```python
# WRONG — curly braces clash with JSON
prompt = "Return: {{'key': 'value'}}".format(x=y)

# CORRECT
prompt = "Return: {'key': 'value'}"
prompt = prompt.replace("PLACEHOLDER", value)
```

## DO NOT TOUCH
- `backend/reframer.py` — Module 2, suspended indefinitely
- `frontend/next.config.js` — proxy config, leave as-is
- `backend/channels/` structure — channel isolation system
- `backend/app/memory/` — Feedback system, suspended indefinitely
- `backend/app/pipeline/steps/s01_audio_extract.py` through `s04_labeled_transcript.py` — these are stable

## ENVIRONMENT VARIABLES

### Railway
```
GEMINI_API_KEY=
DEEPGRAM_API_KEY=
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
DATABASE_URL=           # port 6543 mandatory
FRONTEND_URL=
```
### Vercel
```
NEXT_PUBLIC_API_URL=    # Railway backend URL
```
### Cloudflare R2
```
R2_ACCOUNT_ID=          # hex ID only, no URL
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=
R2_PUBLIC_URL=          # https://pub-xxxxx.r2.dev
```

## KNOWN PITFALLS
| Problem | Fix |
|---------|-----|
| Supabase "Network unreachable" | DATABASE_URL port must be 6543 |
| Gemini JSON parse error | Strip ` ```json ``` ` wrappers, use `re.sub(r'[\x00-\x1f]', '', raw)` |
| Gemini 429 rate limit | Retry: 30s wait × 2, then 60s, then raise |
| Docker build slow | COPY requirements.txt before COPY code |
| Video file not found | Always check `os.path.exists()` before FFmpeg |
