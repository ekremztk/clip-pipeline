# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## REPO STRUCTURE

This is a **monorepo with two separate web applications**:

| Directory | App | URL | Stack |
|-----------|-----|-----|-------|
| `frontend/` | Prognot Studio (clip pipeline UI) | clip.prognot.com | Next.js 16, npm, Supabase Auth |
| `opencut/apps/web/` | Video Editor | edit.prognot.com | Next.js 16, Bun, Turbopack, Supabase Auth |
| `lern/` | Language Learning App | lern.prognot.com | Next.js 16, npm, Supabase SSR |
| `backend/` | API server | Railway | FastAPI, Python 3.11 |
| `landing/` | Marketing page | prognot.com | Static HTML |

The frontends are **completely independent** — separate `node_modules`, separate env files, separate deploys.

---

## DEVELOPMENT COMMANDS

### Lern App (lern.prognot.com)
```bash
cd lern
npm install
npm run dev       # dev server on :3001
npm run build     # production build
```
Deploy: `cd lern && vercel --prod` (NOT auto-deploy from git — manual only)

### Backend (FastAPI + Python 3.11)
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
Entry point: `backend/app/main.py` — FastAPI app with lifespan schedulers.

### Prognot Frontend (clip.prognot.com)
```bash
cd frontend
npm install
npm run dev       # dev server on :3000
npm run build     # production build (Vercel uses this)
```

### Editor (edit.prognot.com) — uses Bun, not npm
```bash
cd opencut
bun install
bun dev:web       # Turbopack dev server :3000
bun build:web     # production build
bun lint:web      # Biome linter
bun lint:web:fix  # auto-fix linting
bun format:web    # Biome formatter
```

### Docker (matches Railway deployment)
```bash
docker build -t prognot .
docker run -p 8080:8080 --env-file backend/.env prognot
```

No test suite exists. No linter is configured for `frontend/` or `backend/`.

---

## DEPLOYMENT
- Backend → Railway (Docker, CPU only, 8GB RAM)
- GPU Pipeline (S08+S09+S10) → Modal (`modal_app.py`, A10G GPU)
- Prognot Frontend → Vercel (`frontend/`)
- Editor → Vercel (`opencut/apps/web/`)
- Database → Supabase (PostgreSQL + pgvector)
- Storage → Cloudflare R2 (clip exports + editor media)
- CI/CD → `git push` to main → auto deploy Railway + Vercel

### Modal GPU deploy
```bash
# Deploy (run from monorepo root):
modal deploy modal_app.py

# Secrets stored in Modal as 'gpu-pipeline-secrets'.
# Vertex AI auth uses GCP_CREDENTIALS_JSON (service account JSON).
# After ANY change to backend/app/pipeline/steps/s08*, s09*, s10*,
# backend/app/captions/, or backend/app/reframe/ → must redeploy Modal.
```
Modal app: `https://modal.com/apps/hesapiki2000/main/deployed/gpu-pipeline`

---

## ARCHITECTURE

### Backend structure
```
backend/app/
├── main.py              # FastAPI entry, lifespan schedulers, CORS, router mount
├── config.py            # Settings singleton (all env vars)
├── pipeline/
│   ├── orchestrator.py  # State machine: runs S01→S10 in a single loop (no user pause); dispatches S08–S10 to Modal
│   ├── steps/s01-s10    # Individual pipeline steps
│   └── prompts/         # unified_discovery (S05, Claude), batch_evaluation (S06, Claude), channel_dna / clip_summary / failure_analysis (Gemini Flash, onboarding + feedback)
├── director/
│   ├── agent.py         # Gemini-powered agentic loop with function calling
│   ├── router.py        # SSE chat, memory, analysis endpoints
│   ├── tools/           # 11 tool modules (DB, filesystem, Langfuse, etc.)
│   ├── proactive.py     # Anomaly detection (hourly)
│   └── events.py        # Pipeline event collector
├── content_finder/      # Module 3 — in development (skeleton only)
│   ├── models.py        # ContentFinderJob, scoring models
│   ├── phases/          # Discovery pipeline phases
│   ├── prompts/         # Gemini prompts for analysis
│   ├── strategies/      # Search strategies
│   ├── utils/           # youtube_api, transcript_fetcher, score_calculator, guest_extractor
│   └── sourcing/        # UK talk-show sourcing (BBC → NZBgeek → Newshosting); see below
├── api/routes/          # 13 route modules (jobs, clips, speakers, channels, etc.)
├── services/            # External clients: Supabase, Gemini, Deepgram, R2
│   ├── video_downloader.py  # yt-dlp wrapper for video download
│   └── youtube_client.py    # YouTube Data API v3 wrapper
├── models/              # Pydantic schemas + enums (JobStatus, ContentType, etc.)
└── channels/            # Channel isolation system (DO NOT TOUCH)
```

### Prognot Frontend structure
```
frontend/app/
├── layout.tsx                # Root layout
├── providers.tsx             # PostHog + Sentry setup
├── (auth)/login/             # Supabase Auth (email + Google OAuth)
├── dashboard/
│   ├── layout.tsx            # Sidebar + ChannelContext provider
│   ├── page.tsx              # Overview: stats, active jobs, recent clips
│   ├── page.tsx              # Video upload + trim + pipeline trigger
│   ├── clips/                # "My Projects" — clip library with approval workflow
│   ├── channel-dna/          # Channel DNA editor (identity, tone, content types, reference clips)
│   ├── content-finder/       # Content Finder (coming soon stub)
│   ├── performance/          # Analytics (coming soon stub)
│   ├── speakers/[jobId]/     # Speaker confirmation (resumes pipeline after S03)
│   ├── settings/             # Channel management only (create/list channels)
│   └── memory/               # Channel Memory (coming soon stub)
└── director/                 # Director dashboard — DO NOT TOUCH
```

### Editor (OpenCut) structure
```
opencut/
├── apps/web/src/
│   ├── app/
│   │   ├── api/
│   │   │   ├── projects/     # CRUD — Supabase editor_projects table
│   │   │   ├── media/        # CRUD + R2 presigned upload — editor_media_assets table
│   │   │   └── sounds/       # Freesound API proxy
│   │   └── editor/[id]/      # Main editor page
│   ├── core/                 # EditorCore singleton — orchestrates all subsystems
│   ├── stores/               # Zustand stores (editor, panel, keybindings, sounds, youtube, reframe)
│   ├── services/
│   │   ├── storage/api-service.ts   # apiStorageService — Supabase projects + R2 media
│   │   └── transcription/           # Deepgram captions via Railway backend
│   ├── hooks/
│   │   └── use-clip-import.ts       # Reads ?clipUrl param, imports clip on first load
│   ├── lib/
│   │   ├── reframe/engine.ts        # Auto-reframe keyframe engine (calls Railway)
│   │   └── supabase/                # client.ts + server.ts
│   └── types/                # TProject, MediaAsset, timeline types
└── packages/
    ├── env/src/web.ts        # Shared zod env schema (validated at startup)
    └── ui/                   # Shared Radix UI components
```

### EditorCore pattern
`EditorCore` is a singleton managing all editor subsystems accessed via `useEditor()`:
- `editor.project` — load/save/settings, writes to Supabase via `apiStorageService`
- `editor.media` — asset management; generates client-side UUID before upload
- `editor.timeline` — tracks, elements, keyframes
- `editor.history` — undo/redo

Media assets are stored in Supabase `editor_media_assets` and uploaded directly to R2 via presigned PUT URLs. The client UUID must flow all the way to the DB — any mismatch breaks timeline references on reload.

### Key connections
- Prognot Frontend calls backend via `NEXT_PUBLIC_API_URL`; `next.config.js` rewrites `/api/backend/:path*` → backend URL
- Editor API routes (`/api/projects`, `/api/media`) are Next.js route handlers with Supabase SSR auth
- Editor calls Railway backend (`NEXT_PUBLIC_PROGNOT_API_URL`) for reframe and captions — **must include** `Authorization: Bearer {supabase_token}`
- Clip import: Prognot dashboard → editor via `?clipUrl=&clipTitle=&clipJobId=` params → `useClipImport` hook fetches via `/proxy/clip` with Bearer token
- Auth: Supabase SSR middleware protects routes in both `frontend/middleware.ts` and `opencut/apps/web/src/middleware.ts`

### Frontend design system
Design language is Figma-derived: pure black backgrounds, no purple, no glassmorphism.

| Token | Value | Usage |
|-------|-------|-------|
| Background | `#000000` | Page bg |
| Surface | `#0a0a0a` | Cards |
| Border | `#1a1a1a` | Default borders |
| Border hover | `#404040` | Focus/hover borders |
| Text | `#ffffff` | Primary |
| Text secondary | `#a3a3a3` | Labels |
| Text muted | `#737373` | Descriptions |
| Text faint | `#525252` | Placeholders |

- Primary button: `bg-white text-black hover:bg-[#e5e5e5]`
- Input: `bg-black border border-[#262626] focus:border-[#404040]`
- Active nav item: `bg-[#1a1a1a] text-white border-l-2 border-white -ml-[2px] pl-[14px]`
- Loading spinner: `border-[#262626] border-t-white` (never purple)
- No Framer Motion on main dashboard pages — plain Tailwind transitions only

### Pipeline flow
```
POST /jobs → background task → run_pipeline(job_id)
  S01-S07 run sequentially on Railway CPU (no user pause after S03 —
  speaker map is auto-assigned and stored with speaker_confirmed=True)
  ── orchestrator dispatches to Modal after S07 ──
  S08-S10 run in a single Modal call (process_clips); CPU fallback on Modal failure
  → Clips saved to R2, metadata to Supabase
```
Pipeline state passed between steps: `transcript_data`, `speaker_data`, `labeled_transcript`, `channel_dna`, `candidates`, `evaluated_clips`, `cut_results`.

Note: `frontend/app/dashboard/speakers/[jobId]/` exists as a manual-review UI but is **not** wired into the orchestrator loop — the pipeline currently does not wait for it.

### Supabase tables (key ones)
`jobs`, `clips`, `transcripts`, `channels`, `director_events`, `director_analyses`, `director_memories`, `viral_library`, `editor_projects`, `editor_media_assets`, `video_uploads` (direct-to-R2 browser uploads), `person_voices` (voice fingerprints, vector(192)), `source_videos` + `show_registry` (UK talk-show sourcing catalog)

### Voice Library (`backend/app/api/routes/voice_library.py` + Modal)
Shared library of reference voice fingerprints (hosts + recurring guests). One clean audio sample per person → ECAPA-TDNN (SpeechBrain `spkrec-ecapa-voxceleb`, VoxCeleb1-O EER 0.80%) → **192-dim vector** stored in `person_voices`.

- **Route prefix**: `/voice-library` — `GET /` (list), `POST /` (multipart audio + name), `DELETE /{id}`. Max upload 25 MB, allowed ext: wav, mp3, m4a, flac, ogg, webm, mp4.
- **Storage**: audio uploaded to R2 under `voice-library/<uuid>.<ext>`, public URL written to `person_voices.audio_path`.
- **Embedding**: computed via Modal `compute_voice_embedding` (A10G, 300 s timeout). FFmpeg-resamples to 16 kHz mono WAV inside Modal, then ECAPA `.encode_batch()`. Model pre-downloaded to `/app/models/ecapa` at image build — **do not** re-download per call.
- **Frontend**: `frontend/app/dashboard/voice-library/page.tsx` + sidebar nav entry (`AudioLines` icon).
- **Dimension guard**: route asserts `len(embedding) == 192`. DB column is `vector(192)`. Legacy commit messages mention "256-dim WeSpeaker ResNet293" — ignore, actual deploy is 192-dim ECAPA.
- **S03 integration**: not wired yet (2026-04-30). Plan: extract representative 5-10 s segment per Deepgram cluster → embed via Modal → cosine-match against `person_voices` (`1 - (a <=> b)` pgvector) → assign name if best score > threshold, else fall back to existing Gemini guest-name heuristic.

### UK Talk-show Sourcing (`backend/app/content_finder/sourcing/`)
3-platform pipeline for sourcing high-quality UK talk-show episodes (Graham Norton, HIGNFY, etc.) as 1080p MP4s — YouTube copies are cropped/compressed, iPlayer is geofenced + DRM.

- **BBC Programmes API** (`bbc_client.py`, `bbc_scraper.py`): catalog-only (pid, `synopsis_long`, first_broadcast, thumbnail). Hit through residential UK proxy (`BBC_PROXY_URL`) because endpoints are UK-geofenced. `/credits.json` endpoint returns 404 across the catalog — guests must be parsed from synopsis.
- **Guest parser** (`guest_parser.py`): Gemini Flash extracts `{host, team_captains, guests, musical_act}` from `synopsis_long`. VERBATIM guard — every returned name must appear literally in the synopsis (zero hallucinations). TVmaze cross-check when `tvmaze_episode_id` is known. Writes `source_videos.guests` jsonb + `guests_source` + `metadata_confidence`.
- **NZBgeek matcher** (`nzb_matcher.py`): Newznab `tvsearch` query (`q=show&season=N&ep=N&o=json`). **Keep ONLY 1080p / 2160p** (720p breaks reframe/captions visually, verified). Among survivors > 300 MB, pick largest (bigger = higher bitrate). Env: `NZBGEEK_API_KEY`, `NZBGEEK_API_URL` (default `https://api.nzbgeek.info/api`).
- **Newshosting + SABnzbd**: paid Usenet provider consumed by self-hosted SABnzbd. Env: `SABNZBD_URL` (default `http://127.0.0.1:8080`), `SABNZBD_API_KEY`. SABnzbd handles the actual Usenet fetch + par2 repair + unrar; backend just queues the NZB returned by NZBgeek and polls completion.

Current state (2026-04-30): `BBC_PROXY_URL` set in `.env`. `NZBGEEK_API_KEY` / `SABNZBD_API_KEY` declared in `config.py` but **not yet written to `.env`**. nzb_matcher + SABnzbd enqueue loop not yet wired to a scheduler. Sourced MP4s will flow into `source_videos` and can then be passed through S01–S10 like any upload, with Voice Library providing speaker-name enrichment.

### Reframe V5 (`backend/app/reframe/`)
14-file pipeline that converts 16:9 → 9:16. Entry: `run_reframe()` in `pipeline.py`; dispatches to one of two modes:

- **Podcast** (default): 12-step flow — video probe → shot detection (FFmpeg scene filter) → face tracking (YOLOv8l-face) → Gemini director (`gemini-2.5-pro`, multi-modal, full video + diarization + shot data + face summary → DirectorPlan: subjects + focus directives) → focus resolver → path solver (AutoFlip kinematic) → keyframe emitter → `render.py::render_podcast_reframe` (single-pass FFmpeg continuous crop expression, outputs MP4). Fallback on Gemini failure: diarization-only plan.
- **Gaming**: `gaming_pipeline.py` — detects webcam overlay via standard YOLO + custom `prognot-webcam.pt` model, renders vstack (1080×640 webcam top + 1080×1280 game bottom). No Gemini, no diarization.

Key files: `pipeline.py` (orchestrator), `render.py` (MP4 renderer), `gaming_pipeline.py`, `face_tracker.py` (YOLO loader), `gemini_director.py`, `shot_detector.py`, `focus_resolver.py`, `path_solver.py`, `keyframe_emitter.py`, `debug_overlay.py`, `debug_analyzer.py`, `config.py`, `types.py`.

YOLO model: `yolov8l-face.pt` (large face-specific). Loader probes `/root/yolov8l-face.pt` → `/app/models/yolov8l-face.pt` → HuggingFace fallback download. `settings.YOLOV8_MODEL_PATH` in `config.py` currently defaults to `yolov8n-pose.pt` but the reframe face tracker does not read that env var — it hardcodes the `yolov8l-face.pt` search paths.

### Captions (`backend/app/captions/`)
`renderer.py` (dispatcher + legacy ASS path), `renderer_pillow.py` (Pillow path), `core.py` (Deepgram transcription), `watermark.py` (per-channel mark), `v2/` and `v3/` (frame-based engines), `assets/` (fonts + watermark PNGs), `finalizer.py`, `davinci_fingerprint.py`.

Entry: `render_captions(video_path, output_path, words, segments, template_key)` in `renderer.py`, which dispatches in this order: V3 → V2 → Pillow (`clean`) → legacy ASS.

**Only three template keys are reachable from the product.** They are listed in the hardcoded `CAPTION_TEMPLATES` array in `frontend/app/dashboard/page.tsx` (~line 80), which is what populates the caption picker on the job-start form:

| Key | Engine | Used by |
|---|---|---|
| `capcut_word_highlight_ii` | V2 | OtherSide Cast — **default** |
| `yellow_center` | V3 | TheYellow Cast |
| `clean` | Pillow | legacy |

A template that is not in that array cannot be requested by any job. Adding a backend template is therefore two edits, not one.

- **V2 / V3 (frame-based)**: render a transparent RGBA frame per video frame with Pillow, pipe to a qtrle `.mov` overlay, then composite onto the source in **one** FFmpeg pass. Karaoke: active word recoloured and pop-scaled around its own centre.
- **V3 is a deliberate fork of V2**, copied verbatim then rebuilt — V2 drives a live monetised channel and must not move when V3 is tuned. Differences: Anton 70px (vs Montserrat Bold 76px), no stroke (shadow alone), single line centred at `height/2`, pages packed by a 24-character budget rather than a fixed word count, overflow shrinks the page instead of wrapping.
- **Pillow path** (`clean` only): one transparent PNG per subtitle group, composited via FFmpeg `overlay` filters. `MAX_OVERLAYS_PER_PASS = 8` → multi-pass encode when a clip has many overlays.
- **Legacy ASS path**: `TEMPLATE_CONFIGS` in `renderer.py` still holds 8 configs (`clean`, `hormozi`, `outline`, `pill`, `neon`, `cinematic`, `bold_pop`, `fire`). Seven of them are **dead** — reachable only by hand-posting a key that no UI offers. Do not cite this list as "the available templates".

**Watermark** (`watermark.py`): a full-frame RGBA PNG composited into the V2/V3 overlay before the caption layer, so it costs no extra encode and persists through frames with no caption. The Pillow and ASS paths get no watermark.

**The watermark is owned by the channel, never by the caption template.** The key lives in `channels.watermark_r2_key` (R2 object key, nullable), S10 resolves it from its `channel_id`, downloads it once per job, and hands the local path to the renderer. The renderers do no lookup — they burn the path they are given or nothing — which is what keeps them from ever picking a mark for a channel they know nothing about.

- **NULL is the default and the safe direction.** A channel is marked only when someone deliberately sets the key. Every failure path in the resolver (no row, no key, DB unreachable, bad download) returns None and produces an unmarked clip.
- **Never key it off the template.** A template is a style and the default one is shared with client accounts; an earlier version did this and stamped our OtherSide Cast mark onto client videos.
- Assets are in R2 under `watermarks/`, not bundled in the repo — a bundled asset would make every new channel require a `modal deploy`.
- To mark a new channel: upload the PNG to R2, then `update channels set watermark_r2_key = '...' where id = '...'`. No code change, no deploy.

**Template selection is NOT read from channel DNA.** `caption_template` is a form field on `POST /jobs`, stored on the `jobs` row, read by the orchestrator (defaults to `clean`), and passed to S10. The docstring claiming otherwise was stale and has been corrected.

Word timestamps in S10 are produced by a **fresh** Deepgram Nova-3 call on the reframed clip (`captions/core.py::transcribe_video`) — S02's word list is NOT reused. This is intentional: the reframed clip duration may differ from the source cut window, and the fresh call re-aligns timestamps on the final rendered audio. The model must stay in sync with S02 (`services/deepgram_client.py`) — the words this call returns are burned into the video, so a weaker model here produces captions that contradict the transcript the pipeline already has. This step ran on Nova-2 until 2026-08-02, which is how a clip whose source transcript read "Eddie's old" shipped with a caption reading "it is old".

---

## PIPELINE STRUCTURE (V4 — 10 Steps)
```
S01 Audio Extract (FFmpeg, ffprobe validation)              — Railway CPU
S02 Transcribe (Deepgram Nova-3, keyterm prompting)         — Railway CPU
S03 Speaker ID (Deepgram diarization + Gemini Flash
    guest-name heuristic; auto-assigns, does NOT pause)     — Railway CPU
S04 Labeled Transcript (pure string formatting, no API)     — Railway CPU
S05 Unified Discovery (Claude Opus 4.7, TEXT-only —
    labeled transcript + channel DNA → clip candidates)     — Railway CPU
S06 Batch Evaluation (Claude — CLAUDE_MODEL env var,
    scores S05 candidates in batches of 4, dedup >50%)      — Railway CPU
S07 Precision Cut (word-boundary snap, breath buffers,
    math-only, no encode)                                   — Railway CPU
── orchestrator dispatches to Modal after S07 ──
S08 Export (FFmpeg cut+encode, ThreadPool×3, R2 upload,
    Supabase insert)                                        — Modal A10G GPU
S09 Reframe V5 (podcast: YOLOv8l-face + Gemini director →
    keyframes → single-pass crop expression; gaming: YOLO
    webcam detect → vstack), ThreadPool×2                   — Modal A10G GPU
S10 Captions (fresh Deepgram Nova-3 transcription of the
    reframed clip → V2/V3 frame overlay + channel watermark,
    one FFmpeg pass)                                        — Modal A10G GPU
```
S08+S09+S10 run as a single Modal function call (`process_clips` in `modal_app.py`).
CPU fallback: if Modal dispatch fails, orchestrator runs S08–S10 locally on Railway CPU.

### Hook Voiceover System (Reused Content Protection)
**Purpose:** 5-7 second TTS hook at clip start to protect against YouTube "reused content" YPP rejection.

**How it works:**
1. S07 precision cut starts 5-7s earlier than the clip's actual moment
2. Claude generates a 1-sentence hook based on clip content (niche-specific tone)
3. Google Cloud TTS synthesizes the hook (fixed voice profile per channel)
4. Pipeline: first 5-7s original audio MUTED → TTS hook overlay → then normal clip continues

**Why:** YouTube reused content = channel-level YPP rejection by human reviewers. Adding narration (even 5-7s) signals "original commentary" = strongest scalable protection. Inspired by JokeWRLD (753K subs) which uses same technique.

**Status:** Concept approved (2026-05-05). Not yet implemented. First test: Unhinged Pods channel.

**TTS Provider:** Google Cloud TTS or Vertex AI-native TTS only. ElevenLabs as backup.

**Per-channel voice:** Each channel gets its own fixed voice profile for brand consistency.

### Pipeline prompts (backend/app/pipeline/prompts/)
| File | Used by | Model | Purpose |
|------|---------|-------|---------|
| `unified_discovery.py` | S05 | Claude (`CLAUDE_MODEL`) | Select clip candidates from labeled transcript + channel DNA |
| `batch_evaluation.py` | S06 | Claude (`CLAUDE_MODEL`) | Score hook quality, retention, loop potential with channel rules |
| `channel_dna.py` | onboarding / reference_analyzer | Gemini Flash | Extract patterns + tone + do/don't lists from successful reference clips |
| `clip_summary.py` | onboarding + post-pipeline feedback | Gemini Flash | Generate RAG-searchable summary of what made a clip work |
| `failure_analysis.py` | feedback_processor (post-pipeline) | Gemini Flash | Root-cause analysis on underperforming clips |
| `guest_research.py` | *not currently wired* | — | Would research guest background for clip-worthiness signals |

---

## ABSOLUTE RULES

### Model usage
| Step / Module | Model | Config key |
|---------------|-------|------------|
| S02 Transcribe | Deepgram **Nova-3** | hardcoded in `services/deepgram_client.py` |
| S03 Speaker guest-name heuristic | `gemini-2.5-flash` | `settings.GEMINI_MODEL_FLASH` |
| S05 Unified Discovery (TEXT transcript, NOT video) | **Claude** `us.anthropic.claude-opus-4-6-v1` (AWS Bedrock) | `settings.CLAUDE_MODEL` |
| S06 Batch Evaluation | **Claude** (same `CLAUDE_MODEL`) | `settings.CLAUDE_MODEL` |
| S09 Reframe — director | `gemini-2.5-pro` (multimodal video + context) | `settings.GEMINI_MODEL_PRO` |
| S10 Captions — transcription | Deepgram **Nova-3** (fresh call per clip) | hardcoded in `captions/core.py` |
| Director agent (tool calling) | `gemini-2.5-pro` | `settings.GEMINI_MODEL_PRO` |
| Director chat (simple queries) | `gemini-2.5-flash` | `settings.GEMINI_MODEL_FLASH` |
| Onboarding DNA + clip summary + failure analysis | `gemini-2.5-flash` | `settings.GEMINI_MODEL_FLASH` |
| Embeddings (vector(768)) | Gemini `text-embedding-004` | via `services/gemini_client.py` |

- Defaults in `config.py`: `CLAUDE_MODEL = "us.anthropic.claude-opus-4-6-v1"` (AWS Bedrock, single provider — Azure Foundry removed), `GEMINI_MODEL_PRO = "gemini-2.5-pro"`, `GEMINI_MODEL_FLASH = "gemini-3.5-flash"`, `GEMINI_MODEL_VIDEO = "gemini-3.5-flash"` (kept for future use)
- Override any model via env var without code changes
- S05 & S06 use `app/services/claude_client.py` → `call_claude()` (Anthropic SDK, requires `ANTHROPIC_API_KEY`)
- S05 receives `video_path` / `audio_path` parameters but does NOT use them — it's pure text-in-text-out on the labeled transcript
- Never change models without being asked

### No GPU libraries in Railway — ever
Railway has no GPU. These will crash the Railway build:
- PyTorch, TensorFlow, transformers, WhisperX (local), MediaPipe
- Any local AI model
GPU libraries (PyTorch, ultralytics) are only allowed in `modal_app.py` and `gpu-service/`.

### No Turkish in code
- Variable names, function names, comments, prompts, string literals → English only
- Exception: user-facing UI text in frontend

### Supabase connection
- Port MUST be `6543` (Connection Pooler), never `5432`
- `5432` is unreachable from Railway/Docker

### FFmpeg encoding
- S07 (precision cut): `-c copy` (lossless stream copy, fast)
- S08 (export, Modal GPU): `h264_nvenc -preset p4 -rc vbr -cq 18 -c:a aac -b:a 320k`
- S08 (export, Railway CPU fallback): `libx264 -preset slow -crf 18 -c:a aac -b:a 320k`
- Codec controlled by env vars: `FFMPEG_VIDEO_CODEC`, `FFMPEG_ENCODE_PRESET`, `FFMPEG_HWACCEL`
- Only ONE re-encode per clip (in S08). S07 does lossless copy.

### Modal deploy rule
After ANY change to these files → `modal deploy modal_app.py` immediately:
- `backend/app/pipeline/steps/s08_export.py`
- `backend/app/pipeline/steps/s09_reframe.py`
- `backend/app/pipeline/steps/s10_captions.py`
- `backend/app/captions/` (any file)
- `backend/app/reframe/` (any file)
- `modal_app.py` itself

### pgvector embedding size
- clips.clip_summary_embedding → `vector(768)` — do NOT change
- reference_clips.clip_summary_embedding → `vector(768)`
- person_voices.embedding → `vector(192)` — ECAPA-TDNN output; do NOT change. Legacy docs mentioning 256-dim WeSpeaker are stale.

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

### Editor calls to Railway backend
Any fetch in `opencut/apps/web/` targeting `NEXT_PUBLIC_PROGNOT_API_URL` must include a Bearer token:
```typescript
const supabase = createClient();
const { data } = await supabase.auth.getSession();
const token = data?.session?.access_token;
// then:
headers: token ? { Authorization: `Bearer ${token}` } : {}
```

### Editor media asset IDs
The editor generates a UUID client-side for each media asset. This UUID must be sent as `id` in the POST body to `/api/media` so Supabase uses it instead of generating a new one. A mismatch breaks all timeline element references after a page reload.

---

## DO NOT TOUCH
- `frontend/app/director/` — Admin panel, completely separate design system, never apply dashboard redesign here
- `backend/reframer.py` — Module 2, suspended indefinitely
- `frontend/next.config.js` — proxy config, leave as-is
- `backend/channels/` structure — channel isolation system
- `backend/app/memory/` — Feedback system, suspended indefinitely
- `backend/app/pipeline/steps/s01_audio_extract.py` through `s04_labeled_transcript.py` — these are stable

---

## ENVIRONMENT VARIABLES

### Railway
```
GCP_PROJECT=
GCP_LOCATION=
GCP_CREDENTIALS_JSON=
GCS_BUCKET_NAME=
DEEPGRAM_API_KEY=
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
DATABASE_URL=           # port 6543 mandatory
FRONTEND_URL=
MAX_UPLOAD_BYTES=       # optional, default 5 GB (5368709120). Presigned PUT + /jobs limit.
# UK talk-show sourcing (optional until sourcing pipeline is wired to a scheduler):
BBC_PROXY_URL=          # residential UK proxy, required for BBC Programmes API
NZBGEEK_API_KEY=        # Newznab API key for NZBgeek
NZBGEEK_API_URL=        # default https://api.nzbgeek.info/api
SABNZBD_URL=            # default http://127.0.0.1:8080
SABNZBD_API_KEY=
```

### Vercel — Prognot Frontend
```
NEXT_PUBLIC_API_URL=    # Railway backend URL
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
```

### Vercel — Editor
```
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
NEXT_PUBLIC_PROGNOT_API_URL=   # Railway backend (reframe + captions)
NEXT_PUBLIC_R2_PUBLIC_URL=     # https://pub-xxxxx.r2.dev
CLOUDFLARE_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=
FREESOUND_API_KEY=             # freesound.org API key (real key required — placeholder causes 401)
```

---

## LERN APP — CONTENT CREATION RULES

### Language & Approach
- **All UI and content in German** (simple A1-A2 level, NOT C1)
- Turkish only behind a "çeviri" toggle button — never visible by default
- Teach through LOGIC and PATTERNS, not memorization
- Rich examples, comparisons, pattern recognition

### Öğren (Learn) Page
- Block types: `heading`, `text`, `example`, `table`, `conjugation`, `tip`, `rule`, `translate`
- Every text/example/tip/rule block gets a `translation` field (Turkish, shown via toggle)
- Flow: introduce concept → give rule → show with examples → exceptions/tips
- Must be comprehensive — not brief, explain deeply with many examples

### Üben (Practice) Page — Difficulty Progression
- Questions 1-5: Easy (simple fill_blank with clear hint)
- Questions 6-10: Easy-Medium (fill_blank without hint, W-Wort blanks)
- Questions 11-15: Medium (harder fill_blank, basic translate)
- Questions 16-20: Hard (full sentence translate, tricky choose questions)
- Choose options must be CLOSE to each other (same category)
- Every exercise gets a `hint` field (in German)

### Test Page
- Different questions from Üben but same topics
- Mixed difficulty
- Mix of fill_blank + choose + translate
- Points: easy=1, translation=2

### Karten (Cards) — Smart Distractors
- Every card MUST have `distractors` array (exactly 3 items)
- Distractors must be from the SAME CATEGORY:
  - Verb conjugation → other person conjugations (komme/kommst/kommt/kommen)
  - W-word → other W-words (Wo/Woher/Wie/Welche/Was)
  - sein → other sein forms (bin/bist/ist/sind)
  - Greetings → other greetings
- NEVER put absurd distractors from unrelated categories
- Card front: German question format (fill blank, choose W-word, etc.)
- Card back: correct answer
- example_sentence: short rule reminder

### Wörter (Vocabulary)
- Fields: word, article (der/die/das), plural, translation (Turkish), example_sentence (German)
- word_type: noun/verb/adjective/adverb/preposition/conjunction/other
- Most frequent words first

### Aufgaben (Tasks)
- Written in German
- task_type: listen/watch/speak/write/review/shadow
- Practical, doable tasks (10 min max)
- Mixed types

### DB Tables
All tables prefixed with `lern_`: `lern_modules`, `lern_topics`, `lern_pages`, `lern_cards` (has `distractors text[]`), `lern_vocabulary`, `lern_tasks`

### Deploy
```bash
cd lern && vercel --prod
```
NOT connected to GitHub auto-deploy. Must deploy manually after changes.
