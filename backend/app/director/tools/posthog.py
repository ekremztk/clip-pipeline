"""Director PostHog tool — fetch frontend behavior events."""

from app.config import settings
import os


def get_posthog_events(event: str | None = None, days: int = 7) -> dict:
    """
    Fetch event stats from PostHog Cloud.
    Returns aggregated counts per event type.

    NOTE on API keys:
    - POSTHOG_API_KEY (phc_...) = project/write key used by the frontend SDK — cannot query API
    - POSTHOG_PERSONAL_API_KEY (phx_...) = personal API key — required for REST queries
    Set POSTHOG_PERSONAL_API_KEY in Railway env vars:
      PostHog → Settings → Personal API Keys → Create
    """
    try:
        import urllib.request
        import urllib.parse
        import json

        project_id = os.getenv("POSTHOG_PROJECT_ID", "")
        if not project_id:
            return {"error": "POSTHOG_PROJECT_ID not set"}

        # Personal API key is required for REST API queries
        # Project key (phc_...) is ingestion-only
        personal_key = os.getenv("POSTHOG_PERSONAL_API_KEY", "")
        if not personal_key:
            return {
                "error": "POSTHOG_PERSONAL_API_KEY not set",
                "fix": (
                    "PostHog project key (phc_...) is ingestion-only — cannot query data. "
                    "To use Director PostHog queries: "
                    "PostHog → Settings → Personal API Keys → Create new key (starts with phx_) → "
                    "Railway env: POSTHOG_PERSONAL_API_KEY=phx_..."
                ),
                "tracking_status": "active" if settings.POSTHOG_API_KEY else "not_configured",
            }

        host = settings.POSTHOG_HOST or "https://us.i.posthog.com"
        url = f"{host}/api/projects/{project_id}/events/?limit=200"
        if event:
            url += f"&event={urllib.parse.quote(event)}"

        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {personal_key}"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        events = data.get("results", [])

        from collections import Counter
        counter = Counter(e.get("event", "unknown") for e in events)

        return {
            "period_days": days,
            "total_events_fetched": len(events),
            "event_counts": dict(counter.most_common(20)),
            "raw_sample": events[:5],
        }

    except Exception as e:
        print(f"[DirectorPostHog] error: {e}")
        return {"error": str(e)}
