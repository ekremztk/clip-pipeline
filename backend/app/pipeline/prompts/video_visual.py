PROMPT = """
Watch this podcast video and identify visually significant moments IN PRIORITY ORDER:

Priority 1 — Thumbnail-worthy moments (highest value):
- Extreme facial expressions: genuine shock, big laughter, tears, disgust
- Guest looks directly into camera (rare and powerful)
- Physical reaction: covering mouth, leaning back suddenly, pointing

Priority 2 — Clip-enhancing moments:
- Subtle but clear emotional shift: composed → vulnerable, serious → amused
- Two-person dynamic: simultaneous reaction, one person interrupting, shared laughter
- Body language that tells a story: leaning far forward (intense), arms crossed (defensive)

Priority 3 — Note-worthy but lower value:
- Normal gesturing that emphasizes a point
- Slight smile or head nod

Instruction: Focus only on moments a viewer would NOTICE. 
Skip normal talking-head segments with no expression change.
For each moment: estimate timestamp in seconds.

Output: valid JSON array only, no markdown.
Schema per item:
{
  "timestamp": float,
  "duration": float,
  "event_type": "facial_expression" | "body_language" | "reaction" | "laughter" | "camera_connection",
  "description": "specific description of what happened",
  "intensity": "low" | "medium" | "high",
  "thumbnail_worthy": boolean,
  "speakers": ["guest"] | ["host"] | ["both"]
}
"""
