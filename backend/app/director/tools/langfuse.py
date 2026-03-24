"""Director Langfuse tool — full trace/cost/input/output data from Langfuse Cloud."""

from app.config import settings


def get_langfuse_data(step: str | None = None, days: int = 7) -> dict:
    """
    Fetch Gemini generation data from Langfuse Cloud.
    Returns full input prompts, outputs, token counts, costs, latency.
    Aggregates totals by step type.
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

            latency_s = getattr(trace, "latency", None) or 0
            latency_ms = int(latency_s * 1000)
            trace_cost = 0.0
            input_tok = 0
            output_tok = 0
            full_input = ""
            full_output = ""

            # Get observations for this trace (tokens, cost, full I/O)
            try:
                obs_page = lf.fetch_observations(trace_id=trace.id)
                for ob in (obs_page.data or []):
                    # Token usage
                    usage = getattr(ob, "usage", None)
                    if usage:
                        input_tok += getattr(usage, "input", 0) or 0
                        output_tok += getattr(usage, "output", 0) or 0

                    # Cost
                    ob_cost = getattr(ob, "calculatedTotalCost", None) or 0.0
                    trace_cost += float(ob_cost)

                    # Full input/output — take the first generation observation
                    if not full_input:
                        raw_input = getattr(ob, "input", None)
                        if raw_input:
                            full_input = str(raw_input) if not isinstance(raw_input, str) else raw_input
                    if not full_output:
                        raw_output = getattr(ob, "output", None)
                        if raw_output:
                            full_output = str(raw_output) if not isinstance(raw_output, str) else raw_output
            except Exception:
                pass

            total_input_tokens += input_tok
            total_output_tokens += output_tok
            total_cost_usd += trace_cost
            total_duration_ms += latency_ms

            # Per-step breakdown
            if name not in step_breakdown:
                step_breakdown[name] = {
                    "count": 0,
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "total_cost_usd": 0.0,
                    "_total_duration_ms": 0,
                    "avg_duration_ms": 0,
                }
            sb = step_breakdown[name]
            sb["count"] += 1
            sb["total_input_tokens"] += input_tok
            sb["total_output_tokens"] += output_tok
            sb["total_cost_usd"] += trace_cost
            sb["_total_duration_ms"] += latency_ms
            sb["avg_duration_ms"] = sb["_total_duration_ms"] // sb["count"]

            trace_list.append({
                "id": getattr(trace, "id", ""),
                "name": name,
                "latency_ms": latency_ms,
                "input_tokens": input_tok,
                "output_tokens": output_tok,
                "cost_usd": round(trace_cost, 6),
                "input_preview": full_input[:500] if full_input else "",
                "output_preview": full_output[:500] if full_output else "",
            })

        # Clean up internal keys, round costs
        for sb in step_breakdown.values():
            sb.pop("_total_duration_ms", None)
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
            "recent_traces": trace_list[:10],
        }

    except ImportError:
        return {"error": "langfuse package not installed"}
    except Exception as e:
        print(f"[DirectorLangfuse] error: {e}")
        return {"error": str(e)}
