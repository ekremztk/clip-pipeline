# Pipeline Architecture & Data Flow Analysis
## S01 → S08 (Strictly No S09/S10)

---

## 0. Orchestrator State Variables

`run_pipeline()` in `orchestrator.py` owns these mutable variables passed between steps:

| Variable | Type | Set by | Read by |
|---|---|---|---|
| `audio_path` | `str` (file path) | S01 | S02, S05 (fallback), S08 cleanup |
| `transcript_data` | `dict` | S02 | S03, S04, S06, S07 |
| `speaker_data` | `dict` | S03 | S04 |
| `labeled_transcript` | `str` | S04 | S05, S06 |
| `channel_dna` | `dict` | Supabase fetch (before S05) | S05, S06 |
| `candidates` | `list[dict]` | S05 | S06 |
| `evaluated_clips` | `list[dict]` | S06 | S07 |
| `cut_results` | `list[dict]` | S07 | S08 |
| `exported_clips` | `list[dict]` | S08 | S09 |

---

## 1. S01 → S02: Audio Extraction to Transcription

### S01 Output
`s01_audio_extract.run(video_path, job_id)` returns a **file path string**:

```
temp_{job_id}.m4a
```

FFmpeg command:
```bash
ffmpeg -y -i {video_path} -vn -c:a aac -b:a 192k -movflags +faststart temp_{job_id}.m4a
```

- Format: M4A container, AAC codec, 192 kbps, `+faststart` for streaming
- No video stream (`-vn`)
- File lives in the working directory (Railway container's `/app` or wherever uvicorn runs)

### Deepgram API Call (inside `deepgram_client.py`)

**HTTP Method:** `POST https://api.deepgram.com/v1/listen`

**Headers:**
```
Authorization: Token {DEEPGRAM_API_KEY}
Content-Type: audio/mp4
```

**Query Parameters:**
```python
{
    "model": "nova-2",
    "diarize": "true",
    "sentiment": "true",
    "punctuate": "true",
    "utterances": "true",
    "words": "true",
    "detect_language": "true",
}
```

**Request body:** Raw binary of the `.m4a` file (read-all-at-once into memory).

**Deepgram Response JSON Structure (simplified):**
```json
{
  "metadata": {
    "duration": 3612.5,
    "channels": 1,
    "models": ["nova-2"],
    "detected_language": "en"
  },
  "results": {
    "channels": [
      {
        "alternatives": [
          {
            "transcript": "full plain text of the audio",
            "confidence": 0.98,
            "words": [
              {
                "word": "hello",
                "punctuated_word": "Hello,",
                "start": 1.42,
                "end": 1.84,
                "confidence": 0.99,
                "speaker": 0,
                "speaker_confidence": 0.95,
                "sentiment": "positive",
                "sentiment_score": 0.82
              }
            ],
            "paragraphs": { ... }
          }
        ]
      }
    ],
    "utterances": [
      {
        "start": 1.42,
        "end": 8.73,
        "transcript": "Hello, welcome to the show.",
        "confidence": 0.97,
        "channel": 0,
        "speaker": 0,
        "sentiment": "positive",
        "sentiment_score": 0.72,
        "words": [ ... ]
      }
    ]
  }
}
```

**Critical word-level fields:**
- `words[].start` — word start in seconds (float, millisecond precision)
- `words[].end` — word end in seconds (float)
- `words[].word` — raw word (no punctuation)
- `words[].punctuated_word` — word with punctuation attached
- `words[].speaker` — integer (0, 1, 2...) — diarization result
- `words[].sentiment_score` — float −1.0 to +1.0

**Utterance-level fields (used for speaker ID and labeled transcript):**
- `utterances[].speaker` — integer speaker ID
- `utterances[].start`, `utterances[].end` — segment boundaries
- `utterances[].transcript` — text of the utterance
- `utterances[].sentiment`, `utterances[].sentiment_score`

### S02 Output Dict

`s02_transcribe.run()` returns:

```python
{
    "transcript": str,        # channels[0].alternatives[0].transcript — full plain text
    "words": list[dict],      # channels[0].alternatives[0].words — per-word objects
    "utterances": list[dict], # results.utterances — speaker-segmented blocks
    "duration": float,        # metadata.duration — total audio length in seconds
    "raw_response": dict      # complete Deepgram JSON response
}
```

**Note:** The `words` list is extracted from `channels[0].alternatives[0].words`, **not** from utterances. The utterance-level `words` array exists in Deepgram's response but is not what gets stored here — the channel-level words are used.

The orchestrator also saves `words` to the `transcripts` table:
```python
supabase.table("transcripts").upsert({
    "job_id": job_id,
    "raw_response": transcript_data.get("raw_response", {}),
    "word_timestamps": words,       # ← this is transcript_data["words"]
    "speaker_map": speaker_data["predicted_map"],
    ...
})
```

---

## 2. S02 → S03 → S04: Data Evolution

### S03 Input / Logic

`s03_speaker_id.run(transcript_data, job_id, video_title)` reads:

```python
utterances = transcript_data.get("utterances", [])
```

For each utterance: reads `utterance.get("speaker", "UNKNOWN")` (integer), `utterance.get("start")`, `utterance.get("end")`. Builds `speaker_stats`:

```python
speaker_stats = {
    0: {"duration": 142.5, "utterance_count": 47},
    1: {"duration": 89.3,  "utterance_count": 31},
}
```

**Heuristic:** Speaker with the **longest total speaking duration** is assigned `role: "guest"`. Second-longest is `role: "host"`. All others are `role: "unknown"`.

A secondary Gemini Flash call tries to extract a guest name from `video_title`. The raw speaker integer becomes the key (not formatted as `SPEAKER_X`).

### S03 Output Dict

```python
{
    "speaker_stats": {
        0: {"duration": 142.5, "utterance_count": 47},
        1: {"duration": 89.3,  "utterance_count": 31},
    },
    "predicted_map": {
        0: {"role": "guest", "name": "Elon Musk"},   # raw integer key
        1: {"role": "host",  "name": None},
    },
    "needs_confirmation": False
}
```

**Key detail:** The `predicted_map` keys are **raw integer speaker IDs** (e.g., `0`, `1`), not the string `"SPEAKER_0"`.

### S04 Input / Logic

`s04_labeled_transcript.run(transcript_data, predicted_map, guest_name)` receives:
- `transcript_data` — same S02 dict
- `predicted_map` — `speaker_data["predicted_map"]` (raw int keys from S03)

For each utterance, it reads `utt.get("speaker", "")` as `speaker_id`, then:

```python
speaker_id = str(utt.get("speaker", ""))
if "SPEAKER_" not in speaker_id:
    speaker_id = f"SPEAKER_{speaker_id}"  # converts "0" → "SPEAKER_0"
```

Then looks up: `speaker_map.get("SPEAKER_0", {})`.

**Mismatch bug:** S03 stores keys as raw integers (`0`, `1`), but S04 constructs the lookup key as `"SPEAKER_0"`. The `speaker_map.get("SPEAKER_0", {})` call will **never find a match** because S03 stored `0` (int), not `"SPEAKER_0"` (string).

The result: `speaker_info` is always `{}`, `role` defaults to `"UNKNOWN"`, `name` defaults to `""`. Every utterance is labeled `UNKNOWN` regardless of actual speaker.

### S04 Output Format

`s04_labeled_transcript.run()` returns a **single string** (not a dict). Each utterance becomes one line:

```
[MM:SS.s] ROLE (Name): [sentiment:X.XX] text
```

Examples:
```
[00:01.4] UNKNOWN: Hello, welcome to the show.
[00:08.9] UNKNOWN: [sentiment:0.72] Yeah, absolutely fascinating.
[45:12.3] UNKNOWN: [sentiment:-0.45] I completely disagree with that.
```

Sentiment annotation only appears if `abs(score) > 0.3`. The timestamp format is `[{minutes:02d}:{seconds:04.1f}]` — minutes as 2 digits, seconds as 4 chars with 1 decimal (e.g., `02.3` → formatted as `02.3`, but `%04.1f` of 2.3 = ` 2.3` — padded with space, not zero).

This string is `labeled_transcript`. It is passed to **S05** and **S06**.

---

## 3. S05: Unified Discovery

### Data Injected Into Prompt

The PROMPT template has 7 placeholders, replaced via `.replace()`:

| Placeholder | Source | Type |
|---|---|---|
| `VIDEO_DURATION_PLACEHOLDER` | `transcript_data["duration"]` → `str(int(video_duration_s))` | String of integer seconds |
| `MAX_CANDIDATES_PLACEHOLDER` | `_calculate_max_candidates(video_duration_s)` | "15", "25", "35", or "45" based on duration |
| `CHANNEL_CONTEXT_PLACEHOLDER` | `build_channel_context(channel_dna, channel_id)` | Natural language string from DNA fields |
| `GUEST_PROFILE_PLACEHOLDER` | `_get_guest_profile(guest_name)` | Natural language from Supabase cache or Gemini Flash |
| `LABELED_TRANSCRIPT_PLACEHOLDER` | `labeled_transcript` from S04 | The full `[MM:SS.s] ROLE: text` string |
| `MIN_DURATION_PLACEHOLDER` | Job-level override > `channel_dna["duration_range"]["min"]` > `settings.MIN_CLIP_DURATION` | Integer seconds as string |
| `MAX_DURATION_PLACEHOLDER` | Job-level override > `channel_dna["duration_range"]["max"]` > `settings.MAX_CLIP_DURATION` | Integer seconds as string |

The prompt is sent via `analyze_video(video_path, prompt, json_mode=True)` using `gemini-2.5-pro` with the full video file uploaded.

### Expected JSON Schema from Gemini (S05)

```json
[
  {
    "candidate_id": 1,
    "timestamp": "12:34",
    "recommended_start": 754.2,
    "recommended_end": 812.8,
    "estimated_duration": 58.6,
    "hook_text": "Exact first sentence the viewer will hear",
    "reason": "Why this moment has viral potential for THIS channel",
    "primary_signal": "visual",
    "content_type": "revelation",
    "needs_context": false
  }
]
```

**Accepted `primary_signal` values:** `"transcript"`, `"visual"`, `"audio_energy"`, `"humor"`, `"multi"`

**Parse path:** `_parse_gemini_json(raw_text)` → strips ` ```json ``` ` wrappers, strips control chars (`re.sub(r'[\x00-\x1f\x7f]', '', ...)`), `json.loads()`. If result is a dict with a `"candidates"` key, extracts that list.

### S05 Validation & Output

`_validate_candidates()` filters:
- Missing `candidate_id` key → dropped
- `start >= video_duration_s` → dropped
- `end <= start` → dropped
- `(end - start) < min_duration` → dropped

**S05 returns:** `list[dict]` of validated candidate objects, each with the 9 fields from the schema above. This becomes `candidates` in the orchestrator.

**Fallback chain** if primary video analysis returns empty:
1. `analyze_audio(audio_path, prompt)` → same parse → same validation
2. `generate_json(prompt)` (text-only) → same parse

---

## 4. S06: Batch Evaluation

### How S06 Receives S05 Data

`s06_batch_evaluation.run(candidates, labeled_transcript, transcript_data, ...)` — `candidates` is the direct S05 output list. S06 reads these keys from each candidate:

```python
{
    "candidate_id": item.get("candidate_id"),       # int
    "timestamp":    item.get("timestamp", "00:00"), # "MM:SS" string
    "hook_text":    item.get("hook_text", ""),
    "reason":       item.get("reason", ""),
    "primary_signal": item.get("primary_signal", ""),
    "content_type": item.get("content_type", ""),
    "recommended_start": item.get("recommended_start", 0),  # float seconds
    "recommended_end":   item.get("recommended_end", 0),    # float seconds
}
```

S05 fields `estimated_duration` and `needs_context` are **silently ignored** by S06 — never read.

### Pre-Claude Enrichment

For each candidate, S06 builds two data sources before calling Claude:

**1. Transcript segments** (`_extract_context_segments`):
Reads `transcript_data["words"]` and builds three text blocks from word-level timestamps:
- `pre_context`: words where `pre_start <= word.start < rec_start` (20s before clip)
- `clip_segment`: words where `rec_start <= word.start <= rec_end`
- `post_context`: words where `rec_end < word.start <= post_end` (20s after clip)

Each block is formatted by `words_to_timestamped_text()`: adds a `[MM:SS.ss]` timestamp marker every 10 words (or when 2+ seconds have passed), then joins words with spaces. Format: `[01:23.45] word1 word2 word3 ...`

**2. Video frames** (`_extract_frames`, `_extract_context_frames`):
Uses FFmpeg subprocess per frame, stored as base64-encoded JPEG strings.

Clip frames (4 per candidate):
- `hook`: `rec_start + 0.5s`
- `early`: `rec_start + duration * 0.25`
- `middle`: `rec_start + duration * 0.5`
- `final`: `rec_start + duration * 0.90`

Context frames (2 per candidate):
- `pre_frame`: `rec_start - 10.0s`
- `post_frame`: `rec_end + 10.0s`

### Claude Call

Batches of 4 candidates. Content array sent to `call_claude()`:
- `SYSTEM_PROMPT` → role/rules for the model
- Text block with all 4 candidates' metadata + 3-part transcript sections
- Interleaved image blocks (pre_frame, 4 clip frames, post_frame per candidate)
- Final instruction: `"Return ONLY a valid JSON array — no markdown, no extra text."`

Model: `claude-sonnet-4-6` via `app/services/claude_client.py`.

**Missing candidates retry:** If Claude returns fewer candidate IDs than sent, each missing candidate is retried as a solo call (`_evaluate_single_with_claude`).

### Expected JSON Schema from Claude (S06)

```json
[
  {
    "candidate_id": 1,
    "recommended_start": 752.0,
    "recommended_end": 809.5,
    "hook_text": "The exact first sentence the viewer will hear",
    "score": 84,
    "quality_verdict": "pass",
    "quality_notes": "",
    "content_type": "revelation",
    "clip_strategy_role": "viral",
    "posting_order": 2,
    "suggested_title": "Title under 60 chars",
    "suggested_description": "2-3 sentences. #hashtag1 #hashtag2 #hashtag3"
  }
]
```

**Note:** Claude's schema does NOT carry forward `reason`, `primary_signal`, `estimated_duration`, `needs_context`, or `timestamp` from S05. These are dropped permanently after S06.

### S06 Quality Gate & Output

**Verdict filter:**
```python
verdict in ("pass", "fixable")  # "omit" candidates were never in output; this is a safety net
```

**Boundary clamping:**
- `clip_end = min(clip_end, video_duration)` — prevents end past EOF
- If clamped duration < `min_duration` → entire clip dropped

**Sorting:** By `posting_order`, then reassigned sequentially (1, 2, 3...).

**Known bug (line 603):** `len(failed_log)` — `failed_log` is never defined in the function scope. This line is inside a `try/except Exception: pass` block, so the `NameError` is silently swallowed. The director event is never actually emitted, but the pipeline continues unaffected.

**S06 output:** `list[dict]` — only pass/fixable clips. Each dict carries all 12 Claude-output fields. This becomes `evaluated_clips`.

---

## 5. S07: Precision Cut (Math Only)

### Trigger Condition

`if not evaluated_clips: skip` — runs whenever S06 produces ≥1 clip. S07 does NOT do any cutting — it only calculates and stores `final_start`, `final_end`, `final_duration_s`.

### Word Boundary Snap Algorithm

`snap_to_word_boundary(target_sec, words, mode)` — reads `transcript_data["words"]` (the Deepgram per-word list).

**Phase 1 — In-word check:**
```python
for word in words:
    if word["start"] <= target_sec <= word["end"]:
        return word["start"] if mode == "start" else word["end"]
```
If the target timestamp falls INSIDE a word, snap directly to that word's boundary.

**Phase 2 — 3-second window search:**
```python
search_window = 3.0
best_time = target_sec  # default: return unchanged if nothing found
best_score = inf

for word in words:
    if mode == "start":
        diff = word["start"] - target_sec
        abs_diff = abs(diff)
        if abs_diff > 3.0: continue
        score = abs_diff * (1.5 if diff > 0 else 1.0)
        # Penalizes word starts AFTER target (diff > 0) — prefer starts BEFORE target
    elif mode == "end":
        diff = word["end"] - target_sec
        abs_diff = abs(diff)
        if abs_diff > 3.0: continue
        score = abs_diff * (1.5 if diff < 0 else 1.0)
        # Penalizes word ends BEFORE target (diff < 0) — prefer ends AFTER target
    if score < best_score:
        best_score = score
        best_time = word["start" or "end"]
```

If no word found within 3 seconds → returns `target_sec` unchanged (no snapping).

### Boundary Math Per Clip

```python
rec_start = clip.get("recommended_start", 0.0)   # from S06 Claude output
rec_end   = clip.get("recommended_end",   0.0)   # from S06 Claude output

snapped_start = snap_to_word_boundary(rec_start, words, "start")
snapped_end   = snap_to_word_boundary(rec_end,   words, "end")

final_start = max(0.0, snapped_start - 0.3)  # 300ms breath buffer before first word
final_end   = snapped_end + 0.5              # 500ms tail buffer after last word

# Clamp duration
if (final_end - final_start) > settings.MAX_CLIP_DURATION:
    final_end = final_start + settings.MAX_CLIP_DURATION  # hard trim
# No trim for too-short clips — just warns

# Clamp to video
if final_end > video_duration:
    final_end = video_duration

final_duration_s = final_end - final_start
```

**Note:** S07 uses `settings.MAX_CLIP_DURATION` and `settings.MIN_CLIP_DURATION` directly — **not** the job-level or channel DNA overrides that S05 and S06 respect. If a user selected `clip_duration_max=45`, S07 still uses `settings.MAX_CLIP_DURATION=60` as its hard cap.

**Exception path (fallback):** If any step throws, the clip is kept with raw unsnapped times:
```python
clip_copy["final_start"] = clip.get("recommended_start", 0.0)
clip_copy["final_end"]   = clip.get("recommended_end",   0.0)
```
This fallback does NOT apply word-boundary snapping — a clip that hits this path can have mid-word boundaries.

### S07 Output

S07 returns `cut_results`: a copy of each evaluated clip dict with 3 new keys appended:

```python
{
    # All existing S06 fields preserved:
    "candidate_id": ...,
    "recommended_start": ...,
    "recommended_end": ...,
    "score": ...,
    "quality_verdict": ...,
    "content_type": ...,
    # ... all other S06 fields ...

    # New from S07:
    "final_start": 751.9,        # float, 3 decimal places
    "final_end": 810.3,          # float, 3 decimal places
    "final_duration_s": 58.4,    # float, 3 decimal places
}
```

---

## 6. S08: Export / Cutting Mechanism

### Source of Timestamps

S08 reads **only** from the S07-computed fields:

```python
final_start    = clip.get("final_start", 0.0)       # word-boundary-snapped start
final_duration = clip.get("final_duration_s", 0.0)  # snapped duration
```

It does **not** read `recommended_start`, `recommended_end`, or `final_end` for the FFmpeg call. `final_end` is only used for the Supabase insert (`clip_data["end_time"]`).

### FFmpeg Command

```bash
ffmpeg -y \
  -ss {final_start} \           # INPUT seek (before -i)
  -i {video_path} \
  -t {final_duration} \          # duration, NOT end time
  -c:v libx264 \
  -preset slow \
  -crf 18 \
  -c:a aac \
  -b:a 320k \
  -movflags +faststart \
  -pix_fmt yuv420p \
  -avoid_negative_ts make_zero \
  -map 0:v:0 \
  -map 0:a:0 \
  {output_path}
```

**`-ss` placement:** BEFORE `-i` = input seek mode. FFmpeg seeks to the nearest GOP (Group of Pictures) keyframe BEFORE `final_start`, then since it re-encodes (`-c:v libx264`), it decodes from that keyframe and discards frames until `final_start` is reached. The output begins precisely at `final_start` seconds.

### Bug Hunt: Why Mid-Word Cuts Happen

**Short answer: S07 prevents mid-word cuts correctly — but there are 5 failure paths that bypass the snap.**

**Full analysis:**

S07 does snap to word boundaries, and the math is correct. However, mid-word cuts occur through these paths:

**Path 1 — Empty words list (most common silent failure)**
```python
words = transcript_data.get("words", [])
if not words:
    print("[S07] Warning: No word timestamps found. Using Gemini's recommended times as-is.")
```
If `transcript_data["words"]` is empty (e.g., Deepgram returned no word-level data despite `words=true` being requested), S07 prints a warning and all candidates are kept with raw LLM timestamps. The 0.3s and 0.5s buffers are still applied to raw non-snapped times.

**Path 2 — 3-second window miss**
`snap_to_word_boundary()` searches only within `±3.0` seconds. If the nearest word boundary is >3s away (long silence, music, B-roll), the function returns `target_sec` unchanged — no snapping occurs. This scenario is rare for speech-dense podcasts but possible at video intros/outros.

**Path 3 — S07 exception fallback**
```python
except Exception as e:
    clip_copy["final_start"] = clip.get("recommended_start", 0.0)
    clip_copy["final_end"] = clip.get("recommended_end", 0.0)
```
Any exception in S07's per-clip processing falls back to raw `recommended_start`/`recommended_end` from S06, bypassing all snapping logic.

**Path 4 — S06 boundary adjustments are LLM-estimated, not snapped**
S06 instructs Claude to "snap to word-level timestamps" in the prompt, but the timestamps Claude sees are the 10-word-interval markers (`[MM:SS.ss]`) injected by `words_to_timestamped_text()`. These are approximate boundary points sampled every ~10 words, not the exact per-word `start`/`end` from Deepgram. Claude adjusts `recommended_start`/`recommended_end` to align with these approximate markers, not actual word boundaries. S07 then corrects this — but only if paths 1-3 don't apply.

**Path 5 — Breath buffers (minor)**
After snapping, `final_start = snapped_start - 0.3`. This deliberately goes 300ms BEFORE the first word. If the previous word's `end` time is within 300ms of `snapped_start`, the buffer reaches into that previous word. Example: if word A ends at 45.1s and word B starts at 45.2s (100ms gap), `snapped_start = 45.2`, `final_start = 44.9`. This is 300ms before B starts, 200ms after A ends — clean gap, no problem. But if there's no gap (back-to-back speech), this could reach into the tail of the previous word's audio.

**The core architectural insight:**
S08 blindly cuts at `final_start`/`final_duration` from S07 — it never independently cross-references Deepgram word timestamps. The entire word-boundary responsibility sits in S07. If S07 fails to snap (paths 1-3), S08 cuts wherever S07 told it to, mid-word or not.

---

## 7. Complete Data Flow Summary

```
S01  video_path (str)
      │ FFmpeg extract → temp_{job_id}.m4a
      ▼
S02  audio_path (str)
      │ Deepgram nova-2 (diarize+sentiment+words+utterances+detect_language)
      ▼
     transcript_data: {
       "transcript": str,
       "words": list[{word, punctuated_word, start, end, speaker, sentiment_score}],
       "utterances": list[{start, end, transcript, speaker, sentiment_score}],
       "duration": float,
       "raw_response": dict
     }
      │
      ├──→ S03 reads: utterances → speaker_stats → predicted_map
      │    speaker_data: {"predicted_map": {int_id: {role, name}}, ...}
      │
      ├──→ S04 reads: utterances + predicted_map (key mismatch bug)
      │    labeled_transcript: str (multi-line "[MM:SS.s] UNKNOWN: text\n...")
      │
      ├──→ S05 reads: labeled_transcript (string injected into prompt)
      │    also reads: transcript_data["duration"] for VIDEO_DURATION_PLACEHOLDER
      │    candidates: list[{candidate_id, timestamp, recommended_start,
      │                       recommended_end, estimated_duration, hook_text,
      │                       reason, primary_signal, content_type, needs_context}]
      │
      ├──→ S06 reads: candidates + labeled_transcript + transcript_data["words"]
      │    enriches with: transcript context windows + video frames (base64)
      │    sends to Claude Sonnet-4.6 in batches of 4
      │    evaluated_clips: list[{candidate_id, recommended_start, recommended_end,
      │                            hook_text, score, quality_verdict, quality_notes,
      │                            content_type, clip_strategy_role, posting_order,
      │                            suggested_title, suggested_description}]
      │
      ├──→ S07 reads: evaluated_clips + transcript_data["words"]
      │    snap_to_word_boundary() on recommended_start/end
      │    adds: final_start, final_end, final_duration_s
      │    cut_results: list[dict] — all S06 fields + 3 new fields
      │
      └──→ S08 reads: cut_results["final_start"] + cut_results["final_duration_s"]
           FFmpeg: -ss final_start -i video -t final_duration (re-encode libx264)
           → R2 upload → Supabase clips insert
           exported_clips: list[dict] — Supabase row data
```

---

## 8. Identified Bugs

| Bug | Location | Severity | Description |
|---|---|---|---|
| Speaker map key mismatch | S03→S04 | **Critical** | S03 stores keys as raw integers (`0`, `1`). S04 lookups use string `"SPEAKER_0"`. Match always fails → all speakers labeled `UNKNOWN` in `labeled_transcript`. |
| `failed_log` NameError | S06 line 603 | Low | `len(failed_log)` references undefined variable inside `try/except Exception: pass` — silently swallowed, director event never fires. |
| S07 ignores job-level duration override | S07 | Medium | Uses `settings.MAX_CLIP_DURATION` not `clip_duration_max`. A user's duration preference set at job creation is honored by S05/S06 but ignored by S07's hard cap. |
| No word-snap when `words` list is empty | S07 | High | If Deepgram returns no per-word timestamps, all clips skip word-boundary snapping. The print is a warning, not an error — pipeline silently continues with raw LLM timestamps. |
| S07 exception fallback bypasses snap | S07 | Medium | Per-clip exception uses raw `recommended_start`/`recommended_end` without snapping. Any exception (e.g., from ffprobe failing) causes fallback to unsnapped times. |
