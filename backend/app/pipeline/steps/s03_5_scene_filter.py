"""
S03.5 — Scene Filter

Narrows down a long episode (50+ min, multiple guests, music, intros) to the
segments where the target guest actually participates. Strictly deterministic:
no LLM, no re-timestamping. Utterances outside kept ranges are dropped; those
inside keep their original (episode) start/end values so S07 can cut from the
original MP4 without drift.

Inputs:
  - transcript_data:  {"utterances": [{speaker, start, end, transcript, confidence}, ...]}
  - speaker_data:     {"predicted_map": {spk_id: {"role": "guest"|"host"|..., "name": str|None}}}
  - target_guest:     str | None — name entered by user on upload

Returns:
  {
    "active": bool,                 # True → S04/S05 should use kept_ranges
    "reason": str,                  # why filter is active / disabled
    "target_speaker_id": str|None,
    "kept_ranges": [(start, end), ...],      # original-episode seconds
    "windows": [                    # density map for debug dump
        {"start": 0.0, "end": 30.0, "target_pct": 0.0,
         "utt_count": 0, "speakers": 0, "decision": "SKIP"},
        ...
    ],
    "stats": {
        "episode_sec": float,
        "kept_sec": float,
        "coverage_pct": float,
        "scene_count": int,
    },
  }

Fail-safes:
  - No speaker mapped to target guest → active=False (full transcript passes)
  - Coverage < MIN_COVERAGE_SEC → active=False (filter unreliable, better to
    give S05 everything than risk dropping the only real segment)
  - Coverage > MAX_COVERAGE_PCT → still active, but logs warning (thresholds
    likely too loose for this show; report shows it)
"""

from __future__ import annotations

# ---- tunables (30s windows, 15s stride → 2x overlap smooths density) ----
WINDOW_SEC = 30.0
STRIDE_SEC = 15.0

KEEP_TARGET_PCT = 0.15        # ≥15% target guest talk in window
KEEP_MIN_UTTERANCES = 3       # at least 3 utterances (noise guard)
KEEP_ADJACENT_PCT = 0.05      # adjacent-to-KEEP tolerance (host setup / reaction)

SCENE_MERGE_GAP_SEC = 30.0    # merge kept windows separated by ≤ 30s
SCENE_SAFETY_PAD_SEC = 10.0   # extend each scene ±10s, then snap to utterance boundary

MIN_COVERAGE_SEC = 180.0      # <3 min kept → filter too aggressive or wrong guest → disable
MAX_COVERAGE_WARN_PCT = 0.70  # >70% kept → filter not biting → warn (still applied)


def _resolve_target_speakers(
    predicted_map: dict,
    target_guest: str | None,
) -> tuple[list[str], str]:
    """
    Find ALL Deepgram speaker_ids that correspond to the target guest.
    Deepgram frequently over-diarizes a single person into multiple clusters.
    Returns (speaker_ids, reason). Empty list when no match.
    """
    if not target_guest:
        return [], "no target_guest provided by user"

    target_norm = target_guest.strip().lower()
    matched_ids = []
    for spk_id, info in (predicted_map or {}).items():
        name = (info or {}).get("name")
        if not name:
            continue
        if name.strip().lower() == target_norm:
            matched_ids.append(str(spk_id))

    if matched_ids:
        ids_str = ", ".join(matched_ids)
        return matched_ids, f"voice-matched target '{target_guest}' → speaker(s) {ids_str}"

    return [], f"no speaker voice-matched to target '{target_guest}'"


def _compute_density_windows(
    utterances: list[dict],
    target_speaker_ids: list[str],
    episode_end_sec: float,
) -> list[dict]:
    """
    Slide a 30s window across the episode at 15s stride, compute for each:
      target_pct  = target guest duration / window duration
      utt_count   = utterances overlapping window
      speakers    = unique speakers in window
    Accepts multiple speaker IDs — Deepgram over-diarizes one person into
    multiple clusters, so all matched clusters count as the target.
    Classification:
      KEEP            → target_pct ≥ 15% AND utt_count ≥ 3
      KEEP_ADJACENT   → target_pct ≥ 5% (promoted later if adjacent to KEEP)
      SKIP            → otherwise
    """
    target_id_set = set(target_speaker_ids)
    windows: list[dict] = []
    t = 0.0
    while t < episode_end_sec:
        w_start = t
        w_end = min(t + WINDOW_SEC, episode_end_sec)
        w_dur = w_end - w_start
        if w_dur <= 0:
            break

        target_dur = 0.0
        utt_count = 0
        speakers_set: set[str] = set()

        for utt in utterances:
            u_start = float(utt.get("start", 0.0))
            u_end = float(utt.get("end", 0.0))
            if u_end <= w_start or u_start >= w_end:
                continue
            overlap = max(0.0, min(u_end, w_end) - max(u_start, w_start))
            if overlap <= 0:
                continue
            utt_count += 1
            speakers_set.add(str(utt.get("speaker", "")))
            if str(utt.get("speaker", "")) in target_id_set:
                target_dur += overlap

        target_pct = target_dur / w_dur if w_dur > 0 else 0.0

        if target_pct >= KEEP_TARGET_PCT and utt_count >= KEEP_MIN_UTTERANCES:
            decision = "KEEP"
        elif target_pct >= KEEP_ADJACENT_PCT:
            decision = "KEEP_ADJACENT"
        else:
            decision = "SKIP"

        windows.append({
            "start": round(w_start, 2),
            "end": round(w_end, 2),
            "target_pct": round(target_pct, 4),
            "target_sec": round(target_dur, 2),
            "utt_count": utt_count,
            "speakers": len(speakers_set),
            "decision": decision,
        })

        t += STRIDE_SEC

    # Promote KEEP_ADJACENT → KEEP only when it touches an actual KEEP window.
    # Isolated KEEP_ADJACENT runs (guest barely in the background) stay dropped.
    for i, w in enumerate(windows):
        if w["decision"] != "KEEP_ADJACENT":
            continue
        prev_keep = i > 0 and windows[i - 1]["decision"] == "KEEP"
        next_keep = i + 1 < len(windows) and windows[i + 1]["decision"] == "KEEP"
        if prev_keep or next_keep:
            w["decision"] = "KEEP"

    return windows


def _merge_windows_to_scenes(
    windows: list[dict],
    utterances: list[dict],
    episode_end_sec: float,
) -> list[tuple[float, float]]:
    """
    Collapse consecutive KEEP windows into scenes, merging across gaps up to
    SCENE_MERGE_GAP_SEC. Then pad each scene by SCENE_SAFETY_PAD_SEC and snap
    the boundaries to the nearest utterance start/end so we never clip in the
    middle of a word.
    """
    kept = [(w["start"], w["end"]) for w in windows if w["decision"] == "KEEP"]
    if not kept:
        return []

    # Merge overlapping / near-adjacent kept windows
    merged: list[list[float]] = []
    for start, end in kept:
        if merged and start - merged[-1][1] <= SCENE_MERGE_GAP_SEC:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    # Pad ± safety, clamp to episode, snap to utterance boundaries.
    # IMPORTANT: only snap within ±PAD. Otherwise a padded end landing in
    # silence would jump to the NEXT scene's utterance — merging two scenes
    # across a long silence gap.
    utt_starts = sorted({float(u.get("start", 0.0)) for u in utterances})
    utt_ends = sorted({float(u.get("end", 0.0)) for u in utterances})

    def snap_start(t: float) -> float:
        candidates = [s for s in utt_starts if abs(s - t) <= SCENE_SAFETY_PAD_SEC]
        if not candidates:
            return max(0.0, t)
        return min(candidates, key=lambda s: abs(s - t))

    def snap_end(t: float) -> float:
        candidates = [e for e in utt_ends if abs(e - t) <= SCENE_SAFETY_PAD_SEC]
        if not candidates:
            return min(episode_end_sec, t)
        return min(candidates, key=lambda e: abs(e - t))

    scenes: list[tuple[float, float]] = []
    for s, e in merged:
        ps = max(0.0, s - SCENE_SAFETY_PAD_SEC)
        pe = min(episode_end_sec, e + SCENE_SAFETY_PAD_SEC)
        ps = snap_start(ps)
        pe = snap_end(pe)
        if pe > ps:
            scenes.append((round(ps, 2), round(pe, 2)))

    # Post-merge: padding can cause two scenes to touch — join them
    final: list[list[float]] = []
    for s, e in scenes:
        if final and s <= final[-1][1]:
            final[-1][1] = max(final[-1][1], e)
        else:
            final.append([s, e])

    return [(s, e) for s, e in final]


def run(
    transcript_data: dict,
    speaker_data: dict,
    target_guest: str | None,
) -> dict:
    """
    Main entry. Never raises — on any failure returns {"active": False, ...}
    and the pipeline continues with the unfiltered transcript.
    """
    utterances = (transcript_data or {}).get("utterances", []) or []
    predicted_map = (speaker_data or {}).get("predicted_map", {}) or {}

    if not utterances:
        return {
            "active": False,
            "reason": "no utterances available",
            "target_speaker_id": None,
            "kept_ranges": [],
            "windows": [],
            "stats": {"episode_sec": 0.0, "kept_sec": 0.0,
                      "coverage_pct": 0.0, "scene_count": 0},
        }

    episode_end_sec = max(
        (float(u.get("end", 0.0)) for u in utterances),
        default=0.0,
    )

    target_speaker_ids, reason = _resolve_target_speakers(predicted_map, target_guest)
    if not target_speaker_ids:
        print(f"[S03.5] Filter disabled — {reason}")
        return {
            "active": False,
            "reason": reason,
            "target_speaker_id": None,
            "kept_ranges": [],
            "windows": [],
            "stats": {"episode_sec": round(episode_end_sec, 2),
                      "kept_sec": 0.0, "coverage_pct": 0.0, "scene_count": 0},
        }

    try:
        windows = _compute_density_windows(utterances, target_speaker_ids, episode_end_sec)
        scenes = _merge_windows_to_scenes(windows, utterances, episode_end_sec)
    except Exception as e:
        print(f"[S03.5] Density/merge error: {e} — disabling filter")
        return {
            "active": False,
            "reason": f"density/merge error: {e}",
            "target_speaker_id": target_speaker_ids[0] if target_speaker_ids else None,
            "kept_ranges": [],
            "windows": [],
            "stats": {"episode_sec": round(episode_end_sec, 2),
                      "kept_sec": 0.0, "coverage_pct": 0.0, "scene_count": 0},
        }

    kept_sec = sum(e - s for s, e in scenes)
    coverage_pct = kept_sec / episode_end_sec if episode_end_sec > 0 else 0.0

    if kept_sec < MIN_COVERAGE_SEC:
        msg = (f"coverage {kept_sec:.1f}s < {MIN_COVERAGE_SEC:.0f}s threshold — "
               f"target guest may not be substantial in this episode")
        print(f"[S03.5] Filter disabled — {msg}")
        return {
            "active": False,
            "reason": msg,
            "target_speaker_id": target_speaker_ids[0] if target_speaker_ids else None,
            "kept_ranges": scenes,
            "windows": windows,
            "stats": {"episode_sec": round(episode_end_sec, 2),
                      "kept_sec": round(kept_sec, 2),
                      "coverage_pct": round(coverage_pct, 4),
                      "scene_count": len(scenes)},
        }

    if coverage_pct > MAX_COVERAGE_WARN_PCT:
        print(f"[S03.5] WARN: kept {coverage_pct*100:.1f}% of episode — thresholds may be too loose")

    ids_str = ", ".join(target_speaker_ids)
    print(
        f"[S03.5] Active — target='{target_guest}' → speaker(s) [{ids_str}]. "
        f"Kept {kept_sec:.1f}s / {episode_end_sec:.1f}s ({coverage_pct*100:.1f}%) "
        f"in {len(scenes)} scene(s)."
    )

    return {
        "active": True,
        "reason": reason,
        "target_speaker_id": target_speaker_ids[0] if target_speaker_ids else None,
        "kept_ranges": scenes,
        "windows": windows,
        "stats": {
            "episode_sec": round(episode_end_sec, 2),
            "kept_sec": round(kept_sec, 2),
            "coverage_pct": round(coverage_pct, 4),
            "scene_count": len(scenes),
        },
    }
