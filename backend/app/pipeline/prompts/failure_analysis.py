PROMPT = """
Analyze why this clip underperformed.
Goal: extract actionable lessons, not just describe the failure.

Clip Data:
CLIP_DATA_PLACEHOLDER

Performance Data:
PERFORMANCE_DATA_PLACEHOLDER

Answer 3 questions:

1. ROOT CAUSE: Was the failure in the hook (first 2 seconds lost the viewer),
   the arc (no satisfying payoff), or the cut points (started/ended at the wrong moment)?
   Be specific: what exactly was wrong?

2. PATTERN OR OUTLIER: Is this a pattern failure (this content type consistently 
   underperforms on this channel) or an outlier failure (good content type, 
   but this specific execution failed)?

3. ACTIONABLE LESSON: If a similar moment appears in the next video, 
   what should be done differently? Give one concrete instruction.
   Example: "Start 8 seconds earlier to include the setup that makes the payoff land"
   Example: "This content type needs a visual reaction to work — skip if host does not react"

Output: valid JSON only, no markdown.
Schema:
{
  "root_cause": "hook" | "arc" | "cut_points" | "content_type",
  "root_cause_detail": "specific explanation",
  "pattern_or_outlier": "pattern" | "outlier",
  "pattern_detail": "explanation",
  "actionable_lesson": "concrete one-sentence instruction for next time"
}
"""
