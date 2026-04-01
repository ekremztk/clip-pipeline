"""
Debug Video Analyzer — sends the annotated debug video to Gemini 2.5 Pro
for a comprehensive frame-by-frame quality analysis of the reframe pipeline.

Answers 8 structured sections covering face detection, focus resolver,
path solver, crop quality, shot classification, root causes, and scoring.
"""
import logging
import os
import tempfile
import urllib.request

from app.config import settings

logger = logging.getLogger(__name__)

_ANALYSIS_PROMPT = """You are a world-class video reframing engineer analyzing a debug visualization video of an AI auto-reframe pipeline.

The video has colored overlays showing internal pipeline state:
- GREEN rectangles: MediaPipe face detection bounding boxes (track ID + confidence score)
- RED circles: Focus resolver target point — what the path solver receives as input
- BLUE circles: Path solver smooth camera position
- YELLOW rectangle: Final crop window — what the viewer sees in the vertical video
- WHITE text (top-left): timestamp, shot type, reframe strategy + crop offset math
- Legend (bottom-left): color definitions

CRITICAL GOAL: Evaluate whether the YELLOW crop window correctly frames the most important content at every moment.

Watch the ENTIRE video carefully frame by frame and provide a COMPREHENSIVE analysis answering ALL sections below. Be SPECIFIC with timestamps (format: 0:03, 0:07-0:12).

---

## SECTION 1: Face Detection Quality
1a. At which specific timestamps are faces MISSED despite people being clearly visible in frame?
1b. For each missed detection, what is the likely cause? (profile/side-facing, occlusion, small size, motion blur, low contrast, distance)
1c. Are there any FALSE POSITIVE detections (green boxes on non-face regions)?
1d. Roughly what percentage of total duration has at least one green box active?
1e. Which person/subject is detected MOST reliably vs LEAST reliably?

---

## SECTION 2: Focus Resolver Accuracy (Red Dot)
2a. When no faces are detected, where does the red dot go? Is this position reasonable or is it pointing at empty space?
2b. In shots with multiple detected faces: does the red dot correctly target the most narratively important subject?
2c. List EVERY timestamp where the red dot is in a clearly WRONG position (e.g. pointing at the desk, empty background, between two people).
2d. In closeup shots: does the red dot land on the face accurately?

---

## SECTION 3: Path Solver Smoothness (Blue Dot)
3a. Does the blue dot track the red dot smoothly, or is there lag/jitter?
3b. Are there any sudden jumps or snapping in the blue dot? At which timestamps?
3c. At shot cut boundaries: does the blue dot transition cleanly to the new position?
3d. Overall: is the blue dot path smooth enough for a good viewing experience?

---

## SECTION 4: Crop Window Quality — MOST IMPORTANT (Yellow Rectangle)
For EACH distinct shot segment you observe, evaluate the yellow crop:
4a. Is the main subject INSIDE the yellow rectangle? Or do they exit the frame?
4b. Is the subject reasonably centered, or pushed uncomfortably to one edge?
4c. Rate each shot: PERFECT / GOOD / ACCEPTABLE / BAD / CRITICAL_FAILURE
4d. List the TOP 3 worst moments where the crop window completely misses the subject.

---

## SECTION 5: Shot-by-Shot Breakdown
For each shot boundary you detect (look for sudden yellow rectangle jumps):
5a. What type of shot is it visually? (wide/two-shot, closeup, b-roll/cutaway)
5b. What is the pipeline's classification? (shown in white text top-left)
5c. Is the classification CORRECT or WRONG?
5d. What does the crop show vs what it SHOULD show?

---

## SECTION 6: Root Cause Diagnosis
6a. What is the SINGLE PRIMARY reason the reframe fails in the worst moments?
6b. Is the failure caused by: face detection blindness / wrong fallback position / path solver lag / shot misclassification / or something else?
6c. Which pipeline component (face_tracker / focus_resolver / path_solver / gemini_director / keyframe_emitter) is responsible for the most failures?

---

## SECTION 7: Priority Fix List
List the TOP 5 improvements ranked by visual impact:
For each: describe the problem, the timestamp where it's clearest, and what the fix should produce.

---

## SECTION 8: Quality Scores
Score each shot segment 1-10 (10 = perfect vertical reframe, 1 = completely wrong):
Format: [timestamp range] [shot description] → score/10 — one-line reason

Overall pipeline quality score: X/10

---

Be detailed and precise. Your analysis will be used by engineers to fix specific bugs in the pipeline code.
"""


def analyze_debug_video(debug_video_url: str, reframe_job_id: str) -> dict:
    """
    Download the debug video from R2, send to Gemini 2.5 Pro, return structured analysis.

    Returns dict with keys: analysis (str), job_id (str), model (str)
    """
    logger.info("[DebugAnalyzer] Starting analysis for job %s, url=%s", reframe_job_id, debug_video_url)

    temp_path = None
    try:
        # Download debug video to temp file
        suffix = ".mp4"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix,
                                         dir=str(settings.UPLOAD_DIR)) as tmp:
            temp_path = tmp.name

        logger.info("[DebugAnalyzer] Downloading debug video...")
        urllib.request.urlretrieve(debug_video_url, temp_path)
        size_mb = os.path.getsize(temp_path) / (1024 * 1024)
        logger.info("[DebugAnalyzer] Downloaded %.1fMB → %s", size_mb, temp_path)

        # Send to Gemini 2.5 Pro
        from app.services.gemini_client import analyze_video as gemini_analyze_video
        model = settings.GEMINI_MODEL_PRO

        logger.info("[DebugAnalyzer] Sending to Gemini %s...", model)
        raw = gemini_analyze_video(
            video_path=temp_path,
            prompt=_ANALYSIS_PROMPT,
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
