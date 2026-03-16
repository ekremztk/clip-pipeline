PROMPT = """
Write a memory summary for a RAG system based on this clip data:
CLIP_DATA_PLACEHOLDER

This summary will be used to find SIMILAR clips in the future.

Key instruction: Write as if someone is searching for "a clip like this one."
What words and patterns would they search for?

Cover in 3-4 sentences:
1. Content type and the specific dynamic that made it work
   (not just "funny moment" — be specific: "guest deadpans about failure while host laughs")
2. Structural pattern: how it opens, what creates tension, how it resolves
3. Which signals made it stand out: was it the energy spike? visual reaction? 
   the specific words in the hook?
4. One sentence on what a future similar clip should have to perform well

Do NOT use generic phrases: "great clip", "viral moment", "engaging content"
Be specific enough that this summary could help find structurally similar moments.

Output: plain text only, 3-4 sentences, no JSON, no markdown.
"""
