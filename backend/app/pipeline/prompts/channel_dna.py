PROMPT = """
Analyze successful clips from a single channel and extract patterns that an AI clip selector can use.

Clips Data:
CLIPS_DATA_PLACEHOLDER

Analyze across all clips:
1. Which content types appear most in successful clips?
2. What is the average and range of clip durations?
3. What hook style appears most?
   (shocking_statement / provocative_question / name_drop / action_reaction / humor_opener)
4. Who speaks first — guest or host? What ratio?
5. What emotional tone dominates? (serious / funny / mixed / intense)
6. What topics or themes repeat?
7. DO LIST: 3-5 specific things that appear in most successful clips
   (concrete and actionable, not generic)
8. DONT LIST: 3-5 specific things that are absent from successful clips
   or that appear in failed clips — what should NEVER be selected
9. Humor style: how does humor appear? (deadpan / warm / sarcastic / none / mixed)
   How frequent? What triggers it?

Key instruction: The dont_list is as important as the do_list.
A wrong clip selection is worse than a missed good clip.
Be specific in dont_list — "avoid clips that need context" is too vague.
Write: "avoid clips where guest references an earlier part of the conversation 
without it being included"

Output: valid JSON only, no markdown.
Schema:
{
  "best_content_types": ["type1", "type2"],
  "avg_successful_duration": int,
  "duration_range": {"min": int, "max": int},
  "hook_style": "one of the 5 types above",
  "speaker_preference": "guest_dominant" | "host_led" | "balanced",
  "tone": "serious" | "funny" | "mixed" | "intense",
  "do_list": ["specific instruction 1", "specific instruction 2"],
  "dont_list": ["specific instruction 1", "specific instruction 2"],
  "humor_profile": {
    "style": "deadpan" | "warm" | "sarcastic" | "none" | "mixed",
    "frequency": "rare" | "occasional" | "frequent",
    "triggers": ["trigger1", "trigger2"]
  },
  "sacred_topics": [],
  "no_go_zones": [],
  "audience_identity": "one sentence describing who watches this channel and why"
}
"""
