PROMPT = """
Research this person: GUEST_NAME_PLACEHOLDER

Your goal is to find information that would make their podcast appearance MORE clip-worthy.

Research areas:
1. Who are they in one sentence?
2. What have they been in the news for in the last 30 days?
   (This is gold — if they say something connected to current news, it is a top clip)
3. What are their most known viral moments or controversial quotes?
   (Pattern match: if they repeat a known pattern, that moment will resonate)
4. What topics are they known to be controversial or opinionated about?
   (These moments have high shareability)
5. What are their expertise areas?
   (Helps identify when they say something surprising or outside their domain)

Tone instruction in prompt: Be specific and factual. 
If the person is not well known, say so clearly — do not fabricate.

Output: valid JSON only, no markdown.
Schema:
{
  "profile_summary": "one sentence",
  "recent_topics": ["topic1", "topic2"],
  "viral_moments": ["moment1"],
  "controversies": ["topic1"],
  "expertise_areas": ["area1"],
  "clip_potential_note": "one sentence: what type of moment from this guest would be most viral on YouTube Shorts"
}
"""
