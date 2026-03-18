import json
import re
from app.services.gemini_client import generate_json
from app.pipeline.prompts import pass1_scan, pass2_evaluate, pass3_select
from app.config import settings

def calculate_clip_counts(duration_s: float) -> dict:
    if duration_s < 900:
        return {"min_candidates": 5, "max_candidates": 10, "min_clips": 2, "max_clips": 4}
    elif duration_s < 1800:
        return {"min_candidates": 10, "max_candidates": 18, "min_clips": 3, "max_clips": 5}
    elif duration_s < 3600:
        return {"min_candidates": 15, "max_candidates": 25, "min_clips": 4, "max_clips": 6}
    else:
        return {"min_candidates": 20, "max_candidates": 35, "min_clips": 5, "max_clips": 7}

def _parse_timestamp(ts_str: str) -> float:
    parts = ts_str.replace('[', '').replace(']', '').split(':')
    seconds = 0.0
    try:
        if len(parts) == 3:
            seconds = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            seconds = float(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 1:
            seconds = float(parts[0])
    except (ValueError, TypeError):
        pass
    return seconds

def run(
    fused_timeline: list,
    labeled_transcript: str,
    context: dict,
    channel_dna: dict,
    video_duration_s: float,
    job_id: str
) -> dict:
    
    counts = calculate_clip_counts(video_duration_s)
    
    candidates_list: list[dict] = []
    evaluated_list: list[dict] = []
    selected_list: list[dict] = []
    rejected_list: list[dict] = []

    result = {
        "candidates": candidates_list,
        "evaluated": evaluated_list,
        "selected": selected_list,
        "rejected": rejected_list,
        "clip_counts": counts
    }
    
    # PASS 1: Wide scan
    try:
        formatted_timeline: list[str] = []
        for entry in fused_timeline:
            priority = entry.get("priority", "NORMAL")
            start = entry.get("timestamp_start", 0)
            end = entry.get("timestamp_end", 0)
            raw_text = entry.get("transcript", "")
            text: str = str(raw_text) if raw_text is not None else ""
            text_trunc = text[:100]
            formatted_timeline.append(str(f"[{priority}] {start}s-{end}s: {text_trunc}"))
        fused_timeline_text = "\n".join(formatted_timeline)
        
        prompt1 = pass1_scan.PROMPT
        prompt1 = prompt1.replace("VIDEO_DURATION_PLACEHOLDER", str(video_duration_s))
        prompt1 = prompt1.replace("MIN_CANDIDATES_PLACEHOLDER", str(counts["min_candidates"]))
        prompt1 = prompt1.replace("MAX_CANDIDATES_PLACEHOLDER", str(counts["max_candidates"]))
        prompt1 = prompt1.replace("CHANNEL_DNA_PLACEHOLDER", json.dumps(channel_dna))
        prompt1 = prompt1.replace("GUEST_PROFILE_PLACEHOLDER", json.dumps(context.get("guest_profile", {})))
        prompt1 = prompt1.replace("CHANNEL_MEMORY_PLACEHOLDER", "")
        prompt1 = prompt1.replace("RAG_CONTEXT_PLACEHOLDER", "")
        prompt1 = prompt1.replace("FUSED_TIMELINE_PLACEHOLDER", fused_timeline_text)
        
        pass1_out = generate_json(prompt1)
        if isinstance(pass1_out, list):
            candidates_list = pass1_out
            result["candidates"] = candidates_list
        else:
            print("[S08] Pass 1 returned non-list output")
            return result
            
        print(f"[S08] Pass 1: found {len(candidates_list)} candidates")
    except Exception as e:
        print(f"[S08] Error in Pass 1: {e}")
        return result
        
    if not result["candidates"]:
        return result
        
    # PASS 2: Deep evaluation
    try:
        transcript_lines = labeled_transcript.split('\n')
        
        chunk_size = 4
        for i in range(0, len(candidates_list), chunk_size):
            batch = candidates_list[i:i + chunk_size]
            
            batch_data = []
            for candidate in batch:
                cand_id = candidate.get("candidate_id", "unknown")
                ts_str = candidate.get("timestamp", "00:00")
                target_s = _parse_timestamp(ts_str)
                
                # Extract +/- 2 minute context window
                window_lines = []
                for line in transcript_lines:
                    match = re.match(r'^\[([\d:\.]+)\]', line)
                    if match:
                        line_s = _parse_timestamp(match.group(1))
                        if target_s - 120 <= line_s <= target_s + 120:
                            window_lines.append(line)
                            
                context_window_text = "\n".join(window_lines)
                
                # Match signals from fused_timeline
                matching_signals = []
                for entry in fused_timeline:
                    start = entry.get("timestamp_start", 0)
                    end = entry.get("timestamp_end", 0)
                    # Include if within 30s of the target or overlapping
                    if start <= target_s <= end or (target_s - 30 <= start <= target_s + 30):
                        matching_signals.append(entry)
                        
                batch_data.append({
                    "candidate_id": cand_id,
                    "timestamp": ts_str,
                    "context_window": context_window_text,
                    "signals": matching_signals
                })
                
            try:
                prompt2 = pass2_evaluate.PASS2_EVALUATE_PROMPT
                prompt2 = prompt2.replace("CHANNEL_DNA_PLACEHOLDER", json.dumps(channel_dna))
                prompt2 = prompt2.replace("CHANNEL_MEMORY_PLACEHOLDER", "")
                prompt2 = prompt2.replace("RAG_CONTEXT_PLACEHOLDER", "")
                prompt2 = prompt2.replace("BATCH_CANDIDATES_DATA_PLACEHOLDER", json.dumps(batch_data))
                
                pass2_out = generate_json(prompt2, model=settings.GEMINI_MODEL_PRO)
                if isinstance(pass2_out, list):
                    for item in pass2_out:
                        if isinstance(item, dict):
                            evaluated_list.append(item)
                else:
                    print(f"[S08] Pass 2 batch {(i//chunk_size)+1} returned non-list")
            except Exception as e:
                print(f"[S08] Error evaluating batch {(i//chunk_size)+1}: {e}")
                continue
                
        print(f"[S08] Pass 2: evaluated {len(evaluated_list)} candidates")
    except Exception as e:
        print(f"[S08] Error in Pass 2: {e}")
        
    if not evaluated_list:
        return result
        
    # PASS 3: Final selection
    try:
        prompt3 = pass3_select.PROMPT
        prompt3 = prompt3.replace("CHANNEL_DNA_PLACEHOLDER", json.dumps(channel_dna))
        prompt3 = prompt3.replace("EVALUATED_CANDIDATES_PLACEHOLDER", json.dumps(result["evaluated"]))
        prompt3 = prompt3.replace("MIN_CLIPS_PLACEHOLDER", str(counts["min_clips"]))
        prompt3 = prompt3.replace("MAX_CLIPS_PLACEHOLDER", str(counts["max_clips"]))
        
        pass3_out = generate_json(prompt3, model=settings.GEMINI_MODEL_PRO)
        if isinstance(pass3_out, dict):
            result["selected"] = pass3_out.get("selected_clips", [])
            result["rejected"] = pass3_out.get("rejected_clips", [])
            
        print(f"[S08] Pass 3: selected {len(result['selected'])} clips")
    except Exception as e:
        print(f"[S08] Error in Pass 3: {e}")
        
    return result
