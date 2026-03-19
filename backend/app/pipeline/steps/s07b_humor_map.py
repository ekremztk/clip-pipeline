from app.services.gemini_client import generate_json
from app.pipeline.prompts.humor_map import PROMPT

def run(labeled_transcript: str, channel_dna: dict, job_id: str) -> list[dict]:
    """
    Uses Gemini to find humor moments in the transcript,
    including subtle types that audio energy cannot detect.
    Processes long transcripts in chunks to avoid missing content.
    """
    try:
        print(f"[S07B] Starting humor map for {job_id}...")

        humor_profile = channel_dna.get("humor_profile", {})
        style = humor_profile.get("style", "general")
        triggers = humor_profile.get("triggers", [])

        # Process in chunks with overlap
        chunk_size = 10000
        overlap = 1000
        all_moments = []

        transcript_length = len(labeled_transcript)
        if transcript_length == 0:
            print(f"[S07B] Empty transcript for {job_id}")
            return []

        chunk_start = 0
        chunk_index = 0
        while chunk_start < transcript_length:
            chunk_end = min(chunk_start + chunk_size, transcript_length)
            chunk = labeled_transcript[chunk_start:chunk_end]

            # Avoid cutting mid-line: extend to next newline
            if chunk_end < transcript_length:
                next_newline = labeled_transcript.find("\n", chunk_end)
                if next_newline != -1 and next_newline - chunk_end < 200:
                    chunk = labeled_transcript[chunk_start:next_newline]
                    chunk_end = next_newline

            prompt = PROMPT
            prompt = prompt.replace("TRANSCRIPT_PLACEHOLDER", chunk)
            prompt = prompt.replace("STYLE_PLACEHOLDER", str(style))
            prompt = prompt.replace("TRIGGERS_PLACEHOLDER", str(triggers))

            try:
                result = generate_json(prompt)
                if isinstance(result, list):
                    all_moments.extend(result)
                elif isinstance(result, dict) and "moments" in result:
                    all_moments.extend(result["moments"])
            except Exception as chunk_err:
                print(f"[S07B] Error in chunk {chunk_index}: {chunk_err}")

            chunk_index += 1
            chunk_start = chunk_end - overlap if chunk_end < transcript_length else transcript_length

        # Deduplicate by timestamp proximity (within 5 seconds = same moment)
        unique_moments = []
        for moment in all_moments:
            ts = moment.get("timestamp")
            if ts is None:
                continue
            try:
                ts_float = float(str(ts))
            except (ValueError, TypeError):
                continue

            is_duplicate = False
            for existing in unique_moments:
                existing_ts = float(str(existing.get("timestamp", 0)))
                if abs(ts_float - existing_ts) < 5.0:
                    # Keep the one with higher confidence
                    if float(str(moment.get("confidence", 0))) > float(str(existing.get("confidence", 0))):
                        unique_moments.remove(existing)
                        unique_moments.append(moment)
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique_moments.append(moment)

        print(f"[S07B] Found {len(unique_moments)} humor moments ({len(all_moments)} raw, {chunk_index} chunks) for {job_id}")
        return unique_moments

    except Exception as e:
        print(f"[S07B] Error: {e}")
        return []
