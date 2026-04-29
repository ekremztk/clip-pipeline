"""
Guest parser — extract structured {host, team_captains, guests, musical_act}
from a BBC episode synopsis using Gemini Flash, with strict hallucination
guards (VERBATIM matching) and TVmaze cross-check.

Pipeline per episode:
  1. LLM extract from synopsis_long
  2. VERBATIM validation — every returned name must appear literally in synopsis
  3. TVmaze cross-check (if tvmaze_episode_id known) — agree / disagree
  4. Write guests jsonb + guests_source + metadata_confidence
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any

from app.services.gemini_client import generate_json
from app.config import settings

SYSTEM_PROMPT = (
    "You are a meticulous metadata extractor for a UK talk show database. "
    "You NEVER invent names. You ONLY return names that appear verbatim in "
    "the provided synopsis. If uncertain, return an empty list."
)

USER_PROMPT_TEMPLATE = """\
Extract guest metadata from the following talk-show episode synopsis.

Return STRICT JSON with this exact schema:
{
  "team_captains": ["string"],
  "guests": ["string"],
  "musical_act": "string or null"
}

Rules (must obey, no exceptions):
- Names MUST appear VERBATIM in the synopsis — do not paraphrase, do not
  expand abbreviations, do not add titles ("Sir", "Dr.") unless the
  synopsis contains them.
- "team_captains" = recurring panelists explicitly called "team captain"
  or clearly playing that role based on wording ("team captains X and Y").
- "guests" = one-off guests. Look for wordings like "joined by", "with
  guests", "tonight's guests", "on the sofa", "Together on X's sofa",
  "Among the guests", "guest panellists". Include EVERY named person in
  the guest list — possessive forms like "Graham's sofa" refer to the
  show host (who you should NOT include as a guest), but all other named
  people listed are guests.
- "musical_act" = only if a band or artist is named performing (e.g.
  "with music from X", "plus music from X"). Otherwise null.
- Do NOT include the show host in the guests list.
- Do NOT infer names from show title. Do NOT use world knowledge.
- If a role is not mentioned at all, leave it empty/null.

Synopsis:
\"\"\"
{synopsis}
\"\"\"

Return ONLY the JSON, no commentary.
"""


@dataclass
class GuestExtraction:
    host: str | None = None
    team_captains: list[str] = field(default_factory=list)
    guests: list[str] = field(default_factory=list)
    musical_act: str | None = None

    def total_names(self) -> list[str]:
        out = []
        if self.host:
            out.append(self.host)
        out.extend(self.team_captains)
        out.extend(self.guests)
        if self.musical_act:
            out.append(self.musical_act)
        return out


@dataclass
class ParseResult:
    extraction: GuestExtraction
    confidence: str                       # 'high' | 'medium' | 'low'
    verbatim_rejections: list[str]        # names dropped because not in synopsis
    tvmaze_agreement: str | None = None   # 'agree' | 'partial' | 'disagree' | None


# ── Public entry ───────────────────────────────────────────────

def parse_synopsis(
    synopsis: str,
    *,
    default_host: str | None = None,
    tvmaze_guest_names: list[str] | None = None,
) -> ParseResult:
    """Extract guests from a synopsis. Safe against LLM hallucination.

    `default_host` is assigned directly — the host never comes from the LLM,
    since show synopses rarely restate the obvious ("Graham's sofa" is a
    possessive, not an assertion that Graham hosts).
    """
    if not synopsis or not synopsis.strip():
        return ParseResult(GuestExtraction(host=default_host), "low", [])

    raw = _llm_extract(synopsis)
    # host is authoritative — bypass verbatim check entirely
    cleaned, rejections = _verbatim_filter(raw, synopsis)
    cleaned.host = default_host
    confidence = _score_confidence(cleaned, rejections)
    agreement = None
    if tvmaze_guest_names:
        agreement = _tvmaze_agreement(cleaned, tvmaze_guest_names)
        # If TVmaze strongly disagrees, downgrade
        if agreement == "disagree":
            confidence = "low"
        elif agreement == "agree" and confidence == "medium":
            confidence = "high"

    return ParseResult(
        extraction=cleaned,
        confidence=confidence,
        verbatim_rejections=rejections,
        tvmaze_agreement=agreement,
    )


# ── LLM call ───────────────────────────────────────────────────

def _llm_extract(synopsis: str) -> GuestExtraction:
    prompt = USER_PROMPT_TEMPLATE.replace("{synopsis}", synopsis)

    # 60s hard timeout — Vertex AI hangs periodically with no native timeout
    import threading
    result_box: dict[str, Any] = {}

    def _run() -> None:
        try:
            result_box["data"] = generate_json(
                prompt,
                system=SYSTEM_PROMPT,
                model=settings.GEMINI_MODEL_FLASH,
            )
        except Exception as e:
            result_box["error"] = e

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=60)
    if t.is_alive():
        print(f"[guest_parser] LLM timeout (60s) — skipping")
        return GuestExtraction()
    if "error" in result_box:
        print(f"[guest_parser] LLM error: {result_box['error']}")
        return GuestExtraction()
    data = result_box.get("data")

    if not isinstance(data, dict):
        return GuestExtraction()

    def _str_or_none(v: Any) -> str | None:
        return v.strip() if isinstance(v, str) and v.strip() else None

    def _str_list(v: Any) -> list[str]:
        if not isinstance(v, list):
            return []
        return [s.strip() for s in v if isinstance(s, str) and s.strip()]

    return GuestExtraction(
        host=None,  # filled by parse_synopsis from default_host
        team_captains=_str_list(data.get("team_captains")),
        guests=_str_list(data.get("guests")),
        musical_act=_str_or_none(data.get("musical_act")),
    )


# ── VERBATIM guard ─────────────────────────────────────────────

_NAME_NORMALIZE_RE = re.compile(r"[^a-z0-9\s]")

def _normalize(text: str) -> str:
    return _NAME_NORMALIZE_RE.sub("", text.lower()).strip()


def _verbatim_filter(
    extraction: GuestExtraction, synopsis: str
) -> tuple[GuestExtraction, list[str]]:
    """
    Drop any name that does not appear verbatim (case-insensitive,
    punctuation-insensitive) in the synopsis. Protects against the LLM
    inventing names or expanding abbreviations.
    """
    synopsis_norm = _normalize(synopsis)
    rejections: list[str] = []

    def _keep(name: str | None) -> str | None:
        if not name:
            return None
        if _normalize(name) in synopsis_norm:
            return name
        rejections.append(name)
        return None

    def _keep_list(names: list[str]) -> list[str]:
        out: list[str] = []
        for n in names:
            kept = _keep(n)
            if kept:
                out.append(kept)
        return out

    return GuestExtraction(
        host=_keep(extraction.host),
        team_captains=_keep_list(extraction.team_captains),
        guests=_keep_list(extraction.guests),
        musical_act=_keep(extraction.musical_act),
    ), rejections


# ── Confidence scoring ────────────────────────────────────────

def _score_confidence(
    cleaned: GuestExtraction, rejections: list[str]
) -> str:
    """
    High: at least 1 name extracted AND no rejections
    Medium: at least 1 name extracted with some rejections (partial trust)
    Low: 0 names extracted
    """
    n_kept = len(cleaned.total_names())
    if n_kept == 0:
        return "low"
    if not rejections:
        return "high"
    return "medium"


# ── TVmaze cross-check ────────────────────────────────────────

def _tvmaze_agreement(
    cleaned: GuestExtraction, tvmaze_names: list[str]
) -> str:
    """
    Compare cleaned extraction's guest names vs TVmaze's guestcast.
    'agree'   : >=50% of TVmaze guests appear in our extraction
    'partial' : some overlap but <50%
    'disagree': zero overlap despite both sides having names
    """
    if not tvmaze_names:
        return "partial"

    our = {_normalize(n) for n in cleaned.guests}
    their = {_normalize(n) for n in tvmaze_names}
    if not our or not their:
        return "disagree" if (their and not our) else "partial"
    overlap = our & their
    ratio = len(overlap) / len(their)
    if ratio >= 0.5:
        return "agree"
    if overlap:
        return "partial"
    return "disagree"


# ── Batch orchestrator over DB rows ───────────────────────────

def parse_and_store_for_show(
    show_id: str,
    *,
    limit: int | None = None,
    only_unparsed: bool = True,
    concurrency: int = 5,
) -> dict[str, Any]:
    """
    Walk source_videos rows for a show, call the parser, write results.

    only_unparsed=True targets rows that are missing OR incomplete:
      - guests IS NULL, OR
      - guests->>'host' IS NULL, OR
      - guests->'guests' = '[]' (empty guest list)
    This lets us safely re-run after a prompt/host fix to backfill.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from threading import Lock

    from app.services.supabase_client import get_client

    sb = get_client()
    if sb is None:
        raise RuntimeError("Supabase client unavailable")

    # Load show_registry to get the default_host (authoritative, not LLM-derived)
    show = (
        sb.table("show_registry")
        .select("id,default_host")
        .eq("id", show_id)
        .single()
        .execute()
    )
    show_row = show.data
    if not show_row:
        raise ValueError(f"show_registry row missing: {show_id}")
    default_host = show_row.get("default_host")

    if only_unparsed:
        # Use SQL to find "problem" rows because Supabase client can't express
        # "jsonb key is null OR array is empty" in a single filter chain.
        sql = """
            SELECT pid, synopsis_long, tvmaze_episode_id
            FROM source_videos
            WHERE show_id = %s
              AND (
                guests IS NULL
                OR guests->>'host' IS NULL
                OR guests->'guests' = '[]'::jsonb
                OR jsonb_array_length(guests->'guests') = 0
              )
        """
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        # Use rpc-less path: just fetch all & filter in app since schema is small.
        # Fallback: fetch with loose filter (guests is null OR not null) and filter locally.
        base = (
            sb.table("source_videos")
            .select("pid,synopsis_long,tvmaze_episode_id,guests")
            .eq("show_id", show_id)
        )
        if limit is not None:
            base = base.limit(max(limit * 3, 1000))  # overfetch for local filter
        all_rows = base.execute().data or []

        def _needs_parse(r: dict[str, Any]) -> bool:
            g = r.get("guests")
            if g is None:
                return True
            if not isinstance(g, dict):
                return True
            if not g.get("host"):
                return True
            if not g.get("guests"):
                return True
            return False

        rows = [r for r in all_rows if _needs_parse(r)]
        if limit is not None:
            rows = rows[:limit]
    else:
        query = (
            sb.table("source_videos")
            .select("pid,synopsis_long,tvmaze_episode_id,guests")
            .eq("show_id", show_id)
        )
        if limit is not None:
            query = query.limit(limit)
        rows = query.execute().data or []

    total = len(rows)
    print(f"[guest_parser] {total} rows to parse (concurrency={concurrency})", flush=True)

    counters = {"high": 0, "medium": 0, "low": 0, "done": 0}
    lock = Lock()

    def _process(row: dict[str, Any]) -> None:
        pid = row["pid"]
        synopsis = row.get("synopsis_long") or ""
        if not synopsis.strip():
            _write_result(
                sb,
                pid,
                GuestExtraction(host=default_host),
                "low",
                "bbc_synopsis_parsed",
            )
            with lock:
                counters["low"] += 1
                counters["done"] += 1
                if counters["done"] % 5 == 0:
                    print(
                        f"[guest_parser] {counters['done']}/{total} | "
                        f"H={counters['high']} M={counters['medium']} L={counters['low']}",
                        flush=True,
                    )
            return

        result = parse_synopsis(
            synopsis,
            default_host=default_host,
            tvmaze_guest_names=None,
        )
        _write_result(
            sb,
            pid,
            result.extraction,
            result.confidence,
            "bbc_synopsis_parsed",
        )
        with lock:
            counters[result.confidence] += 1
            counters["done"] += 1
            if counters["done"] % 5 == 0:
                print(
                    f"[guest_parser] {counters['done']}/{total} | "
                    f"H={counters['high']} M={counters['medium']} L={counters['low']}",
                    flush=True,
                )

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(_process, r) for r in rows]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception as e:
                print(f"[guest_parser] worker error: {e}", flush=True)

    summary = {
        "show_id": show_id,
        "processed": counters["done"],
        "high_confidence": counters["high"],
        "medium_confidence": counters["medium"],
        "low_confidence": counters["low"],
    }
    print(f"[guest_parser] Done: {json.dumps(summary, indent=2)}")
    return summary


def _write_result(
    sb,
    pid: str,
    extraction: GuestExtraction,
    confidence: str,
    source: str,
) -> None:
    guests_jsonb = asdict(extraction)
    sb.table("source_videos").update(
        {
            "guests": guests_jsonb,
            "guests_source": source,
            "metadata_confidence": confidence,
        }
    ).eq("pid", pid).execute()


# ── CLI ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--show", default="graham_norton")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--reparse", action="store_true",
                    help="Re-parse rows that already have guests")
    args = ap.parse_args()

    parse_and_store_for_show(
        args.show,
        limit=args.limit,
        only_unparsed=not args.reparse,
    )
