import json
from app.services.gemini_client import generate_json
from app.pipeline.prompts import pass3_select
from app.services.supabase_client import get_client

def run(quality_results: list, evaluated_clips: list, channel_dna: dict, job_id: str) -> list:
    """
    Assigns a strategy role and posting order to each clip that passed quality gate.
    """
    try:
        # 1. Filter quality_results to only clips with quality_status "pass" or "fixable"
        passing_clips = [c for c in quality_results if c.get("quality_status") in ("pass", "fixable")]
        
        # 2. If no clips passed: return empty list with [S09B] log
        if not passing_clips:
            print("[S09B] No clips passed quality gate. Returning empty list.")
            return []
            
        # 3. Merge each passing clip with its full evaluation data from evaluated_clips (match by candidate_id)
        merged_clips = []
        eval_dict = {c.get("candidate_id"): c for c in evaluated_clips}
        
        for p_clip in passing_clips:
            c_id = p_clip.get("candidate_id")
            if c_id in eval_dict:
                merged_clip = {**eval_dict[c_id], **p_clip}
                merged_clips.append(merged_clip)
            else:
                merged_clips.append(p_clip)

        # 4. Build prompt from pass3_select.PROMPT replacing placeholders
        prompt = pass3_select.PROMPT
        prompt = prompt.replace("CHANNEL_DNA_PLACEHOLDER", json.dumps(channel_dna))
        prompt = prompt.replace("EVALUATED_CANDIDATES_PLACEHOLDER", json.dumps(merged_clips))
        prompt = prompt.replace("MIN_CLIPS_PLACEHOLDER", str(max(2, len(passing_clips) // 2)))
        prompt = prompt.replace("MAX_CLIPS_PLACEHOLDER", str(len(passing_clips)))

        # 5. Call generate_json(prompt)
        print(f"[S09B] Evaluating {len(passing_clips)} clips for strategy and posting order...")
        response = generate_json(prompt)
        
        # 6. Parse result: selected_clips and rejected_clips
        selected_clips_info = response.get("selected_clips", [])
        
        # Map selected info by candidate_id
        strategy_dict = {
            item.get("candidate_id"): item 
            for item in selected_clips_info
        }

        final_clips = []
        
        # 7. For each selected clip: add clip_strategy_role and posting_order to the clip data
        for clip in merged_clips:
            c_id = clip.get("candidate_id")
            if c_id in strategy_dict:
                strat_info = strategy_dict[c_id]
                clip["clip_strategy_role"] = strat_info.get("clip_strategy_role", "viral")
                clip["posting_order"] = strat_info.get("posting_order", 999)
                clip["selection_reason"] = strat_info.get("selection_reason", "")
                final_clips.append(clip)

        # 8. Return final list sorted by posting_order ascending
        final_clips.sort(key=lambda x: x.get("posting_order", 999))
        
        print(f"[S09B] Received {len(passing_clips)} clips, {len(final_clips)} selected with roles.")
        return final_clips

    except Exception as e:
        print(f"[S09B] Error: {e}")
        # Full try/except — if Gemini fails, return passing clips without strategy
        fallback_clips = []
        for i, clip in enumerate(passing_clips):
            c_id = clip.get("candidate_id")
            # Try to get evaluation data if available
            eval_data = next((c for c in evaluated_clips if c.get("candidate_id") == c_id), {})
            merged = {**eval_data, **clip}
            merged["clip_strategy_role"] = "viral"
            merged["posting_order"] = i + 1
            merged["selection_reason"] = "Fallback assignment"
            fallback_clips.append(merged)
        
        print(f"[S09B] Fallback triggered. Returning {len(fallback_clips)} clips with default strategy.")
        return fallback_clips
