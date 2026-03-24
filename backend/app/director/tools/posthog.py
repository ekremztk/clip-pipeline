"""Director PostHog tool — fetch frontend behavior events."""

from app.config import settings


def get_posthog_events(event: str | None = None, days: int = 7) -> dict:
    """
    Fetch event stats from PostHog Cloud.
    Returns aggregated counts per event type.
    """
    try:
        if not settings.POSTHOG_API_KEY:
            return {"error": "PostHog not configured (missing POSTHOG_API_KEY)"}

        import os
        import urllib.request
        import json

        project_id = os.getenv("POSTHOG_PROJECT_ID", "")
        if not project_id:
            return {"warning": "POSTHOG_PROJECT_ID not set. PostHog tracking is active but Director queries need the project ID."}

        # PostHog Insights API — events aggregate
        url = f"{settings.POSTHOG_HOST}/api/projects/{project_id}/events/?limit=100"
        if event:
            url += f"&event={event}"

        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {settings.POSTHOG_API_KEY}"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        events = data.get("results", [])

        # Aggregate counts by event type
        from collections import Counter
        counter = Counter(e.get("event", "unknown") for e in events)

        return {
            "period_days": days,
            "total_events_fetched": len(events),
            "event_counts": dict(counter.most_common(20)),
            "raw_sample": events[:5],
        }

    except ImportError:
        return {"error": "posthog package not installed"}
    except Exception as e:
        print(f"[DirectorPostHog] error: {e}")
        return {"error": str(e)}
