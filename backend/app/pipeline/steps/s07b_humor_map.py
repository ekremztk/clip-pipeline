from app.services.gemini_client import generate_json
from app.pipeline.prompts.humor_map import PROMPT

def run(labeled_transcript: str, channel_dna: dict, job_id: str) -> list[dict]:
    """
    Uses Gemini to find humor moments in the transcript, 
    including subtle types that audio energy cannot detect.
    """
    try:
        print(f"[S07B] Starting humor map for {job_id}...")
        
        # Extract humor profile
        humor_profile = channel_dna.get("humor_profile", {})
        style = humor_profile.get("style", "general")
        triggers = humor_profile.get("triggers", [])
        
        # Truncate transcript to 12000 chars
        truncated_transcript = labeled_transcript[:12000]
        
        # Build prompt
        prompt = PROMPT
        prompt = prompt.replace("TRANSCRIPT_PLACEHOLDER", truncated_transcript)
        prompt = prompt.replace("STYLE_PLACEHOLDER", str(style))
        prompt = prompt.replace("TRIGGERS_PLACEHOLDER", str(triggers))
        
        # Call Gemini
        result = generate_json(prompt)
        
        # Parse result
        # Assuming the result is a list of humor moments or a dict with a list
        if isinstance(result, list):
            humor_moments = result
        elif isinstance(result, dict) and "moments" in result:
            humor_moments = result["moments"]
        else:
            humor_moments = []
            
        print(f"[S07B] Found {len(humor_moments)} humor moments for {job_id}")
        return humor_moments
        
    except Exception as e:
        print(f"[S07B] Error: {e}")
        return []
