# Gaming Mode Reframe — Technical Plan v2

## Architecture

Gaming mode is architecturally different from podcast mode in every layer:

| Concern | Podcast | Gaming |
|---|---|---|
| Output | Keyframes → frontend applies transforms | New `.mp4` rendered by FFmpeg on server |
| Composition | Single video, cropped/panned | Two zones stacked vertically (vstack) |
| AI | Gemini analyzes every scene | None — deterministic only |
| Diarization | Required | Not used |
| Face tracking | All frames, all shots | First 5 seconds only |
| Result type | `keyframes[]` array | `processed_video_url` (R2 URL) |
| Frontend | Applies transforms to existing element | Replaces video asset with processed file |

---

## Fixed Output Format

**Always 1080×1920 (9:16) split-screen:**

```
┌──────────────────────────┐  ← 1080 wide
│                          │
│     WEBCAM (face-cam)    │  640 px tall
│                          │
├──────────────────────────┤
│                          │
│                          │
│     GAMEPLAY (center)    │  1280 px tall
│                          │
│                          │
└──────────────────────────┘
         1080 × 1920 total
```

The proportions (640 top / 1280 bottom) are fixed. The game panel gets 2× the screen space of the webcam panel.

---

## Pipeline Steps

### Step 1 — Probe
`ffprobe` → `src_w`, `src_h`, `fps`, `duration_s`.
Identical to podcast. Reuse `_probe_video()` from `pipeline.py`.

### Step 2 — Startup Frame Sampling
Extract frames at t=0, 1, 2, 3, 4 seconds (max `min(5, duration_s)` frames):

```python
def _sample_startup_frames(video_path: str, n_seconds: int = 5) -> list[tuple[float, np.ndarray]]:
    results = []
    cap = cv2.VideoCapture(video_path)
    try:
        for t in range(n_seconds):
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ret, frame = cap.read()
            if ret and frame is not None:
                results.append((float(t), frame))
    finally:
        cap.release()
    return results  # [(time_s, bgr_frame), ...]
```

Why first 5 seconds: the game UI and webcam overlay are always visible at video start.
Cutscenes / loading screens happen later and don't affect layout detection.

### Step 3 — Webcam Face Detection (YOLO)
Reuse `YoloDetector` from `face_tracker.py`. Run on all sampled frames.
Webcam faces are **small** — they are an overlay box, not a full close-up.

**Webcam detection criteria:**
```python
WEBCAM_MAX_FACE_WIDTH_NORM = 0.20   # >20% of frame width = in-game character, not webcam
WEBCAM_MIN_CONFIDENCE = 0.55        # Same as FaceTrackerConfig default
WEBCAM_MIN_FRAME_COUNT = 3          # Must be stable across 3+ of the 5 sampled frames
WEBCAM_STABILITY_RADIUS_NORM = 0.12 # Centroid must not wander > 12% of frame width
```

For each sampled frame, keep only detections where `face_width < WEBCAM_MAX_FACE_WIDTH_NORM`.
Group consistent small faces (appear in ≥3 frames at stable position) → these are webcam.
Inconsistent or large detections → game characters, discard.

**Best webcam candidate selection:**
- Group by approximate quadrant (TL / TR / BL / BR)
- Count how many frames each group appears in
- Pick the group with the most frames (most stable)
- Compute median `face_cx`, `face_cy`, `face_w`, `face_h` for that group

### Step 4 — Canny Edge Detection (Exact Webcam Bounds)

YOLO gives us the face bbox, but the actual webcam overlay extends beyond the face (includes
body, background, and a rounded-corner border). Canny finds the exact rectangle.

```python
def find_webcam_bounds_canny(
    frame: np.ndarray,
    face_cx_norm: float,
    face_cy_norm: float,
    face_w_norm: float,
    face_h_norm: float,
    src_w: int,
    src_h: int,
) -> tuple[int, int, int, int] | None:
    """
    Scan outward from YOLO face center using Canny edge detection.
    Returns (webcam_x, webcam_y, webcam_w, webcam_h) in source pixels.
    Returns None if no clear rectangle is found — caller uses YOLO bbox fallback.
    """
    face_cx_px = int(face_cx_norm * src_w)
    face_cy_px = int(face_cy_norm * src_h)
    face_w_px  = int(face_w_norm  * src_w)
    face_h_px  = int(face_h_norm  * src_h)

    # Expand ROI 2.5× around face center to capture webcam border fully
    EXPAND = 2.5
    roi_x1 = max(0, face_cx_px - int(face_w_px * EXPAND))
    roi_y1 = max(0, face_cy_px - int(face_h_px * EXPAND))
    roi_x2 = min(src_w, face_cx_px + int(face_w_px * EXPAND))
    roi_y2 = min(src_h, face_cy_px + int(face_h_px * EXPAND))

    roi = frame[roi_y1:roi_y2, roi_x1:roi_x2]
    if roi.size == 0:
        return None

    gray    = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)      # remove noise before Canny
    edges   = cv2.Canny(blurred, threshold1=30, threshold2=100)

    # Dilate to bridge minor gaps in the webcam border line
    kernel = np.ones((3, 3), np.uint8)
    edges  = cv2.dilate(edges, kernel, iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    MIN_AREA = face_w_px * face_h_px  # result must be at least the size of the face itself
    best_rect = None
    best_area = float(MIN_AREA)

    for cnt in contours:
        peri   = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.03 * peri, True)
        if len(approx) != 4:
            continue  # only rectangles
        area = cv2.contourArea(approx)
        if area <= best_area:
            continue
        x, y, w, h = cv2.boundingRect(approx)
        # Reject degenerate shapes (very thin strips)
        if w < 40 or h < 40 or (w / h) > 5.0 or (h / w) > 5.0:
            continue
        # Reject if the bounding rect doesn't contain the face center
        cx_roi = face_cx_px - roi_x1
        cy_roi = face_cy_px - roi_y1
        if not (x <= cx_roi <= x + w and y <= cy_roi <= y + h):
            continue
        best_rect = (x, y, w, h)
        best_area = area

    if best_rect is None:
        return None

    x, y, w, h = best_rect
    # Offset back to full-frame coordinates
    return (roi_x1 + x, roi_y1 + y, w, h)


def _webcam_bounds_fallback(
    face_cx_norm: float, face_cy_norm: float,
    face_w_norm: float,  face_h_norm: float,
    src_w: int, src_h: int,
    expand_factor: float = 2.0,
) -> tuple[int, int, int, int]:
    """Fallback when Canny fails: expand YOLO face bbox by expand_factor."""
    cx = int(face_cx_norm * src_w)
    cy = int(face_cy_norm * src_h)
    fw = int(face_w_norm  * src_w)
    fh = int(face_h_norm  * src_h)
    wc_x = max(0, cx - int(fw * expand_factor / 2))
    wc_y = max(0, cy - int(fh * expand_factor / 2))
    wc_w = min(src_w - wc_x, int(fw * expand_factor))
    wc_h = min(src_h - wc_y, int(fh * expand_factor))
    return wc_x, wc_y, wc_w, wc_h
```

**Why Canny beats YOLO bbox alone:**
YOLO returns the face bounding box, not the webcam overlay box. The webcam overlay typically
includes body, background, rounded corners, and a visible border — Canny finds the exact
rectangle edge so the FFmpeg crop does not bleed into the gameplay area.

### Step 5 — Game Area Calculation

**Game panel output:** 1080×1280 px
**Game source crop** from a 1920×1080 source:

```
game_crop_h = src_h                            # = 1080 (full height)
game_crop_w = round(src_h × 1080 / 1280)       # = round(1080 × 0.84375) = 911 px
```

This gives exactly the 1080:1280 aspect ratio, so `scale=1080:1280` in FFmpeg is lossless.

**Horizontal position — CENTER-FIRST:**

In gaming (shooters, RPGs, MOBAs), the crosshair and main action are always at screen center.
The game_crop_x MUST start from the absolute center and only shift if the webcam overlaps.

```python
EDGE_MARGIN = 20  # px

game_crop_w = int(round(src_h * 1080 / 1280))
game_crop_h = src_h

# STEP A: Start at dead center — this covers the crosshair for virtually all games
center_x = (src_w - game_crop_w) / 2.0  # = 504 for 1920w source

# STEP B: Check how much the center crop overlaps the webcam
def _overlap_ratio(game_x: float, game_w: int, wc_x: int, wc_w: int) -> float:
    overlap_px = max(0.0, min(game_x + game_w, wc_x + wc_w) - max(game_x, wc_x))
    return overlap_px / wc_w if wc_w > 0 else 0.0

overlap = _overlap_ratio(center_x, game_crop_w, wc_x, wc_w)

if overlap <= 0.15:
    # Most webcams sit in extreme corners — center crop doesn't touch them at all
    game_crop_x = int(round(center_x))
else:
    # STEP C: Minimal shift to clear the webcam — stay as close to center as possible
    # Option A: shift game crop fully LEFT of webcam
    left_x  = float(wc_x - game_crop_w - EDGE_MARGIN)
    # Option B: shift game crop fully RIGHT of webcam
    right_x = float(wc_x + wc_w + EDGE_MARGIN)

    shift_left  = abs(center_x - left_x)
    shift_right = abs(right_x - center_x)

    if shift_left <= shift_right:
        candidate = left_x
    else:
        candidate = right_x

    game_crop_x = int(round(max(0.0, min(float(src_w - game_crop_w), candidate))))
```

**Why center-first is correct:**
- Crosshair / main character = always `x ≈ src_w / 2` in every game engine
- Webcam overlays are placed in **corners** by every streaming software (OBS, Streamlabs)
- For 1920w source, center crop covers `[504, 1415]` — a typical corner webcam at `x > 1600` has zero overlap
- Shift only happens when a streamer placed their webcam unusually close to center

### Step 6 — FFmpeg Render (filter_complex vstack)

```python
def _run_ffmpeg_gaming(
    input_path: str,
    output_path: str,
    wc_x: int, wc_y: int, wc_w: int, wc_h: int,
    game_x: int, game_y: int, game_w: int, game_h: int,
) -> None:
    """
    Render split-screen gaming video using FFmpeg filter_complex.

    Output: 1080×1920
      [0:0] → crop webcam region → scale to 1080×640 → top panel
      [0:1] → crop game region   → scale to 1080×1280 → bottom panel
      vstack → final 1080×1920 output
    """
    # Webcam: letterbox to 1080×640 (preserves aspect ratio, black bars for non-16:9 webcams)
    webcam_filter = (
        f"[0:v]crop={wc_w}:{wc_h}:{wc_x}:{wc_y},"
        "scale=1080:640:force_original_aspect_ratio=decrease,"
        "pad=1080:640:(ow-iw)/2:(oh-ih)/2:black"
        "[top]"
    )

    # Game: direct scale (crop dimensions already match 1080:1280 aspect ratio)
    game_filter = (
        f"[0:v]crop={game_w}:{game_h}:{game_x}:{game_y},"
        "scale=1080:1280"
        "[bottom]"
    )

    filter_complex = f"{webcam_filter};{game_filter};[top][bottom]vstack=inputs=2[out]"

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-map", "0:a?",          # copy audio if present
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "320k",
        "-movflags", "+faststart",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg gaming render failed: {result.stderr[-500:]}")
```

**Note on preset:** `fast` instead of the export pipeline's `slow`. Gaming clips are often longer
(10–30 min streams → even short clips are 1–5 min). `fast` keeps quality high (crf=18) while
processing at ~50–100× realtime on CPU vs ~10–20× for `slow`.

### Step 7 — R2 Upload

```python
from app.services.r2_client import get_r2_client
from app.config import settings

r2  = get_r2_client()
key = f"gaming-reframe/{uuid.uuid4().hex}.mp4"
with open(output_path, "rb") as f:
    r2.put_object(
        Bucket=settings.R2_BUCKET_NAME,
        Key=key,
        Body=f,
        ContentType="video/mp4",
    )
processed_url = f"{settings.R2_PUBLIC_URL.rstrip('/')}/{key}"
```

### Step 8 — Return

Gaming pipeline returns a `ReframeResult` with an empty `keyframes` list and the processed URL
stored in `metadata["processed_video_url"]`:

```python
return ReframeResult(
    keyframes=[],          # no keyframes — video is already composed
    scene_cuts=[],
    src_w=1080,            # output dimensions (not source)
    src_h=1920,
    fps=fps,
    duration_s=duration_s,
    content_type="gaming",
    tracking_mode="x_only",
    metadata={
        "processed_video_url": processed_url,
        "webcam_bounds": {"x": wc_x, "y": wc_y, "w": wc_w, "h": wc_h},
        "game_bounds": {"x": game_x, "y": game_y, "w": game_w, "h": game_h},
        "webcam_detected_by": "canny" or "yolo_fallback" or "none",
        "pipeline": "gaming_vstack",
        "source_w": src_w,
        "source_h": src_h,
    },
)
```

---

## Backend Implementation

### New file: `backend/app/reframe/gaming_pipeline.py`

Full implementation combining all the code blocks above. Public entry point:

```python
def run_gaming_reframe(
    video_path: str,
    src_w: int,
    src_h: int,
    fps: float,
    duration_s: float,
    detection_engine: str = "yolo",
    on_progress: Callable[[str, int], None] | None = None,
) -> ReframeResult:
    """
    Gaming mode reframe pipeline.
    Produces a new 1080×1920 video (webcam on top, gameplay on bottom).
    Returns ReframeResult with metadata["processed_video_url"] set.
    No keyframes, no Gemini, no diarization.
    """
    progress = lambda step, pct: (logger.info("[Gaming] %d%% — %s", pct, step), on_progress and on_progress(step, pct))

    # 1. Sample startup frames
    progress("Sampling startup frames...", 10)
    sampled = _sample_startup_frames(video_path, n_seconds=5)

    # 2. Face detection → webcam candidate
    progress("Detecting webcam region...", 25)
    config   = FaceTrackerConfig()
    detector = _get_detector(detection_engine, config)
    webcam_face, best_frame = _find_webcam_face(sampled, detector, config, src_w, src_h)

    # 3. Canny → exact webcam bounds
    wc_detected_by = "none"
    if webcam_face is not None:
        progress("Canny edge detection...", 40)
        canny_result = find_webcam_bounds_canny(
            best_frame,
            webcam_face.face_x, webcam_face.face_y,
            webcam_face.face_width, webcam_face.face_height,
            src_w, src_h,
        )
        if canny_result:
            wc_x, wc_y, wc_w, wc_h = canny_result
            wc_detected_by = "canny"
        else:
            wc_x, wc_y, wc_w, wc_h = _webcam_bounds_fallback(
                webcam_face.face_x, webcam_face.face_y,
                webcam_face.face_width, webcam_face.face_height,
                src_w, src_h,
            )
            wc_detected_by = "yolo_fallback"
    else:
        # No webcam found — cannot do split-screen, raise to inform user
        raise RuntimeError(
            "No webcam overlay detected in the first 5 seconds of video. "
            "Gaming mode requires a visible face-cam. "
            "If this is a screen recording without webcam, use Podcast mode."
        )

    # 4. Game crop region
    progress("Computing game crop region...", 55)
    game_w, game_h, game_x, game_y = _compute_game_crop(src_w, src_h, wc_x, wc_y, wc_w, wc_h)

    # 5. FFmpeg render
    progress("Rendering split-screen video...", 65)
    output_path = os.path.join(str(settings.UPLOAD_DIR), f"gaming_{uuid.uuid4().hex}.mp4")
    try:
        _run_ffmpeg_gaming(video_path, output_path, wc_x, wc_y, wc_w, wc_h, game_x, game_y, game_w, game_h)
    except Exception as e:
        raise RuntimeError(f"FFmpeg gaming render failed: {e}") from e

    # 6. Upload to R2
    progress("Uploading processed video...", 90)
    try:
        r2  = get_r2_client()
        key = f"gaming-reframe/{uuid.uuid4().hex}.mp4"
        with open(output_path, "rb") as f:
            r2.put_object(Bucket=settings.R2_BUCKET_NAME, Key=key, Body=f, ContentType="video/mp4")
        processed_url = f"{settings.R2_PUBLIC_URL.rstrip('/')}/{key}"
    finally:
        try:
            os.remove(output_path)
        except Exception:
            pass

    progress("Done!", 100)
    return ReframeResult(
        keyframes=[],
        scene_cuts=[],
        src_w=1080,
        src_h=1920,
        fps=fps,
        duration_s=duration_s,
        content_type="gaming",
        tracking_mode="x_only",
        metadata={
            "processed_video_url": processed_url,
            "webcam_bounds": {"x": wc_x, "y": wc_y, "w": wc_w, "h": wc_h},
            "game_bounds":   {"x": game_x, "y": game_y, "w": game_w, "h": game_h},
            "webcam_detected_by": wc_detected_by,
            "pipeline": "gaming_vstack",
            "source_w": src_w,
            "source_h": src_h,
        },
    )
```

### Integration in `pipeline.py`

Add immediately after `_probe_video` (step 2), before shot detection (step 3):

```python
# Gaming mode: server-side FFmpeg split-screen render. No Gemini, no diarization.
if content_type_hint == "gaming":
    from .gaming_pipeline import run_gaming_reframe
    progress("Gaming mode — analyzing webcam overlay...", 10)
    result = run_gaming_reframe(
        video_path=input_path,
        src_w=src_w,
        src_h=src_h,
        fps=fps,
        duration_s=duration_s,
        detection_engine=detection_engine,
        on_progress=on_progress,
    )
    return result
    # Note: temp_path cleanup is handled by the outer try/finally block
```

---

## API Changes

### 1. `ReframeStatusResponse` — add `processed_video_url`

In `backend/app/api/routes/reframe.py`:

```python
class ReframeStatusResponse(BaseModel):
    status: str
    step: str
    percent: int
    keyframes: Optional[list[dict]] = None
    scene_cuts: Optional[list[float]] = None
    src_w: Optional[int] = None
    src_h: Optional[int] = None
    fps: Optional[float] = None
    duration_s: Optional[float] = None
    content_type: Optional[str] = None
    tracking_mode: Optional[str] = None
    processed_video_url: Optional[str] = None   # NEW — gaming mode only
    error: Optional[str] = None
```

### 2. Status endpoint — read from `pipeline_metadata`

In `get_reframe_status()`, after building `ReframeStatusResponse`:

```python
# Extract processed_video_url from pipeline_metadata for gaming mode
pipeline_meta = job.get("pipeline_metadata") or {}
processed_video_url = pipeline_meta.get("processed_video_url")

return ReframeStatusResponse(
    ...existing fields...,
    processed_video_url=processed_video_url,
)
```

No Supabase schema change needed — `pipeline_metadata` is already a JSONB column.

---

## Frontend Changes

### `engine.ts` — `pollReframeJob` return type

Extend return type to include gaming mode result:

```typescript
interface PollResult {
    keyframes: ReframeKeyframe[];
    scene_cuts: number[];
    src_w: number;
    src_h: number;
    fps: number;
    debugVideoUrl?: string;
    processedVideoUrl?: string;  // gaming mode
}
```

In `pollReframeJob`, when `data.status === "done"`:
```typescript
return {
    keyframes: (data.keyframes ?? []) as ReframeKeyframe[],
    scene_cuts: (data.scene_cuts ?? []) as number[],
    src_w: data.src_w as number,
    src_h: data.src_h as number,
    fps: (data.fps as number) ?? 30,
    debugVideoUrl,
    processedVideoUrl: data.processed_video_url ?? undefined,
};
```

### `engine.ts` — `runReframe` gaming handler

In the main `runReframe` loop, after `pollReframeJob`:

```typescript
// Gaming mode: backend produced a new composed video — replace the timeline element
if (processedVideoUrl) {
    onProgress({ step: `Replacing video with split-screen output${label}...`, percent: 97 });
    await replaceVideoWithGamingOutput(editor, trackId, element, processedVideoUrl, options.aspectRatio);
    results.push({ elementId: element.id, keyframeCount: 0, reframeJobId: reframe_job_id });
    continue;
}

// Podcast mode: apply keyframes to timeline
const segmentCount = applyReframeWithSplits(...);
```

### `engine.ts` — `replaceVideoWithGamingOutput`

```typescript
async function replaceVideoWithGamingOutput(
    editor: EditorCore,
    trackId: string,
    element: VideoElement,
    processedVideoUrl: string,
    aspectRatio: ReframeAspectRatio,
): Promise<void> {
    // Register the processed video as a new media asset
    const newAssetId = crypto.randomUUID();
    await editor.media.addAsset({
        id: newAssetId,
        url: processedVideoUrl,
        type: "video",
        name: `gaming_reframe_${element.id}.mp4`,
        duration: element.duration,
    });

    // Point the timeline element to the new asset, reset all transforms
    editor.timeline.updateElements({
        updates: [{
            trackId,
            elementId: element.id,
            updates: {
                mediaId: newAssetId,
                coverMode: false,
                animations: { channels: {} },
                transform: {
                    position: { x: 0, y: 0 },
                    scale: 1,
                    rotate: element.transform.rotate,
                },
            },
        }],
    });

    // Update canvas to 1080×1920 (gaming always 9:16)
    const canvasSize = ASPECT_RATIO_CANVAS["9:16"];
    await editor.project.updateSettings({ settings: { canvasSize } });
}
```

**Important:** Check the exact `editor.media.addAsset()` API signature in `EditorCore` before
implementing. The parameters above follow the pattern seen in `use-clip-import.ts`.

### `reframe.tsx` — Enable gaming button

When the gaming pipeline is implemented, replace the "coming soon" block for gaming:

```tsx
contentType === "gaming" ? (
    <Button className="w-full" onClick={handleReframe} disabled={isProcessing}>
        {isProcessing && <Spinner className="mr-2" />}
        {isProcessing
            ? (progress?.step ?? "Processing...")
            : "Render Split-Screen"}
    </Button>
) : ...
```

Also hide Tracking Mode and Detection Engine sections when `contentType === "gaming"` since
those are irrelevant (engine auto-selects YOLO, tracking mode is irrelevant).

---

## Math Verification

### 1920×1080 source → 1080×1920 output

```
src_w = 1920, src_h = 1080

Webcam panel output:  1080 × 640
Game panel output:    1080 × 1280
Total output:         1080 × 1920  ✓

game_crop_w = round(1080 × 1080/1280) = round(911.25) = 911 px
game_crop_h = 1080 px
game_crop_aspect = 911/1080 = 0.8435...
target_game_aspect = 1080/1280 = 0.84375  → difference: 0.00015 → negligible ✓

FFmpeg scale=1080:1280 stretches 911×1080 by factor 1.185 horizontally and vertically.

Webcam on right (face_cx > 0.5):
    game_crop_x = 20 (EDGE_MARGIN)
    game_crop rightmost pixel: 20 + 911 = 931
    If webcam starts at x=1600: overlap = 0  ✓

Webcam on left (face_cx < 0.5):
    game_crop_x = 1920 - 911 - 20 = 989
    game_crop leftmost pixel: 989
    If webcam ends at x=320: overlap = 0  ✓
```

### 1280×720 source (common OBS output)

```
src_w = 1280, src_h = 720

game_crop_w = round(720 × 1080/1280) = round(607.5) = 608 px
game_crop_h = 720 px
game_crop_aspect = 608/720 = 0.8444 ≈ 1080/1280 = 0.8438  ✓

Webcam on right:  game_crop_x = 20         → game covers [20, 628]
Webcam on left:   game_crop_x = 1280-608-20 = 652 → game covers [652, 1260]
```

---

## Known Risks & Edge Cases

| Risk | Root cause | Mitigation |
|---|---|---|
| Canny misses the webcam border | Rounded corners, semi-transparent overlay | `cv2.dilate` bridges gaps; fallback to YOLO bbox expansion |
| In-game faces trigger as webcam | Game has a face close-up | `WEBCAM_MAX_FACE_WIDTH_NORM = 0.20` filters these out; in-game faces are usually full-screen |
| No webcam detected | Pure screen recording, no face-cam | Pipeline raises `RuntimeError` with clear user message; frontend shows the error |
| Webcam is NOT in a corner | Streamer moves window to center | YOLO + Canny still find it; game crop avoids it via overlap check |
| Very tall webcam (9:16 phone cam overlay) | wc_h > wc_w | Aspect ratio sanity check in Canny (rejects h/w > 5.0); YOLO fallback handles it |
| Long video processing time | FFmpeg -preset fast on 1-hour stream | `clip_start`/`clip_end` are passed → trim before rendering using `-ss` and `-t` flags |
| R2 upload fails | Network/auth issue | `try/finally` always cleans up `output_path`; error propagates as job failure |
| YOLO model cold start | First request loads 300MB model | Already cached by `_detector_cache` dict in face_tracker.py across requests |
| game_crop bleeds into webcam after overlap fix | Webcam unusually large (>50% frame) | Accept best-effort; log warning. These are edge cases outside typical streaming setups |

---

## Implementation Order

1. `backend/app/reframe/gaming_pipeline.py` — full implementation
2. `backend/app/api/routes/reframe.py` — add `processed_video_url` to status response
3. `backend/app/reframe/pipeline.py` — add gaming branch after probe
4. `opencut/apps/web/src/lib/reframe/engine.ts` — add `processedVideoUrl` handling + `replaceVideoWithGamingOutput`
5. `opencut/apps/web/src/components/editor/panels/assets/views/reframe.tsx` — enable gaming button
