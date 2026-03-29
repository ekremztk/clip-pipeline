# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## REPO STRUCTURE

This is a **monorepo with two separate web applications**:

| Directory | App | URL | Stack |
|-----------|-----|-----|-------|
| `frontend/` | Prognot Studio (clip pipeline UI) | clip.prognot.com | Next.js 16, npm, Supabase Auth |
| `opencut/apps/web/` | Video Editor | edit.prognot.com | Next.js 16, Bun, Turbopack, Supabase Auth |
| `backend/` | API server | Railway | FastAPI, Python 3.11 |
| `landing/` | Marketing page | prognot.com | Static HTML |

The two frontends are **completely independent** — separate `node_modules`, separate env files, separate deploys.

---

## DEVELOPMENT COMMANDS

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
- Prognot Frontend → Vercel (`frontend/`)
- Editor → Vercel (`opencut/apps/web/`)
- Database → Supabase (PostgreSQL + pgvector)
- Storage → Cloudflare R2 (clip exports + editor media)
- CI/CD → `git push` to main → auto deploy both

---

## ARCHITECTURE

### Backend structure
```
backend/app/
├── main.py              # FastAPI entry, lifespan schedulers, CORS, router mount
├── config.py            # Settings singleton (all env vars)
├── pipeline/
│   ├── orchestrator.py  # State machine: runs S01→S08, handles pause after S03
│   ├── steps/s01-s08    # Individual pipeline steps
│   └── prompts/         # Gemini prompts for S05, S06
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
│   └── utils/           # youtube_api, transcript_fetcher, score_calculator, guest_extractor
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
│   ├── new-job/              # Video upload + trim + pipeline trigger
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
  S01-S03: extract audio, transcribe, speaker ID
  ── PAUSE (status=awaiting_speaker_confirm) ──
  POST /jobs/{id}/confirm-speakers → resumes
  S04-S08: label transcript, discover clips, evaluate, cut, export
  → Clips saved to R2, metadata to Supabase
```
Pipeline state passed between steps: `transcript_data`, `speaker_data`, `labeled_transcript`, `channel_dna`, `candidates`, `evaluated_clips`, `cut_results`.

### Supabase tables (key ones)
`jobs`, `clips`, `transcripts`, `channels`, `director_events`, `director_analyses`, `director_memories`, `viral_library`, `editor_projects`, `editor_media_assets`

---

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

---

## ABSOLUTE RULES

### Model usage
| Step / Module | Model | Config key |
|---------------|-------|------------|
| S05 Unified Discovery (video analysis) | `gemini-2.5-pro` | `settings.GEMINI_MODEL_PRO` |
| S05 channel profile lookup (text only) | `gemini-2.5-flash` | `settings.GEMINI_MODEL_FLASH` |
| S06 Batch Evaluation | **Claude** `claude-sonnet-4-6` | `settings.CLAUDE_MODEL` |
| Director agent (tool calling) | `gemini-2.5-pro` | `settings.GEMINI_MODEL_PRO` |
| Director chat (simple queries) | `gemini-2.5-flash` | `settings.GEMINI_MODEL_FLASH` |
| All other Gemini calls (DNA gen, embeddings, etc.) | `gemini-2.5-flash` | `settings.GEMINI_MODEL_FLASH` |

- Default values live in `config.py`: `GEMINI_MODEL_PRO = "gemini-2.5-pro"`, `GEMINI_MODEL_FLASH = "gemini-2.5-flash"`, `CLAUDE_MODEL = "claude-sonnet-4-6"`
- Override any model via env var without code changes
- S06 uses `app/services/claude_client.py` → `call_claude()` (Anthropic SDK, requires `ANTHROPIC_API_KEY`)
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
GEMINI_API_KEY=
DEEPGRAM_API_KEY=
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
DATABASE_URL=           # port 6543 mandatory
FRONTEND_URL=
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

## KNOWN PITFALLS
| Problem | Fix |
|---------|-----|
| Supabase "Network unreachable" | DATABASE_URL port must be 6543 |
| Gemini JSON parse error | Strip ` ```json ``` ` wrappers, use `re.sub(r'[\x00-\x1f]', '', raw)` |
| Gemini 429 rate limit | Retry: 30s wait × 2, then 60s, then raise |
| Docker build slow | COPY requirements.txt before COPY code |
| Video file not found | Always check `os.path.exists()` before FFmpeg |
| Editor reframe/captions 401 | All Railway calls from editor need `Authorization: Bearer {supabase_token}` |
| Editor media disappears after reload | Pass client `id` to POST /api/media; never let Supabase generate a new UUID |
| Editor project 404 loop | POST /api/projects must receive `id` from client; uses upsert to handle races |
| Vercel 4.5MB body limit | Never proxy large files through Next.js routes; use R2 presigned PUT URLs |
| `npm install` fails in opencut/ | Use `bun install` — opencut uses Bun workspaces, not npm |
