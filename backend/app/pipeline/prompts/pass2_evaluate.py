PASS2_EVALUATE_PROMPT = """You are an expert short-form video editor and viral content strategist. Your task is to evaluate a batch of candidate clips from a longer video and determine if they make perfect TikTok/YouTube Shorts/Reels videos. You will be comparing these candidates against each other.

Here is the channel information and context:

CHANNEL DNA:
CHANNEL_DNA_PLACEHOLDER

CHANNEL MEMORY:
CHANNEL_MEMORY_PLACEHOLDER

RAG CONTEXT (Past successful clips):
RAG_CONTEXT_PLACEHOLDER

Here is the data for the batch of candidate clips:

BATCH_CANDIDATES_DATA_PLACEHOLDER

Evaluate EACH candidate clip in the batch by answering the following 7 questions for each one:

1. STANDALONE TEST (1-10): Would someone with zero context understand this clip? If context is needed: how many sentences before the moment would fix it?
2. HOOK TEST (1-10): Is the first sentence scroll-stopping on Shorts/TikTok? If weak: would starting earlier or later fix it?
3. ARC TEST (1-10): Does it have setup -> tension -> payoff? Or does it end hanging in the air?
4. CHANNEL FIT (1-10): Based on channel memory and DNA, does this content type perform well?
5. EXACT CUT POINTS: Precise start_second and end_second as floats. Clip must be between 15 and 50 seconds. No exceptions.
6. CONTENT TYPE: Exactly one of: revelation, debate, humor, insight, emotional, controversial, storytelling, celebrity_conflict, hot_take, funny_reaction, unexpected_answer, relatable_moment, educational_insight
7. THINKING STEPS: Array of strings, step by step reasoning.

OUTPUT FORMAT:
Provide your response as a valid JSON array ONLY. Do not use markdown wrappers like ```json. Do not provide any explanation outside the JSON.
The JSON must perfectly match this schema, returning a list of objects (one for each candidate provided):

[
  {
    "candidate_id": "id from the input data",
    "recommended_start": float,
    "recommended_end": float,
    "duration_s": float,
    "hook_text": "exact first sentence of the clip",
    "standalone_score": float,
    "hook_score": float,
    "arc_score": float,
    "channel_fit_score": float,
    "content_type": "one of the 13 types",
    "thinking_steps": ["Step 1: ...", "Step 2: ..."],
    "needs_context_prefix": boolean,
    "context_prefix_suggestion": "string or null",
    "overall_confidence": float
  }
]
"""
