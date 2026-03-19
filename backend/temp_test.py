from app.pipeline.steps import s08_clip_finder
from app.pipeline.steps import s07b_humor_map

# Test setup
channel_dna = {
    "do_list": ["Talk about recent AI developments", "Mention specific code frameworks"],
    "best_content_types": ["code_tutorial", "ai_debate", "tech_news", "funny_reaction"],
    "humor_profile": {
        "style": "none",
        "frequency": "none",
        "triggers": []
    }
}

fused_timeline = [
    {"priority": "TRIPLE", "timestamp_start": 0, "timestamp_end": 10, "transcript": "Hello"}
]
labeled_transcript = "[00:00:00] Hello\n[00:00:10] World"
context = {}
video_duration_s = 600

# Testing S08
def mock_generate_json(prompt, model=None):
    if "Evaluate EACH candidate clip in the batch by answering the following 7 questions for each one" in prompt:
        print("----- PASS 2 PROMPT (CONTENT TYPES CHECK) -----")
        lines = prompt.split('\n')
        for i, line in enumerate(lines):
            if "CONTENT TYPE:" in line:
                print(lines[i])
                print(lines[i+1])
        print("---------------------------------")
        return [{"candidate_id": 1, "recommended_start": 0.0, "recommended_end": 10.0, "duration_s": 10.0}]

    elif "Find up to MAX_CANDIDATES_PLACEHOLDER" in prompt or "CANDIDATES TARGET:" in prompt:
        print("----- PASS 1 PROMPT (DO LIST CHECK) -----")
        lines = prompt.split('\n')
        for i, line in enumerate(lines):
            if "CHANNEL-SPECIFIC PRIORITIES" in line:
                print(lines[i])
                print(lines[i+1])
                print(lines[i+2])
        print("---------------------------------")
        return [{"candidate_id": 1, "timestamp": "00:00", "reason": "test", "signal": "multi", "strength": 9}]

    return {"selected_clips": [], "rejected_clips": []}

s08_clip_finder.generate_json = mock_generate_json

print("Running S08 mock...")
s08_clip_finder.run(
    fused_timeline=fused_timeline,
    labeled_transcript=labeled_transcript,
    context=context,
    channel_dna=channel_dna,
    video_duration_s=video_duration_s,
    job_id="test_job"
)
