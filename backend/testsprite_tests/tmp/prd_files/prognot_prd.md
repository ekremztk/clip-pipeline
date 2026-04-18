# Prognot Backend — Product Requirements Document

## Overview
Prognot is a viral clip extraction pipeline. It takes a long-form video (podcast/interview), runs it through a 10-step AI pipeline, and produces short-form clips (15–90 seconds) optimized for YouTube Shorts/TikTok/Reels.

The backend is a FastAPI application. Base URL in tests: http://localhost:8000

## Authentication
All endpoints require a Supabase JWT Bearer token in the Authorization header:
`Authorization: Bearer <token>`

**IMPORTANT for testing:** When running tests locally, the server accepts any token that is NOT a real JWT (does not contain exactly 2 dots). Placeholder tokens like `"Bearer dev_token"` or `"Bearer test123"` will be accepted automatically — no real Supabase JWT is needed.

## Core Entities

### Job
- Represents a pipeline run for one video
- States: queued → processing → analyzing → awaiting_speaker_confirm → cutting → completed / failed / partial
- DB fields: id, status, current_step, current_step_number, total_steps, progress_pct, clip_count, video_title, channel_id, user_id

### Clip
- A short-form video extracted from a job
- DB fields: id, job_id, channel_id, start_time, end_time, duration_s, hook_text, content_type, standalone_score, clip_strategy_role, video_landscape_path, video_reframed_path, suggested_title, suggested_description, user_approved (null=pending, true=approved, false=rejected)

### Channel
- Represents a YouTube channel with its DNA configuration
- DB fields: id (slug string, not UUID), display_name, niche, content_format, clip_duration_min, clip_duration_max, channel_vision, channel_dna (JSON), onboarding_status, user_id

## API Endpoints

### Health
```
GET /health
Response 200: { ok: true, version: "2.0.0", environment: "development" }
```

### Channels

#### POST /channels
Creates a new channel.
```
Request body (JSON):
  channel_id: string  — user-defined slug, e.g. "my_podcast" (required)
  display_name: string  — human-readable name (required)
  niche: string (optional)
  content_format: string (optional)
  clip_duration_min: int (optional, default 15)
  clip_duration_max: int (optional, default 50)
  channel_vision: string (optional)

Response 200:
  { created: true, channel_id: "my_podcast" }

Response 422: Missing required fields (channel_id or display_name)
```

#### GET /channels
Returns list of channels for the authenticated user.
```
Response 200: array of channel objects, each with:
  id: string (slug)
  display_name: string
  channel_dna: object or null
  user_id: string
  created_at: string
  ... (other fields)
```

#### GET /channels/{channel_id}
Returns single channel details.
```
Response 200: channel object
Response 404: Channel not found
```

#### PATCH /channels/{channel_id}
Updates channel fields.
```
Request body (JSON): any of { display_name, niche, content_format, clip_duration_min, clip_duration_max, channel_vision, channel_dna, onboarding_status }
Response 200: { updated: true, channel_id: string }
Response 404: Channel not found
```

### Jobs

#### POST /jobs
Creates a new pipeline job. Multipart form data (NOT JSON):
```
Form fields:
  title: string  — video title (REQUIRED, field name is "title" not "video_title")
  channel_id: string  — must be an existing channel id (REQUIRED)
  youtube_url: string  — YouTube URL to download (optional, field name is "youtube_url" not "video_url")
  upload_id: string  — UUID from /jobs/upload-preview (optional)
  guest_name: string (optional)
  trim_start_seconds: float (optional, default 0)
  trim_end_seconds: float (optional)
  clip_duration_min: int (optional)
  clip_duration_max: int (optional)

IMPORTANT: Use requests.post(url, data={...}, headers=headers) NOT json={...}
  
Response 200:
  { job_id: string (UUID), status: "queued", message: "Processing started" }

Response 400: Invalid YouTube URL, or no video source provided
Response 404: Channel not found
Response 422: Missing required fields (title or channel_id)
```

#### GET /jobs/{job_id}
Returns job details.
```
Response 200:
  {
    job: {
      id: string,
      status: string,  — one of: queued, processing, analyzing, awaiting_speaker_confirm, cutting, completed, failed, partial
      current_step: int,
      current_step_number: int,
      total_steps: int,
      progress_pct: int,
      clip_count: int,
      video_title: string,
      channel_id: string,
      ... (other fields)
    },
    clips: array,
    speaker_map: object or null
  }

Response 404: Job not found
```

#### GET /jobs
Returns list of jobs for a channel.
```
Query params:
  channel_id: string (REQUIRED) — returns 422 if missing
  limit: int (optional, default 20)

Response 200: array of job objects, each with: id, status, channel_id, video_title, current_step, progress_pct, clip_count, created_at, ...
Response 422: Missing channel_id
```

#### DELETE /jobs/{job_id}
Deletes a job and its clips.
```
Response 200: { deleted: true, job_id: string }
Response 404: Job not found
```

#### POST /jobs/upload-preview
Uploads a video file and returns upload_id + duration. Uses ffprobe to read duration — requires a real valid MP4, not fake bytes.
```
Form fields:
  file: binary (MP4 video file, field name is "file") — REQUIRED, must be a real valid MP4

IMPORTANT: Generate a real MP4 using ffmpeg before uploading:
  subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:size=64x64:rate=1",
    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
    "-t", "1", "-c:v", "libx264", "-c:a", "aac", output_path], check=True)

Response 200:
  { upload_id: string (UUID), duration_seconds: float }

Response 400: Unsupported file format
```

### Speakers

#### POST /jobs/{job_id}/confirm-speakers
Resumes pipeline after S03 speaker identification. Job must be in awaiting_speaker_confirm state.
```
Request body (JSON):
  {
    "speaker_map": {
      "0": { "role": "host", "name": "Joe" },
      "1": { "role": "guest", "name": "Elon" }
    }
  }

Response 200: { status: "resumed", speaker_map: {...} }
Response 400: Job not in awaiting_speaker_confirm state
Response 404: Job not found
```

### Clips

#### GET /clips
Returns clips for the authenticated user. Filters by channel_id and optionally job_id.
```
Query params:
  channel_id: string (REQUIRED)
  job_id: string (optional)
  limit: int (optional)
  offset: int (optional)

Response 200: array of clip objects (may be empty list if no clips yet)
  NOTE: /clips without channel_id returns 200 with empty list, NOT 422

Each clip object includes: id, job_id, channel_id, start_time, end_time, duration_s, hook_text, content_type, standalone_score, clip_strategy_role, video_landscape_path, video_reframed_path, user_approved, suggested_title, suggested_description
```

#### GET /clips/{clip_id}
Returns a single clip.
```
Response 200: clip object
Response 404: Clip not found
```

#### PATCH /clips/{clip_id}/approve
Marks clip as approved.
```
Response 200: { approved: true, clip_id: string }
```

#### PATCH /clips/{clip_id}/reject
Marks clip as rejected.
```
Response 200: { rejected: true, clip_id: string }
```

#### PATCH /clips/{clip_id}/unset-approval
Resets approval to null.
```
Response 200: { unset: true, clip_id: string }
```

## Pipeline State Machine

```
POST /jobs → background task starts immediately
  S01 (10%): FFmpeg extracts audio
  S02 (20%): Deepgram Nova-3 transcribes
  S03 (30%): Speaker ID → STATUS = awaiting_speaker_confirm
  ← POST /jobs/{id}/confirm-speakers → pipeline resumes
  S04 (40%): Build labeled transcript
  S05 (55%): Gemini discovers clip candidates
  S06 (70%): Claude Opus evaluates candidates
  S07 (80%): Precision cut
  S08 (88%): FFmpeg encode + R2 upload + DB insert
  S09 (94%): YOLO + Gemini reframe 9:16
  S10 (100%): Deepgram captions
  STATUS = completed, clip_count = N
```

## YouTube Download Note
The pipeline uses yt-dlp to download YouTube videos. yt-dlp works fine from the local machine.
However, when running tests from a CI/cloud server, YouTube may block the download IP.
Tests that use youtube_url should be written defensively: if job status goes to "failed" shortly after creation (within 30 seconds), assume YouTube download was blocked and skip the test with a warning rather than hard-failing.

## Data Validation Rules
- clip.standalone_score: integer 0-100 (field name is "standalone_score" not "score")
- clip.user_approved: null (pending), true (approved), false (rejected) — field name is "user_approved" not "is_successful"
- clip.clip_strategy_role: one of "launch", "viral", "engagement", "fan_service"
- channel.id: string slug (NOT a UUID), e.g. "my_podcast_channel"
- job response: nested as { job: {...}, clips: [...], speaker_map: {...} }
- POST /jobs response field: "job_id" (not "id")
- POST /channels response: { created: true, channel_id: string } with HTTP 200 (not 201)
- GET /clips without channel_id: returns 200 with empty list (not 422)
- GET /jobs without channel_id: returns 422

## Test Scenarios

### Scenario 1: Channel CRUD
1. POST /channels with { channel_id: "test_xyz", display_name: "Test" } → 200, created: true
2. GET /channels/{channel_id} → 200, id == "test_xyz"
3. PATCH /channels/{channel_id} with { display_name: "Updated" } → 200, updated: true
4. GET /channels → 200, array includes the channel

### Scenario 2: Job Creation and Status
1. POST /channels → get channel_id
2. POST /jobs with { title: "Test", channel_id, youtube_url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ" }
3. Response: { job_id: UUID, status: "queued" }
4. GET /jobs/{job_id} → { job: { id, status, current_step, progress_pct, clip_count }, clips, speaker_map }
5. GET /jobs?channel_id={channel_id} → array containing the job
6. DELETE /jobs/{job_id} → { deleted: true }
7. GET /jobs/{job_id} → 404

### Scenario 3: Upload Preview
1. Generate a real MP4 file using ffmpeg (lavfi color source, 1 second)
2. POST /jobs/upload-preview with the real MP4 file as "file" field
3. Response: { upload_id: UUID, duration_seconds: float > 0 }

### Scenario 4: Clip Approval (using existing clips)
1. GET /clips?channel_id={existing_channel_id} → get an existing clip
2. PATCH /clips/{clip_id}/approve → { approved: true, clip_id }
3. GET /clips/{clip_id} → user_approved == true
4. PATCH /clips/{clip_id}/reject → { rejected: true }
5. PATCH /clips/{clip_id}/unset-approval → { unset: true }
