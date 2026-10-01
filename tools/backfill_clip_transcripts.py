"""Fill clips.transcript for clips cut before S08 started writing it.

Rebuilds each clip's spoken text from its job's word timestamps between
start_time and end_time (the same rule S08 now applies at cut time). Only
touches rows whose transcript is empty. For stitched clips only the main
window is recoverable, since the setup window is not stored on the row.

Usage (from the monorepo root):
    python3 tools/backfill_clip_transcripts.py [--channel otherside_cast] [--apply]

Without --apply it only reports what it would write.
"""

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / "backend" / ".env"


def load_env() -> dict:
    env = {}
    try:
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    except Exception as e:
        print(f"[Backfill] Error reading env: {e}")
    return env


def request(env: dict, method: str, path: str, body=None):
    req = urllib.request.Request(
        f"{env['SUPABASE_URL'].rstrip('/')}/rest/v1/{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "apikey": env["SUPABASE_SERVICE_KEY"],
            "Authorization": f"Bearer {env['SUPABASE_SERVICE_KEY']}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def clip_text(words: list, start: float, end: float) -> str:
    return " ".join(
        (w.get("punctuated_word") or w.get("word") or "").strip()
        for w in words
        if start <= float(w.get("start", -1)) < end
    ).strip()


def main() -> None:
    args = sys.argv[1:]
    apply = "--apply" in args
    channel = args[args.index("--channel") + 1] if "--channel" in args else None
    env = load_env()

    # PostgREST caps a response at 1000 rows, so page through by id.
    base = "clips?select=id,job_id,start_time,end_time&or=(transcript.is.null,transcript.eq.)&order=id&limit=1000"
    if channel:
        base += "&channel_id=eq." + urllib.parse.quote(channel)
    clips, last_id = [], None
    try:
        while True:
            page = request(env, "GET", base + (f"&id=gt.{last_id}" if last_id else "")) or []
            clips.extend(page)
            if len(page) < 1000:
                break
            last_id = page[-1]["id"]
    except Exception as e:
        print(f"[Backfill] Error listing clips: {e}")
        sys.exit(1)

    by_job = {}
    for c in clips:
        by_job.setdefault(c["job_id"], []).append(c)
    print(f"[Backfill] {len(clips)} clips without transcript across {len(by_job)} jobs "
          f"({'APPLY' if apply else 'dry run'})")

    written = skipped = 0
    for job_id, job_clips in by_job.items():
        try:
            tx = request(env, "GET", f"transcripts?select=word_timestamps&job_id=eq.{job_id}&limit=1")
            words = (tx[0].get("word_timestamps") or []) if tx else []
        except Exception as e:
            print(f"[Backfill] Error loading words for job {job_id}: {e}")
            skipped += len(job_clips)
            continue
        for c in job_clips:
            text = clip_text(words, float(c.get("start_time") or 0), float(c.get("end_time") or 0))
            if not text:
                skipped += 1
                continue
            if apply:
                try:
                    request(env, "PATCH", f"clips?id=eq.{c['id']}", {"transcript": text})
                except Exception as e:
                    print(f"[Backfill] Error writing clip {c['id']}: {e}")
                    skipped += 1
                    continue
            written += 1
    verb = "wrote" if apply else "would write"
    print(f"[Backfill] {verb} {written}, skipped {skipped}")


if __name__ == "__main__":
    main()
