"""Director Langfuse tool — fetch Gemini trace data from Langfuse Cloud."""

from app.config import settings


def get_langfuse_data(step: str | None = None, days: int = 7) -> dict:
    """
    Fetch Gemini usage stats from Langfuse Cloud.
    Returns token usage, latency, retry counts per trace.
    """
    try:
        if not settings.LANGFUSE_SECRET_KEY or not settings.LANGFUSE_PUBLIC_KEY:
            return {"error": "Langfuse not configured (missing LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY)"}

        from langfuse import Langfuse

        lf = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
        )

        # Fetch recent traces
        traces = lf.fetch_traces(limit=100).data

        result = {
            "total_traces": len(traces),
            "step_filter": step,
            "period_days": days,
            "traces": [],
        }

        for trace in traces:
            name = getattr(trace, "name", "") or ""
            if step and step not in name:
                continue

            trace_data = {
                "id": getattr(trace, "id", ""),
                "name": name,
                "latency_ms": getattr(trace, "latency", None),
                "total_cost": getattr(trace, "totalCost", None),
                "input_tokens": None,
                "output_tokens": None,
            }

            # Try to get token counts from observations
            try:
                obs = lf.fetch_observations(trace_id=trace.id).data
                for ob in obs:
                    usage = getattr(ob, "usage", None)
                    if usage:
                        trace_data["input_tokens"] = getattr(usage, "input", None)
                        trace_data["output_tokens"] = getattr(usage, "output", None)
                        break
            except Exception:
                pass

            result["traces"].append(trace_data)

        return result

    except ImportError:
        return {"error": "langfuse package not installed"}
    except Exception as e:
        print(f"[DirectorLangfuse] error: {e}")
        return {"error": str(e)}
