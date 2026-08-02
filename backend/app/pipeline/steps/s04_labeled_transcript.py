"""
S04 — Canonical labeled transcript.

Turns Deepgram utterances into the single text representation every downstream
AI step reads. Three properties matter here, and each one used to be broken:

  * Both `start` AND `end` are emitted. Deepgram gives both; this step used to
    drop `end`, while the S05 prompt asked the model for an exact end timestamp.
    The only precise number left in its input was the *next* utterance's start,
    so that is what it returned — producing clips that ran seconds past the last
    spoken word.
  * Every utterance carries a stable `U####` id, so downstream steps can name a
    boundary instead of inventing a millisecond value.
  * Speaker labels never claim more certainty than they have. A name appears only
    when the voice library actually matched it; heuristic clusters get a neutral
    SPEAKER_x, and the header says plainly that the ids are unreliable.
"""

# Deepgram splits a turn whenever the speaker pauses, leaving runs of 1-3 word
# backchannel fragments ("No." / "Yeah." / "What?") that add lines without adding
# meaning. Those get folded into the neighbouring turn.
#
# The bounds below are deliberately tight. An earlier version merged any
# same-speaker pair under a 2s gap and produced 44-second blocks — longer than
# the clips themselves — which cost S05 the ability to name a boundary inside a
# turn. On the Sofia source that collapsed the whole Ed O'Neill payoff into one
# unsplittable block, and the boundary that made the published clip work sat in
# the middle of it. Readability is worth having; boundary precision is worth more.
_MERGE_GAP_SECONDS = 2.0
_MERGE_MAX_WORDS = 4        # only absorb fragments this short
_MERGE_MAX_DURATION = 12.0  # never grow a turn past this

_HEADER = """## HOW TO READ THIS TRANSCRIPT
Each line is: [utterance-id start-end] SPEAKER: text

Speaker ids come from automatic diarization and are NOT reliable. The same person
can appear under more than one id, and an id carries no meaning beyond "this
sounded like a different voice". Work out who is the host and who is the guest
from what they say, not from the labels. A label showing a real name has been
confirmed against a voice sample; a SPEAKER_x label has not been identified.
"""


def _fmt_ts(sec: float) -> str:
    return f"{int(sec // 60):02d}:{sec % 60:05.2f}"


def _speaker_letters(utterances: list) -> dict:
    """Map raw Deepgram speaker ids to stable A, B, C… labels."""
    seen: list[str] = []
    for utt in utterances:
        raw = str(utt.get("speaker", ""))
        if raw not in seen:
            seen.append(raw)

    def sort_key(raw: str):
        try:
            return (0, int(raw))
        except (TypeError, ValueError):
            return (1, raw)

    letters = {}
    for idx, raw in enumerate(sorted(seen, key=sort_key)):
        suffix = chr(ord("A") + idx) if idx < 26 else str(idx + 1)
        letters[raw] = f"SPEAKER_{suffix}"
    return letters


def _resolve_label(raw_speaker, speaker_map: dict, letters: dict) -> str:
    """
    A confirmed name wins; otherwise the neutral letter.

    S03 sets `name` only when the voice library matched the speaker, so a
    non-empty name here means verified, never guessed. The previous version
    pasted the user-typed target guest onto whichever cluster the heuristic
    happened to call GUEST, presenting a guess as fact.
    """
    info = (
        speaker_map.get(raw_speaker)
        or speaker_map.get(str(raw_speaker))
        or speaker_map.get(f"SPEAKER_{raw_speaker}")
        or {}
    )
    name = (info.get("name") or "").strip()
    if name:
        return name.upper()
    return letters.get(str(raw_speaker), "SPEAKER_?")


def _sentiment_tag(utt: dict) -> str:
    raw = utt.get("sentiment_score") or utt.get("sentiment")
    if raw is None:
        return ""
    try:
        score = float(raw)
    except (ValueError, TypeError):
        return ""
    return f" [sentiment:{score:.2f}]" if abs(score) > 0.3 else ""


def run(
    transcript_data: dict,
    speaker_map: dict,
    target_guest: str | None = None,
    scene_ranges: list[tuple[float, float]] | None = None,
    video_title: str = "",
) -> str:
    """
    Args:
        transcript_data: s02 output; must contain 'utterances' with start/end/text.
        speaker_map: s03 predicted_map. `name` is populated only on a verified
            voice match.
        target_guest: accepted for signature compatibility and deliberately NOT
            used to label speakers — see _resolve_label.
        scene_ranges: optional (start, end) tuples in episode seconds. When given,
            only utterances starting inside a range are emitted and each range gets
            a `[Scene N — …]` header so S05 can see where the cuts are. Timestamps
            stay absolute.
        video_title: source title, surfaced in the header so the model knows who is
            likely in the episode without being told which speaker id they are.

    Returns:
        Full labeled transcript as a single string.
    """
    try:
        if not transcript_data:
            raise RuntimeError("transcript_data is empty")

        utterances = transcript_data.get("utterances", [])
        if not utterances:
            raise RuntimeError("No utterances found in transcript_data")

        letters = _speaker_letters(utterances)

        def scene_for(start_sec: float):
            if not scene_ranges:
                return None
            for idx, (s, e) in enumerate(scene_ranges):
                if s <= start_sec < e:
                    return idx
            return None

        # Pass 1 — collect what we will emit, numbering in source order so ids
        # stay stable whether or not the scene filter is active.
        kept = []
        for seq, utt in enumerate(utterances, start=1):
            text = (utt.get("transcript") or "").strip()
            if not text:
                continue

            start_sec = float(utt.get("start", 0.0))
            end_sec = float(utt.get("end", start_sec))

            scene_idx = None
            if scene_ranges is not None:
                scene_idx = scene_for(start_sec)
                if scene_idx is None:
                    continue

            kept.append({
                "uid": f"U{seq:04d}",
                "last_uid": f"U{seq:04d}",
                "start": start_sec,
                "end": end_sec,
                "speaker": str(utt.get("speaker", "")),
                "label": _resolve_label(utt.get("speaker", ""), speaker_map, letters),
                "text": text,
                "sentiment": _sentiment_tag(utt),
                "scene": scene_idx,
            })

        # Pass 2 — absorb short backchannel fragments into the turn they belong to.
        merged: list[dict] = []
        for item in kept:
            prev = merged[-1] if merged else None
            same_turn = (
                prev is not None
                and prev["speaker"] == item["speaker"]
                and prev["scene"] == item["scene"]
                and (item["start"] - prev["end"]) < _MERGE_GAP_SECONDS
                and len(item["text"].split()) <= _MERGE_MAX_WORDS
                and (item["end"] - prev["start"]) <= _MERGE_MAX_DURATION
            )
            if same_turn:
                prev["end"] = item["end"]
                prev["last_uid"] = item["uid"]
                prev["text"] = f"{prev['text']} {item['text']}"
                if not prev["sentiment"]:
                    prev["sentiment"] = item["sentiment"]
            else:
                merged.append(item)

        # Pass 3 — render.
        lines = [_HEADER]
        if video_title:
            lines.append(f"Source video title: {video_title}\n")

        current_scene = None
        for item in merged:
            if scene_ranges is not None and item["scene"] != current_scene:
                s, e = scene_ranges[item["scene"]]
                lines.append(f"\n[Scene {item['scene'] + 1} — {_fmt_ts(s)} to {_fmt_ts(e)}]")
                current_scene = item["scene"]

            uid = item["uid"]
            if item["last_uid"] != uid:
                uid = f"{uid}-{item['last_uid']}"

            lines.append(
                f"[{uid} {_fmt_ts(item['start'])}-{_fmt_ts(item['end'])}] "
                f"{item['label']}:{item['sentiment']} {item['text']}"
            )

        if scene_ranges is not None:
            print(
                f"[S04] Scene-filtered transcript: {len(merged)} turns from "
                f"{len(kept)} utterances across {len(scene_ranges)} scene(s)"
            )
        else:
            print(
                f"[S04] Labeled transcript: {len(merged)} turns from "
                f"{len(kept)} utterances, {len(letters)} raw speaker(s)"
            )

        return "\n".join(lines)

    except RuntimeError:
        raise
    except Exception as e:
        print(f"[S04] Error: {e}")
        raise RuntimeError(f"Failed to generate labeled transcript: {e}")
