"""
Director Dependency Graph — hardcoded service dependency map + impact analysis.
Used by Director to understand blast radius when a service has issues.
"""

from app.director.tools.database import _run_sql

DEPENDENCY_MAP = {
    "r2_storage": {
        "used_by": ["s08_export", "editor_reframe", "clip_playback"],
        "impact_if_down": "CRITICAL — new clips cannot be uploaded, editor won't work",
    },
    "deepgram": {
        "used_by": ["s02_transcribe"],
        "impact_if_down": "HIGH — transcription stops, pipeline halts at S02",
    },
    "gemini_pro": {
        "used_by": ["s05_discovery", "s06_evaluation", "director_chat"],
        "impact_if_down": "CRITICAL — clip discovery, evaluation, and Director all stop",
    },
    "gemini_flash": {
        "used_by": ["guest_research", "channel_dna_generation", "director_simple_chat"],
        "impact_if_down": "MEDIUM — fallback tasks fail but core pipeline unaffected",
    },
    "supabase": {
        "used_by": ["all_modules"],
        "impact_if_down": "CRITICAL — nothing works without database",
    },
    "channel_dna": {
        "used_by": ["s05_discovery", "s06_evaluation"],
        "impact_if_down": "HIGH — clip selection becomes random without channel context",
    },
    "railway": {
        "used_by": ["backend_api", "pipeline_worker"],
        "impact_if_down": "CRITICAL — backend offline, no API or processing",
    },
    "langfuse": {
        "used_by": ["gemini_tracing", "cost_tracking"],
        "impact_if_down": "LOW — tracing stops but pipeline continues normally",
    },
    "sentry": {
        "used_by": ["error_tracking"],
        "impact_if_down": "LOW — error tracking stops but everything else works",
    },
    "posthog": {
        "used_by": ["frontend_analytics", "editor_engagement"],
        "impact_if_down": "LOW — analytics stop but app works fine",
    },
}


def check_dependency_impact(component: str) -> dict:
    """Analyze impact if a specific service/component is down."""
    component_lower = component.lower().replace(" ", "_").replace("-", "_")

    entry = DEPENDENCY_MAP.get(component_lower)
    if not entry:
        candidates = [k for k in DEPENDENCY_MAP if component_lower in k or k in component_lower]
        if candidates:
            entry = DEPENDENCY_MAP[candidates[0]]
            component_lower = candidates[0]
        else:
            return {
                "error": f"Unknown component: {component}",
                "available": list(DEPENDENCY_MAP.keys()),
            }

    downstream = entry["used_by"]
    impact = entry["impact_if_down"]

    affected_by_downstream = []
    for dep_name, dep_info in DEPENDENCY_MAP.items():
        if dep_name == component_lower:
            continue
        if any(d in dep_info["used_by"] for d in downstream):
            affected_by_downstream.append(dep_name)

    return {
        "component": component_lower,
        "direct_dependents": downstream,
        "impact": impact,
        "cascade_risk": affected_by_downstream,
        "recommendation": _get_recommendation(component_lower),
    }


def get_full_dependency_map() -> dict:
    """Return the complete dependency map for visualization."""
    return {
        "components": DEPENDENCY_MAP,
        "total_components": len(DEPENDENCY_MAP),
    }


def get_cross_module_signals(channel_id: str | None = None, days: int = 7) -> dict:
    """Fetch recent cross-module signal flow from the database."""
    try:
        if channel_id:
            rows = _run_sql("""
                SELECT source_module, target_module, event_type,
                       COUNT(*) AS signal_count,
                       MAX(created_at) AS last_signal
                FROM director_cross_module_signals
                WHERE created_at > now() - interval '%s days'
                  AND channel_id = %s
                GROUP BY source_module, target_module, event_type
                ORDER BY signal_count DESC
                LIMIT 50
            """, (days, channel_id))
        else:
            rows = _run_sql("""
                SELECT source_module, target_module, event_type,
                       COUNT(*) AS signal_count,
                       MAX(created_at) AS last_signal
                FROM director_cross_module_signals
                WHERE created_at > now() - interval '%s days'
                GROUP BY source_module, target_module, event_type
                ORDER BY signal_count DESC
                LIMIT 50
            """, (days,))

        return {
            "signals": rows,
            "total_flows": len(rows),
            "period_days": days,
        }
    except Exception as e:
        return {"error": str(e)}


def _get_recommendation(component: str) -> str:
    """Get remediation recommendation for a component failure."""
    recs = {
        "r2_storage": "Check Cloudflare R2 status page. Verify R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY env vars.",
        "deepgram": "Check Deepgram status page and API key balance. Pipeline will retry 3x automatically.",
        "gemini_pro": "Check Google AI Studio quotas. Rate limit retries are built-in (30s, 30s, 60s). If persistent, check GEMINI_API_KEY.",
        "gemini_flash": "Same as gemini_pro but lower priority. Non-critical tasks will queue.",
        "supabase": "Check Supabase dashboard. Verify DATABASE_URL uses port 6543 (pooler). Check connection limits.",
        "channel_dna": "Channel DNA is in Supabase. If missing, Director can regenerate with update_channel_dna tool.",
        "railway": "Check Railway dashboard for deployment status. May need manual redeploy.",
        "langfuse": "Non-blocking — tracing failure never stops the pipeline. Check Langfuse dashboard for quota.",
        "sentry": "Non-blocking — check Sentry DSN env var if errors not appearing.",
        "posthog": "Non-blocking — check PostHog project key if events not appearing.",
    }
    return recs.get(component, "Check service status and env vars.")
