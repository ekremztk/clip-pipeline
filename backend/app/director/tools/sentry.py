"""Director Sentry tool — fetch error/issue data from Sentry."""

from app.config import settings


def get_sentry_issues(days: int = 7, resolved: bool = False) -> list[dict]:
    """
    Fetch recent Sentry issues for the project.
    Returns [{title, count, culprit, lastSeen, level}]
    """
    try:
        import sentry_sdk

        # Sentry SDK doesn't expose a query API directly.
        # We use the Sentry REST API via requests if DSN is set.
        if not settings.SENTRY_DSN:
            return [{"error": "Sentry not configured (missing SENTRY_DSN)"}]

        # Extract org/project slug from DSN
        # DSN format: https://<key>@<host>/<project_id>
        # We need SENTRY_AUTH_TOKEN and SENTRY_ORG env vars for the API
        import os
        auth_token = os.getenv("SENTRY_AUTH_TOKEN", "")
        org_slug = os.getenv("SENTRY_ORG", "")
        project_slug = os.getenv("SENTRY_PROJECT", "")

        if not auth_token or not org_slug or not project_slug:
            return [{
                "warning": "Sentry REST API needs SENTRY_AUTH_TOKEN, SENTRY_ORG, SENTRY_PROJECT env vars.",
                "note": "Sentry SDK is initialized for error tracking but Director query requires API access."
            }]

        import urllib.request
        import json

        status_filter = "resolved" if resolved else "unresolved"
        url = (
            f"https://sentry.io/api/0/projects/{org_slug}/{project_slug}/issues/"
            f"?statsPeriod={days}d&query=is:{status_filter}&limit=25"
        )
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {auth_token}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            issues = json.loads(resp.read())

        return [
            {
                "id": issue.get("id"),
                "title": issue.get("title"),
                "culprit": issue.get("culprit"),
                "count": issue.get("count"),
                "level": issue.get("level"),
                "lastSeen": issue.get("lastSeen"),
                "firstSeen": issue.get("firstSeen"),
            }
            for issue in issues
        ]
    except ImportError:
        return [{"error": "sentry-sdk not installed"}]
    except Exception as e:
        print(f"[DirectorSentry] error: {e}")
        return [{"error": str(e)}]
