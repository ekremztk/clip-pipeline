def seconds_to_srt_time(seconds: float) -> str:
    """Converts float seconds to SRT timestamp format: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_srt(words: list, clip_start: float, clip_end: float, max_chars_per_line: int = 42) -> str:
    """
    Generates SRT subtitle content from Deepgram word-level timestamps.

    Args:
        words: List of word dicts with 'start', 'end', 'punctuated_word'/'word' keys
        clip_start: Clip start time in seconds (used to filter and offset timestamps)
        clip_end: Clip end time in seconds
        max_chars_per_line: Max characters per subtitle line before wrapping

    Returns:
        SRT formatted string
    """
    # Filter words within the clip window (with small tolerance)
    tolerance = 0.05
    clip_words = [
        w for w in words
        if w.get("start", 0) >= (clip_start - tolerance)
        and w.get("end", 0) <= (clip_end + tolerance)
    ]

    if not clip_words:
        return ""

    # Group words into subtitle blocks (~5 seconds or max_chars_per_line)
    blocks = []
    current_block = []
    current_chars = 0
    block_start = None
    block_end = None
    max_block_duration = 5.0

    for word in clip_words:
        word_text = word.get("punctuated_word", word.get("word", ""))
        word_start = word.get("start", 0)
        word_end = word.get("end", 0)

        if block_start is None:
            block_start = word_start

        new_chars = len(word_text) + (1 if current_block else 0)
        block_duration = word_end - block_start

        # Start new block if too long or too wide
        if current_block and (
            current_chars + new_chars > max_chars_per_line
            or block_duration > max_block_duration
        ):
            blocks.append({
                "start": block_start - clip_start,
                "end": block_end - clip_start,
                "text": " ".join(current_block)
            })
            current_block = []
            current_chars = 0
            block_start = word_start

        current_block.append(word_text)
        current_chars += new_chars
        block_end = word_end

    # Flush last block
    if current_block and block_start is not None:
        blocks.append({
            "start": block_start - clip_start,
            "end": block_end - clip_start,
            "text": " ".join(current_block)
        })

    # Build SRT string
    lines = []
    for i, block in enumerate(blocks, 1):
        start_ts = seconds_to_srt_time(max(0.0, block["start"]))
        end_ts = seconds_to_srt_time(max(0.0, block["end"]))
        lines.append(str(i))
        lines.append(f"{start_ts} --> {end_ts}")
        lines.append(block["text"])
        lines.append("")

    return "\n".join(lines)
