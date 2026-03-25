"""Director Deepgram tool — usage and cost data from Deepgram API."""

import os
import json
import urllib.request
from app.config import settings

DEEPGRAM_API_URL = "https://api.deepgram.com/v1"


def get_deepgram_usage(days: int = 7) -> dict:
    """
    Fetch Deepgram usage stats: requests, audio hours, estimated cost.
    Returns breakdown by date and totals.
    """
    try:
        api_key = settings.DEEPGRAM_MANAGEMENT_KEY
        if not api_key:
            return {"error": "DEEPGRAM_API_KEY not set"}
        if api_key == settings.DEEPGRAM_API_KEY and not os.getenv("DEEPGRAM_MANAGEMENT_KEY"):
            # Warn that the transcription key likely lacks usage:read scope
            print("[DirectorDeepgram] Warning: using transcription key for usage API — may 403. Set DEEPGRAM_MANAGEMENT_KEY with Member role.")

        project_id = os.getenv("DEEPGRAM_PROJECT_ID", "")

        # Step 1: get project ID if not set
        if not project_id:
            req = urllib.request.Request(
                f"{DEEPGRAM_API_URL}/projects",
                headers={"Authorization": f"Token {api_key}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            projects = data.get("projects", [])
            if not projects:
                return {"error": "No Deepgram projects found"}
            project_id = projects[0]["project_id"]

        # Step 2: fetch usage summary
        from datetime import datetime, timezone, timedelta
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")

        url = (
            f"{DEEPGRAM_API_URL}/projects/{project_id}/usage"
            f"?start={start_str}&end={end_str}"
        )
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Token {api_key}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            usage_data = json.loads(resp.read())

        # Step 3: fetch balance
        balance = None
        try:
            bal_req = urllib.request.Request(
                f"{DEEPGRAM_API_URL}/projects/{project_id}/balances",
                headers={"Authorization": f"Token {api_key}"},
            )
            with urllib.request.urlopen(bal_req, timeout=10) as resp:
                bal_data = json.loads(resp.read())
            balances = bal_data.get("balances", [])
            if balances:
                balance = {
                    "amount": balances[0].get("amount"),
                    "units": balances[0].get("units"),
                }
        except Exception:
            pass

        results = usage_data.get("results", [])
        total_requests = sum(r.get("requests", 0) for r in results)
        total_hours = sum(r.get("hours", 0.0) for r in results)

        # Deepgram Nova-2 pricing: ~$0.0043/minute = $0.258/hour
        PRICE_PER_HOUR = 0.258
        estimated_cost = round(total_hours * PRICE_PER_HOUR, 4)

        return {
            "period_days": days,
            "project_id": project_id,
            "totals": {
                "requests": total_requests,
                "audio_hours": round(total_hours, 3),
                "audio_minutes": round(total_hours * 60, 1),
                "estimated_cost_usd": estimated_cost,
            },
            "balance": balance,
            "daily_breakdown": results,
        }

    except Exception as e:
        print(f"[DirectorDeepgram] error: {e}")
        return {"error": str(e)}
