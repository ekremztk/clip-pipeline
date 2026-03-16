import json
from app.services.gemini_client import generate_json
from app.pipeline.prompts.standalone_check import PROMPT
from app.config import settings

def run(selected_clips: list, evaluated_clips: list, labeled_transcript: str, job_id: str) -> list:
    """
    Step 9: Quality Gate
    Filters and annotates selected clips based on structural and standalone meaning checks.
    """
    print(f"[S09] Starting quality gate for job {job_id} with {len(selected_clips)} clips")
    
    # Pre-process labeled transcript lines for faster lookup
    # labeled_transcript is a string with lines like "[00:00:15.500] Speaker 1: Hello"
    # Wait, the instruction says:
    # "Extract clip transcript from labeled_transcript (lines where timestamp is between recommended_start and recommended_end)"
    # A generic approach to extract lines between start and end seconds:
    transcript_lines = labeled_transcript.strip().split("\n") if labeled_transcript else []
    
    parsed_transcript = []
    for line in transcript_lines:
        line = line.strip()
        if not line:
            continue
        try:
            # Parse timestamp e.g. [00:00:15.500]
            if line.startswith("[") and "]" in line:
                ts_str = line[1:line.find("]")]
                parts = ts_str.split(":")
                if len(parts) == 3:
                    h, m, s = parts
                    total_seconds = int(h) * 3600 + int(m) * 60 + float(s)
                    parsed_transcript.append({"time": total_seconds, "text": line})
        except Exception as e:
            pass # Ignore malformed lines
    
    results = []
    
    # Metrics
    passed_count = 0
    fixable_count = 0
    failed_count = 0
    
    # We need a quick lookup map for evaluated_clips by candidate_id
    eval_map = {c.get("candidate_id"): c for c in evaluated_clips if "candidate_id" in c}
    
    for clip in selected_clips:
        try:
            candidate_id = clip.get("candidate_id")
            eval_data = eval_map.get(candidate_id, {})
            
            # Use data from clip directly if present, fallback to eval_data
            start = clip.get("recommended_start", eval_data.get("recommended_start", 0))
            end = clip.get("recommended_end", eval_data.get("recommended_end", 0))
            overall_confidence = clip.get("overall_confidence", eval_data.get("overall_confidence", 0))
            standalone_score = clip.get("standalone_score", eval_data.get("standalone_score", 0))
            hook_text = clip.get("hook_text", eval_data.get("hook_text"))
            
            # --- PART 1: Structural validation ---
            duration = end - start
            fail_reason = None
            
            if duration < 15:
                fail_reason = f"Duration too short ({duration:.1f}s < 15s)"
            elif duration > 50:
                fail_reason = f"Duration too long ({duration:.1f}s > 50s)"
            elif start < 0:
                fail_reason = f"Invalid start time ({start})"
            elif end <= start:
                fail_reason = f"End time <= start time ({end} <= {start})"
            elif standalone_score < 4:
                fail_reason = f"Standalone score too low ({standalone_score} < 4)"
            elif not hook_text or len(str(hook_text).strip()) <= 3:
                fail_reason = "Missing or empty hook text"
            
            if overall_confidence < 0.4:
                print(f"[S09] Warning: Clip {candidate_id} has low confidence ({overall_confidence})")
                
            if fail_reason:
                print(f"[S09] Clip {candidate_id} rejected (structural): {fail_reason}")
                clip["quality_status"] = "structural_fail"
                clip["quality_note"] = fail_reason
                failed_count += 1
                results.append(clip)
                continue
                
            # --- PART 2: Standalone meaning check ---
            
            # Extract transcript segment
            clip_transcript_lines = []
            for item in parsed_transcript:
                if start <= item["time"] <= end:
                    clip_transcript_lines.append(item["text"])
            
            clip_transcript_str = "\n".join(str(x) for x in clip_transcript_lines)
            
            if not clip_transcript_str.strip():
                # No transcript found, maybe silent or bad timestamps
                print(f"[S09] Clip {candidate_id} rejected (standalone): No transcript found between {start} and {end}")
                clip["quality_status"] = "structural_fail"
                clip["quality_note"] = "Empty transcript"
                failed_count += 1
                results.append(clip)
                continue
            
            prompt = PROMPT.replace("CLIP_TRANSCRIPT_PLACEHOLDER", clip_transcript_str)
            gemini_res = generate_json(prompt)
            
            overall = gemini_res.get("overall", "fail")
            note = gemini_res.get("note", "")
            
            clip["standalone_result"] = gemini_res
            
            if overall == "fail":
                clip["quality_status"] = "standalone_fail"
                clip["quality_note"] = note or "Standalone check failed"
                print(f"[S09] Clip {candidate_id} rejected (standalone): {clip['quality_note']}")
                failed_count += 1
            elif overall == "fixable":
                clip["quality_status"] = "fixable"
                clip["standalone_fix"] = note
                print(f"[S09] Clip {candidate_id} fixable (standalone): {note}")
                fixable_count += 1
            elif overall == "pass":
                clip["quality_status"] = "pass"
                print(f"[S09] Clip {candidate_id} passed standalone check")
                passed_count += 1
            else:
                clip["quality_status"] = "standalone_fail"
                clip["quality_note"] = f"Unknown overall status: {overall}"
                print(f"[S09] Clip {candidate_id} rejected (standalone): Unknown status {overall}")
                failed_count += 1
            
            results.append(clip)
            
        except Exception as e:
            print(f"[S09] Error processing clip {clip.get('candidate_id')}: {e}")
            clip["quality_status"] = "structural_fail"
            clip["quality_note"] = f"Error: {str(e)}"
            failed_count += 1
            results.append(clip)
            
    # Sort results: pass first, then fixable, then failed
    status_order = {"pass": 0, "fixable": 1, "structural_fail": 2, "standalone_fail": 2}
    results.sort(key=lambda x: status_order.get(x.get("quality_status", "structural_fail"), 3))
    
    print(f"[S09] Summary: {passed_count} passed, {fixable_count} fixable, {failed_count} failed.")
    
    return results
