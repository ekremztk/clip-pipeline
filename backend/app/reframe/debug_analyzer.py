"""
Debug Video Analyzer — sends the annotated debug video + full pipeline decision
data to Gemini 2.5 Pro for a comprehensive, adversarial quality analysis.

Gemini receives:
  1. The annotated debug video (visual ground truth)
  2. Every intermediate decision the pipeline made (shot types, Gemini plan,
     focus resolver choices, path solver strategies, keyframes)

It cross-validates video evidence vs pipeline decisions and reports discrepancies.
"""
import json
import logging
import os
import tempfile

from app.config import settings

logger = logging.getLogger(__name__)


def _build_prompt(pipeline_context: dict) -> str:
    pipeline_json = json.dumps(pipeline_context, indent=2, ensure_ascii=False)

    return f"""You are a ruthless video reframing QA engineer. Your job is to FIND BUGS, not to praise the system.

You are given TWO inputs:
1. A debug visualization video of an AI auto-reframe pipeline
2. The complete JSON of every decision the pipeline made

**Video overlay legend:**
- GREEN rectangles = MediaPipe face detections (track ID + confidence)
- RED circles = Focus resolver target (what path solver receives)
- BLUE circles = Path solver smooth camera position
- YELLOW rectangle = Final crop window (what viewer sees)
- WHITE text top-left = timestamp, shot type, strategy

**Your mandate:** Watch the video with your own eyes. Then look at the pipeline's decisions. Find every place where the pipeline's decisions caused bad output. Be specific. Be brutal. Do not say "acceptable" when it looks wrong.

---

## PIPELINE DECISIONS (complete JSON):
```json
{pipeline_json}
```

---

Now analyze the video and answer all sections:

## SECTION 1: Face Detection vs Reality
Compare what you see (green boxes) vs what the pipeline reports.
- List every timestamp where a person is visible but has NO green box
- List every timestamp where green box is on the WRONG person or wrong location
- Is the face detection data in the JSON consistent with what you see?
- Where does detection loss cause downstream damage?

## SECTION 2: Shot Classification Audit
The pipeline's `shots` array says each shot's type (closeup/wide/b_roll).
Compare each shot's VISUAL REALITY to the pipeline's classification:
- Is each shot type label CORRECT or WRONG?
- For EVERY misclassified shot: what is it visually, what did the pipeline say?
- How does the wrong classification cascade into wrong crop behavior?

## SECTION 3: Gemini Director Audit
The pipeline's `gemini_director` section shows WHO Gemini told the system to focus on and WHY.
- For each directive: was the focus decision CORRECT from a storytelling standpoint?
- Where did Gemini pick the wrong subject? At which timestamp?
- Where did the Gemini plan conflict with what you actually see in the video?
- Is the content_type and layout classification accurate?

## SECTION 4: Focus Resolver Audit (Red Dot)
The pipeline picked a focus point per frame. Compare red dot position to what you see:
- At which timestamps is the red dot on the WRONG person?
- At which timestamps is the red dot in EMPTY SPACE (no face nearby)?
- When faces are lost, does the red dot hold position or jump? Where?
- List all timestamps where the red dot is clearly wrong, with what it should be.

## SECTION 5: Path Solver Audit (Blue Dot)
The pipeline used TRACKING or STATIONARY strategy per shot.
- For each shot: was the strategy choice correct given the visual content?
- Does the blue dot actually track the red dot or does it lag/overshoot?
- Any jitter, snapping, or sudden jumps WITHIN a shot (not at cut boundaries)?
- Are there moments where the path solver's smoothing obscures important motion?

## SECTION 6: Crop Window Audit (Yellow Rectangle) — MOST CRITICAL
For EVERY shot segment, rate the crop 1-10 and explain:
- Is the primary subject INSIDE the yellow rectangle?
- Is the subject well-centered or pushed to an edge?
- Does the crop miss key action (gesture, expression, reaction)?
- List the 5 worst crop moments with timestamps and descriptions.

## SECTION 7: Shot Transition / Sliding Audit
At every shot cut (scene_cuts in the JSON), inspect the yellow rectangle:
- Does it JUMP INSTANTLY to the new position? (correct behavior)
- Or does it SLIDE/PAN from the old position to the new? (bug: means wrong interpolation)
- List every transition where sliding occurs instead of hard cut.
- Also check: is the first frame of each new shot already in the right position?

## SECTION 8: Root Cause Mapping
For the top 5 worst moments in the video, trace the exact bug path:
- What does the viewer see wrong?
- Which pipeline component made the decision that caused it?
- Which specific field in the JSON shows the wrong decision?
- What the field SHOULD have been set to instead?

## SECTION 9: Cascading Failure Analysis
Identify chain reactions where one wrong decision caused multiple downstream failures.
Format: [wrong decision] → [intermediate effect] → [visible result in video]

## SECTION 10: Priority Fix List
List the top 5 code changes ranked by viewer impact.
For each: component name, specific logic to change, expected improvement.

## SECTION 11: Score per Shot + Overall
Rate each shot 1-10 (10 = perfect vertical reframe).
Then give an overall pipeline quality score 1-10.
Be harsh. A score above 7 requires perfect subject framing with no wrong-person tracking.

---
Be specific with timestamps (0:03, 0:07-0:12 format).
Cross-reference video observations with JSON data constantly.
If the JSON says TRACKING but the crop is not moving, say so explicitly.
If Gemini said focus on Subject A but the red dot is on Subject B, say so explicitly."""


def analyze_debug_video(
    debug_video_url: str,
    reframe_job_id: str,
    pipeline_context: dict,
) -> dict:
    """
    Download the debug video from R2 (authenticated), combine with full pipeline
    decision JSON, send to Gemini 2.5 Pro for adversarial cross-validation analysis.
    """
    logger.info(
        "[DebugAnalyzer] Starting analysis for job %s, url=%s",
        reframe_job_id, debug_video_url,
    )

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4",
                                         dir=str(settings.UPLOAD_DIR)) as tmp:
            temp_path = tmp.name

        # Download via R2 SDK (debug/ path is not publicly accessible)
        r2_key = debug_video_url.split(settings.R2_PUBLIC_URL.rstrip("/") + "/", 1)[-1]
        logger.info("[DebugAnalyzer] Downloading via R2 SDK: key=%s", r2_key)

        from app.services.r2_client import get_r2_client
        r2 = get_r2_client()
        obj = r2.get_object(Bucket=settings.R2_BUCKET_NAME, Key=r2_key)
        with open(temp_path, "wb") as f:
            f.write(obj["Body"].read())

        size_mb = os.path.getsize(temp_path) / (1024 * 1024)
        logger.info("[DebugAnalyzer] Downloaded %.1fMB → %s", size_mb, temp_path)

        prompt = _build_prompt(pipeline_context)

        from app.services.gemini_client import analyze_video as gemini_analyze_video
        model = settings.GEMINI_MODEL_PRO

        logger.info("[DebugAnalyzer] Sending to Gemini %s (video + pipeline JSON)...", model)
        raw = gemini_analyze_video(
            video_path=temp_path,
            prompt=prompt,
            model=model,
            json_mode=False,
        )
        logger.info("[DebugAnalyzer] Analysis received: %d chars", len(raw))

        return {
            "job_id": reframe_job_id,
            "model": model,
            "analysis": raw,
            "debug_video_url": debug_video_url,
        }

    except Exception as e:
        logger.error("[DebugAnalyzer] Analysis failed: %s", e)
        raise

    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
