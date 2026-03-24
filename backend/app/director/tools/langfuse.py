"""Director Langfuse tool — fetch Gemini trace/cost data from Langfuse Cloud."""

from app.config import settings


def get_langfuse_data(step: str | None = None, days: int = 7) -> dict:
    """
    Fetch Gemini usage stats from Langfuse Cloud.
    Returns token usage, latency, cost per trace — and aggregated totals.
    """
    try:
        if not settings.LANGFUSE_SECRET_KEY or not settings.LANGFUSE_PUBLIC_KEY:
            return {"error": "Langfuse not configured (missing keys)"}

        from langfuse import Langfuse
        from datetime import datetime, timezone, timedelta

        lf = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
        )

        from_date = datetime.now(timezone.utc) - timedelta(days=days)
        traces = lf.fetch_traces(limit=200, from_timestamp=from_date).data

        total_input_tokens = 0
        total_output_tokens = 0
        total_cost_usd = 0.0
        total_duration_ms = 0
        step_breakdown: dict[str, dict] = {}
        trace_list = []

        for trace in traces:
            name = getattr(trace, "name", "") or ""
            if step and step not in name:
                continue

            latency = getattr(trace, "latency", None) or 0
            cost = getattr(trace, "totalCost", None) or 0.0
            input_tok = output_tok = 0

            # Get token counts from observations
            try:
                obs = lf.fetch_observations(trace_id=trace.id).data
                for ob in obs:
                    usage = getattr(ob, "usage", None)
                    if usage:
                        input_tok += getattr(usage, "input", 0) or 0
                        output_tok += getattr(usage, "output", 0) or 0
                    ob_cost = getattr(ob, "calculatedTotalCost", None) or 0.0
                    cost += float(ob_cost)
            except Exception:
                pass

            total_input_tokens += input_tok
            total_output_tokens += output_tok
            total_cost_usd += float(cost)
            total_duration_ms += int(latency * 1000) if latency else 0

            # Per-step breakdown
            if name not in step_breakdown:
                step_breakdown[name] = {
                    "count": 0,
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "total_cost_usd": 0.0,
                    "avg_duration_ms": 0,
                    "_total_duration": 0,
                }
            sb = step_breakdown[name]
            sb["count"] += 1
            sb["total_input_tokens"] += input_tok
            sb["total_output_tokens"] += output_tok
            sb["total_cost_usd"] += float(cost)
            sb["_total_duration"] += int(latency * 1000) if latency else 0
            sb["avg_duration_ms"] = sb["_total_duration"] // sb["count"]

            trace_list.append({
                "id": getattr(trace, "id", ""),
                "name": name,
                "latency_ms": int(latency * 1000) if latency else None,
                "input_tokens": input_tok,
                "output_tokens": output_tok,
                "cost_usd": round(float(cost), 6),
            })

        # Clean up internal key
        for sb in step_breakdown.values():
            sb.pop("_total_duration", None)
            sb["total_cost_usd"] = round(sb["total_cost_usd"], 6)

        return {
            "period_days": days,
            "step_filter": step,
            "total_traces": len(trace_list),
            "totals": {
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "total_tokens": total_input_tokens + total_output_tokens,
                "cost_usd": round(total_cost_usd, 4),
                "avg_duration_ms": total_duration_ms // len(trace_list) if trace_list else 0,
            },
            "by_step": step_breakdown,
            "traces": trace_list[:20],  # Sample — last 20
        }

    except ImportError:
        return {"error": "langfuse package not installed"}
    except Exception as e:
        print(f"[DirectorLangfuse] error: {e}")
        return {"error": str(e)}
