"""
Director Agent — Gemini Pro with function calling.

Runs a tool-calling loop, yields SSE events at each step:
    {"type": "thinking", "message": "..."}
    {"type": "tool_call", "tool": "...", "args": {...}}
    {"type": "tool_result", "tool": "...", "summary": "..."}
    {"type": "text", "text": "..."}
    {"type": "done"}
    {"type": "error", "message": "..."}
"""

import json
import time
from typing import AsyncGenerator, Any
from google.genai import types

from app.config import settings
from app.services.gemini_client import get_gemini_client, _trace_generation
from app.director.tools import database as db_tools
from app.director.tools import filesystem as fs_tools
from app.director.tools import memory as mem_tools
from app.director.tools import langfuse as lf_tools
from app.director.tools import sentry as sentry_tools
from app.director.tools import posthog as ph_tools
from app.director.tools import railway as railway_tools
from app.director.tools import deepgram as deepgram_tools
from app.director.tools import websearch as ws_tools
from app.director.tools import self_analysis as sa_tools

# ─────────────────────────────────────────────
# System Prompt
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """Sen Prognot sisteminin Director'ısın — yapay zeka destekli CEO ve sistem yöneticisi.

Prognot, YouTube podcast kliplerini otomatik keşfeden, düzenleyen ve export eden bir pipeline sistemidir.
Kurucunun sağ kolu olarak çalışırsın: verilere bakarsın, kodu okursun, geçmişi hatırlarsın, cesur öneriler üretirsin.

## Temel Prensipler

1. **Araçlarla düşün, varsayımla değil.** Bir şeyi "bilmek" yerine önce araçlarınla sistemi oku.
   "S05 yavaş görünüyor" diyorsan önce query_database ile gerçek süreleri bak.

2. **Kanıt olmadan hata bulma.** Bir şeyin problem olduğunu söylemeden önce read_file veya query_database ile doğrula.

3. **Kasıtlı tasarım kararlarını tanı.** Örneğin: M1 çıktısı 16:9 çünkü M2 reframe 16:9 gerektirir.
   Bunu "problem" olarak işaretlemeden önce MODULE_2_EDITOR.md dosyasını oku.

4. **Hafıza kullan.** Her konuşmada query_memory ile geçmişe bak. Öğrendiklerini save_memory ile kaydet.

5. **Emin olmadığında sor.** "Bunun kasıtlı olup olmadığından emin değilim, teyit edebilir misin?"

6. **Cesur ol.** Küçük iyileştirmelerden değil, sistem seviyesi değişikliklerden bahset.

## Sistem Yapısı

- **Module 1**: 8-adımlı pipeline (S01-S08), Gemini Pro ile klip keşfi ve değerlendirme
- **Module 2**: Editor (OpenCut), Reframe (yüz takibi), Auto Captions (Deepgram)
- **Stack**: Railway (FastAPI) + Vercel (Next.js) + Supabase + Cloudflare R2
- **Models**: gemini-3.1-pro-preview (S05, S06), gemini-2.5-flash (diğerleri)

## Dokümanlar

Sistemi anlamak için önce bunları oku:
- docs/MODULE_1_CLIP_EXTRACTOR.md
- docs/MODULE_2_EDITOR.md
- docs/SYSTEM_CORE.md
- docs/DIRECTOR_MODULE.md

## Önemli Kısıtlamalar

- Railway CPU-only, GPU kütüphanesi yok (PyTorch, TensorFlow, WhisperX vs.)
- DATABASE_URL port 6543 olmalı (5432 değil)
- **Kod değişikliği yapma yetkisi yok.** Kod önerilerini açık ve uygulanabilir şekilde sun — hangi dosya, hangi satır, ne değişecek. Kullanıcı kendisi uygular.
- Kilitli dosyalar: reframer.py, memory/, next.config.js, s01-s04 pipeline adımları
- Tüm kod ve dosyaları okuyabilirsin — `read_file`, `list_files`, `search_codebase` serbestçe kullan.

Türkçe konuş. Kısa ve net ol. Araç zincirini göster ama gereksiz teknik detaya boğma."""

# ─────────────────────────────────────────────
# Tool Definitions (Gemini function declarations)
# ─────────────────────────────────────────────

TOOL_DECLARATIONS = [
    types.FunctionDeclaration(
        name="read_file",
        description="Read any project file (MD, Python, TypeScript, SQL, JSON). path is relative to project root.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"path": types.Schema(type="STRING", description="Relative file path, e.g. docs/MODULE_1_CLIP_EXTRACTOR.md")},
            required=["path"]
        )
    ),
    types.FunctionDeclaration(
        name="list_files",
        description="List files in a directory with optional glob pattern.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "directory": types.Schema(type="STRING"),
                "pattern": types.Schema(type="STRING", description="Glob pattern, e.g. *.py"),
            },
            required=["directory"]
        )
    ),
    types.FunctionDeclaration(
        name="search_codebase",
        description="Search codebase with regex. Returns [{file, line, content}].",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "query": types.Schema(type="STRING", description="Regex pattern to search"),
                "file_pattern": types.Schema(type="STRING", description="Optional glob filter, e.g. *.py"),
            },
            required=["query"]
        )
    ),
    types.FunctionDeclaration(
        name="query_database",
        description="Run a SELECT query on Supabase. Only SELECT allowed. Returns list of rows.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"sql": types.Schema(type="STRING", description="SQL SELECT query")},
            required=["sql"]
        )
    ),
    types.FunctionDeclaration(
        name="get_pipeline_stats",
        description="Get pipeline pass rate, avg duration, error count, step-level breakdown.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "days": types.Schema(type="INTEGER", description="Look-back period in days"),
                "channel_id": types.Schema(type="STRING"),
            }
        )
    ),
    types.FunctionDeclaration(
        name="get_clip_analysis",
        description="Get clip score distribution, verdict breakdown, content type stats.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "job_id": types.Schema(type="STRING"),
                "days": types.Schema(type="INTEGER"),
            }
        )
    ),
    types.FunctionDeclaration(
        name="get_channel_dna",
        description="Get Channel DNA JSON for a channel.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"channel_id": types.Schema(type="STRING")},
            required=["channel_id"]
        )
    ),
    types.FunctionDeclaration(
        name="get_recent_events",
        description="Fetch recent director_events for a module (pipeline telemetry).",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "module": types.Schema(type="STRING", description="e.g. module_1, module_2"),
                "days": types.Schema(type="INTEGER"),
                "limit": types.Schema(type="INTEGER"),
            }
        )
    ),
    types.FunctionDeclaration(
        name="save_memory",
        description="Save a long-term memory record. type: decision|context|plan|note|learning.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "content": types.Schema(type="STRING"),
                "type": types.Schema(type="STRING"),
                "tags": types.Schema(type="ARRAY", items=types.Schema(type="STRING")),
            },
            required=["content", "type"]
        )
    ),
    types.FunctionDeclaration(
        name="query_memory",
        description="Semantic search over long-term memory.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "query": types.Schema(type="STRING"),
                "type": types.Schema(type="STRING"),
                "top_k": types.Schema(type="INTEGER"),
            },
            required=["query"]
        )
    ),
    types.FunctionDeclaration(
        name="list_memories",
        description="List all memory records, optionally filtered by type.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"type": types.Schema(type="STRING")}
        )
    ),
    types.FunctionDeclaration(
        name="get_langfuse_data",
        description="Fetch Gemini trace data from Langfuse Cloud (token usage, latency, retries).",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "step": types.Schema(type="STRING", description="Filter by pipeline step name, e.g. s05"),
                "days": types.Schema(type="INTEGER"),
            }
        )
    ),
    types.FunctionDeclaration(
        name="get_sentry_issues",
        description="Fetch recent errors/issues from Sentry.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "days": types.Schema(type="INTEGER"),
                "resolved": types.Schema(type="BOOLEAN"),
            }
        )
    ),
    types.FunctionDeclaration(
        name="get_posthog_events",
        description="Fetch frontend behavior events from PostHog Cloud.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "event": types.Schema(type="STRING", description="Filter by event name"),
                "days": types.Schema(type="INTEGER"),
            }
        )
    ),
    types.FunctionDeclaration(
        name="get_railway_status",
        description="Fetch Railway deployment status, service health, and latest deployment info.",
        parameters=types.Schema(type="OBJECT", properties={})
    ),
    types.FunctionDeclaration(
        name="get_railway_logs",
        description="Fetch recent deployment logs from Railway for a service.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "service_name": types.Schema(type="STRING", description="Service name filter, e.g. backend"),
                "limit": types.Schema(type="INTEGER", description="Number of log lines, default 50"),
            }
        )
    ),
    types.FunctionDeclaration(
        name="get_deepgram_usage",
        description="Fetch Deepgram transcription usage: requests, audio hours, estimated cost and current balance.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "days": types.Schema(type="INTEGER", description="Look-back period in days"),
            }
        )
    ),
    types.FunctionDeclaration(
        name="web_search",
        description="Search the internet for information, tools, integrations, best practices. Uses Brave Search or DuckDuckGo fallback.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "query": types.Schema(type="STRING", description="Search query in English or Turkish"),
                "num_results": types.Schema(type="INTEGER", description="Number of results, default 6"),
            },
            required=["query"]
        )
    ),
    types.FunctionDeclaration(
        name="fetch_url",
        description="Fetch and read the text content of a specific URL (documentation, blog posts, GitHub repos, etc.).",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "url": types.Schema(type="STRING", description="URL to fetch"),
                "max_chars": types.Schema(type="INTEGER", description="Max characters to return, default 6000"),
            },
            required=["url"]
        )
    ),
    types.FunctionDeclaration(
        name="get_director_self_analysis",
        description="Director analyzes its own capabilities: tools inventory, API integration status, memory count, limitations, and self-improvement recommendations.",
        parameters=types.Schema(type="OBJECT", properties={})
    ),
    types.FunctionDeclaration(
        name="create_recommendation",
        description="Write a new improvement recommendation to the database. Use this when you identify a concrete, actionable improvement opportunity.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "module_name": types.Schema(type="STRING", description="e.g. clip_pipeline, editor, director, system"),
                "title": types.Schema(type="STRING", description="Short, clear title"),
                "description": types.Schema(type="STRING", description="Detailed description of what to do and why"),
                "priority": types.Schema(type="INTEGER", description="1=critical, 2=high, 3=medium, 4=low, 5=nice-to-have"),
                "impact": types.Schema(type="STRING", description="Expected impact: yüksek/orta/düşük"),
                "effort": types.Schema(type="STRING", description="Implementation effort estimate"),
                "what_it_solves": types.Schema(type="STRING", description="What problem or opportunity this addresses"),
                "how_to_integrate": types.Schema(type="STRING", description="Concrete steps to implement"),
                "why_recommended": types.Schema(type="STRING", description="Reasoning and evidence behind this recommendation"),
            },
            required=["module_name", "title", "description", "priority"]
        )
    ),
    types.FunctionDeclaration(
        name="get_cost_breakdown",
        description="Get pipeline cost breakdown from token usage data. Aggregated by day, step, or job.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "days": types.Schema(type="INTEGER", description="Look-back period, default 30"),
                "per": types.Schema(type="STRING", description="Aggregation: day | step | job"),
            }
        )
    ),
    types.FunctionDeclaration(
        name="detect_cost_anomalies",
        description="Detect pipeline jobs with abnormal cost (2σ above or below mean). Returns list of anomalous jobs.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "threshold_sigma": types.Schema(type="NUMBER", description="Z-score threshold, default 2.0"),
            }
        )
    ),
    types.FunctionDeclaration(
        name="get_pass_rate_trend",
        description="Compare pass rate last 30 days vs previous 30 days. Shows whether AI quality is improving, stable, or declining.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "channel_id": types.Schema(type="STRING", description="Optional channel filter"),
            }
        )
    ),
    types.FunctionDeclaration(
        name="get_analyses_history",
        description="Fetch past Director analysis records from director_analyses table.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "module": types.Schema(type="STRING", description="Filter by module name"),
                "limit": types.Schema(type="INTEGER", description="Number of records, default 10"),
            }
        )
    ),
    types.FunctionDeclaration(
        name="trigger_analysis",
        description="Trigger an on-demand analysis of a module. Collects current metrics, calculates scores, saves to director_analyses, and returns a summary.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "module": types.Schema(type="STRING", description="Module to analyze: clip_pipeline | editor | director | all"),
                "depth": types.Schema(type="STRING", description="Analysis depth: standard | deep. Standard is faster."),
            },
            required=["module"]
        )
    ),
    types.FunctionDeclaration(
        name="update_channel_dna",
        description="Update Channel DNA fields for a channel. Only updates the provided fields, leaves others unchanged.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "channel_id": types.Schema(type="STRING", description="Channel ID to update"),
                "updates": types.Schema(type="STRING", description="JSON string of fields to update in channel_dna. E.g. {\"do_list\": [...], \"tone\": \"...\"} "),
                "reason": types.Schema(type="STRING", description="Why this update is being made"),
            },
            required=["channel_id", "updates"]
        )
    ),
    types.FunctionDeclaration(
        name="compare_channels",
        description="Compare two channels side-by-side on a metric (pass_rate, avg_confidence, clip_count, cost). Returns stats for both channels and a suggestion.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "channel_a": types.Schema(type="STRING", description="First channel ID"),
                "channel_b": types.Schema(type="STRING", description="Second channel ID"),
                "metric": types.Schema(type="STRING", description="Metric to compare: pass_rate | avg_confidence | clip_count | cost"),
            },
            required=["channel_a", "channel_b"]
        )
    ),
    types.FunctionDeclaration(
        name="audit_channel_dna",
        description="Run a 6-point health audit on a channel's DNA: freshness, consistency, performance reflection, specificity, hook style, duration fit.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "channel_id": types.Schema(type="STRING", description="Channel ID to audit"),
            },
            required=["channel_id"]
        )
    ),
    types.FunctionDeclaration(
        name="send_notification",
        description="Send a notification event to director_events (stub — no email/webhook yet). Use for logging important alerts.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "title": types.Schema(type="STRING", description="Notification title"),
                "message": types.Schema(type="STRING", description="Notification body"),
                "channel_id": types.Schema(type="STRING", description="Optional channel context"),
            },
            required=["title", "message"]
        )
    ),
    types.FunctionDeclaration(
        name="trigger_test",
        description="Create a test run entry in director_test_runs for debugging pipeline behavior without processing real content.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "test_name": types.Schema(type="STRING", description="Name/description of this test run"),
                "channel_id": types.Schema(type="STRING", description="Optional channel ID to test against"),
                "params": types.Schema(type="STRING", description="JSON string of test parameters"),
            },
            required=["test_name"]
        )
    ),
]

GEMINI_TOOLS = [types.Tool(function_declarations=TOOL_DECLARATIONS)]


# ─────────────────────────────────────────────
# Action Tool Implementations
# ─────────────────────────────────────────────

def _get_analyses_history(module: str | None = None, limit: int = 10) -> list[dict]:
    """Fetch director_analyses records."""
    try:
        from app.services.supabase_client import get_client
        client = get_client()
        q = (client.table("director_analyses")
             .select("id,module_name,triggered_by,score,subscores,findings,data_points_used,timestamp")
             .order("timestamp", desc=True).limit(limit))
        if module:
            q = q.eq("module_name", module)
        res = q.execute()
        return res.data or []
    except Exception as e:
        print(f"[Director] get_analyses_history error: {e}")
        return []


def _trigger_analysis(module: str, depth: str = "standard") -> dict:
    """Run on-demand analysis, save to director_analyses, return summary."""
    try:
        from app.services.supabase_client import get_client
        pipeline = db_tools.get_pipeline_stats(30)
        clips = db_tools.get_clip_analysis(None, 30)

        # Compute score inline (avoids circular import with router.py)
        s = (pipeline.get("summary") or {})
        total = int(s.get("total_jobs", 0) or 0)
        completed = int(s.get("completed", 0) or 0)
        ca = (clips.get("analysis") or {})
        total_clips = int(ca.get("total_clips", 0) or 0)
        pass_count = int(ca.get("pass_count", 0) or 0)
        avg_conf = float(ca.get("avg_confidence", 0) or 0)
        success_rate = (completed / total * 100) if total > 0 else 0
        pass_rate = (pass_count / total_clips * 100) if total_clips > 0 else 0
        sr_score = 6 if success_rate >= 100 else 5 if success_rate >= 95 else 4 if success_rate >= 90 else 2 if success_rate >= 80 else 0
        avg_dur = float(s.get("avg_duration_min", 0) or 0)
        dur_score = 4 if avg_dur < 6 else 3 if avg_dur < 8 else 2 if avg_dur < 12 else 0
        tech = sr_score + dur_score + 5
        pr = 8 if pass_rate > 50 else 6 if pass_rate > 35 else 3 if pass_rate > 20 else 0
        cf = 7 if avg_conf >= 8.0 else 5 if avg_conf >= 7.0 else 3 if avg_conf >= 6.0 else 0
        ai_q = pr + cf + 5
        clips_per_job = total_clips / max(total, 1)
        cj = 8 if clips_per_job >= 5 else 5 if clips_per_job >= 3 else 2 if clips_per_job >= 1 else 0
        out_q = cj + 8
        learn = 8 if total < 20 else 10
        overall_score = min(100, round(tech + ai_q + out_q + learn + 3)) if total > 0 else None
        scores = {"overall_score": overall_score,
                  "modules": {"clip_pipeline": {"score": overall_score, "subscores": {
                      "teknik_saglik": tech, "ai_karar": ai_q, "cikti": out_q, "ogrenme": learn}}}}

        client = get_client()
        analysis_row = {
            "module_name": module,
            "triggered_by": "chat",
            "score": scores.get("overall_score") or 0,
            "subscores": scores.get("modules", {}),
            "findings": [
                {"key": "pipeline_summary", "data": pipeline.get("summary", {})},
                {"key": "clip_summary", "data": clips.get("analysis", {})},
            ],
            "recommendations": [],
            "data_points_used": int((pipeline.get("summary") or {}).get("total_jobs", 0) or 0),
        }
        res = client.table("director_analyses").insert(analysis_row).execute()
        analysis_id = res.data[0].get("id") if res.data else None

        return {
            "ok": True,
            "analysis_id": analysis_id,
            "module": module,
            "overall_score": scores.get("overall_score"),
            "modules": scores.get("modules", {}),
            "pipeline_summary": pipeline.get("summary", {}),
        }
    except Exception as e:
        print(f"[Director] trigger_analysis error: {e}")
        return {"error": str(e)}


def _update_channel_dna(channel_id: str, updates_json: str, reason: str = "") -> dict:
    """Update Channel DNA fields. updates_json is a JSON string of fields to merge."""
    try:
        import json as _json
        from app.services.supabase_client import get_client

        updates = _json.loads(updates_json) if isinstance(updates_json, str) else updates_json

        client = get_client()
        # Fetch current DNA
        res = client.table("channels").select("channel_dna").eq("id", channel_id).single().execute()
        if not res.data:
            return {"error": f"Channel {channel_id} not found"}

        current_dna = res.data.get("channel_dna") or {}
        current_dna.update(updates)

        client.table("channels").update({"channel_dna": current_dna}).eq("id", channel_id).execute()

        from app.director.events import director_events
        director_events.emit_sync(
            module="module_1", event="channel_dna_updated",
            payload={"channel_id": channel_id, "changed_fields": list(updates.keys()),
                     "reason": reason, "triggered_by": "director_chat"},
            channel_id=channel_id,
        )

        return {"ok": True, "channel_id": channel_id, "updated_fields": list(updates.keys())}
    except Exception as e:
        print(f"[Director] update_channel_dna error: {e}")
        return {"error": str(e)}


def _audit_channel_dna(channel_id: str) -> dict:
    """6-point DNA health audit."""
    try:
        from app.director.dna_auditor import audit_channel_dna
        return audit_channel_dna(channel_id)
    except Exception as e:
        print(f"[Director] audit_channel_dna error: {e}")
        return {"error": str(e)}


def _send_notification(title: str, message: str, channel_id: str | None = None) -> dict:
    """Stub: log notification to director_events."""
    try:
        from app.director.events import director_events
        director_events.emit_sync(
            module="director",
            event="notification_sent",
            payload={"title": title, "message": message},
            channel_id=channel_id,
        )
        return {"ok": True, "title": title}
    except Exception as e:
        print(f"[Director] send_notification error: {e}")
        return {"error": str(e)}


def _trigger_test(test_name: str, channel_id: str | None = None, params_json: str = "{}") -> dict:
    """Create a test run entry in director_test_runs."""
    try:
        import json as _json
        from app.services.supabase_client import get_client

        params = {}
        try:
            params = _json.loads(params_json) if params_json else {}
        except Exception:
            pass

        client = get_client()
        res = client.table("director_test_runs").insert({
            "test_name": test_name,
            "channel_id": channel_id,
            "params": params,
            "status": "created",
            "is_test_run": True,
        }).execute()
        test_id = res.data[0].get("id") if res.data else None
        return {"ok": True, "test_id": test_id, "test_name": test_name}
    except Exception as e:
        print(f"[Director] trigger_test error: {e}")
        return {"error": str(e)}


# ─────────────────────────────────────────────
# Tool Dispatcher
# ─────────────────────────────────────────────

def _dispatch_tool(name: str, args: dict[str, Any]) -> Any:
    """Execute a tool by name and return result."""
    if name == "read_file":
        return fs_tools.read_file(args["path"])
    elif name == "list_files":
        return fs_tools.list_files(args["directory"], args.get("pattern", "*"))
    elif name == "search_codebase":
        return fs_tools.search_codebase(args["query"], args.get("file_pattern"))
    elif name == "query_database":
        return db_tools.query_database(args["sql"])
    elif name == "get_pipeline_stats":
        return db_tools.get_pipeline_stats(args.get("days", 7), args.get("channel_id"))
    elif name == "get_clip_analysis":
        return db_tools.get_clip_analysis(args.get("job_id"), args.get("days", 7))
    elif name == "get_channel_dna":
        return db_tools.get_channel_dna(args["channel_id"])
    elif name == "get_recent_events":
        return db_tools.get_recent_events(args.get("module"), args.get("days", 7), args.get("limit", 50))
    elif name == "save_memory":
        return mem_tools.save_memory(args["content"], args["type"], args.get("tags"), "director_inference")
    elif name == "query_memory":
        return mem_tools.query_memory(args["query"], args.get("type"), args.get("top_k", 5))
    elif name == "list_memories":
        return mem_tools.list_memories(args.get("type"))
    elif name == "get_langfuse_data":
        return lf_tools.get_langfuse_data(args.get("step"), args.get("days", 7))
    elif name == "get_sentry_issues":
        return sentry_tools.get_sentry_issues(args.get("days", 7), args.get("resolved", False))
    elif name == "get_posthog_events":
        return ph_tools.get_posthog_events(args.get("event"), args.get("days", 7))
    elif name == "get_railway_status":
        return railway_tools.get_railway_status()
    elif name == "get_railway_logs":
        return railway_tools.get_railway_logs(args.get("service_name"), args.get("limit", 50))
    elif name == "get_deepgram_usage":
        return deepgram_tools.get_deepgram_usage(args.get("days", 7))
    elif name == "web_search":
        return ws_tools.web_search(args["query"], args.get("num_results", 6))
    elif name == "fetch_url":
        return ws_tools.fetch_url(args["url"], args.get("max_chars", 6000))
    elif name == "get_director_self_analysis":
        return sa_tools.get_director_self_analysis()
    elif name == "create_recommendation":
        return db_tools.create_recommendation(
            module_name=args["module_name"],
            title=args["title"],
            description=args["description"],
            priority=args.get("priority", 3),
            impact=args.get("impact", "orta"),
            effort=args.get("effort", ""),
            what_it_solves=args.get("what_it_solves", ""),
            how_to_integrate=args.get("how_to_integrate", ""),
            why_recommended=args.get("why_recommended", ""),
        )
    elif name == "get_cost_breakdown":
        return db_tools.get_cost_breakdown(args.get("days", 30), args.get("per", "day"))
    elif name == "detect_cost_anomalies":
        return db_tools.detect_cost_anomalies(args.get("threshold_sigma", 2.0))
    elif name == "get_pass_rate_trend":
        return db_tools.get_pass_rate_trend(args.get("channel_id"))
    elif name == "get_analyses_history":
        return _get_analyses_history(args.get("module"), args.get("limit", 10))
    elif name == "trigger_analysis":
        return _trigger_analysis(args.get("module", "all"), args.get("depth", "standard"))
    elif name == "update_channel_dna":
        return _update_channel_dna(args["channel_id"], args["updates"], args.get("reason", ""))
    elif name == "compare_channels":
        return db_tools.compare_channels(args["channel_a"], args["channel_b"], args.get("metric", "pass_rate"))
    elif name == "audit_channel_dna":
        return _audit_channel_dna(args["channel_id"])
    elif name == "send_notification":
        return _send_notification(args["title"], args["message"], args.get("channel_id"))
    elif name == "trigger_test":
        return _trigger_test(args["test_name"], args.get("channel_id"), args.get("params", "{}"))
    else:
        return {"error": f"Unknown tool: {name}"}


def _result_summary(result: Any, tool_name: str) -> str:
    """Generate a short human-readable summary of a tool result."""
    try:
        if isinstance(result, str):
            lines = result.splitlines()
            return f"{len(lines)} lines" if len(lines) > 3 else result[:200]
        elif isinstance(result, list):
            return f"{len(result)} rows/items"
        elif isinstance(result, dict):
            if "error" in result:
                return f"Error: {result['error']}"
            keys = list(result.keys())[:4]
            return f"Keys: {keys}"
        return str(result)[:200]
    except Exception:
        return "result received"

# ─────────────────────────────────────────────
# Agent Loop
# ─────────────────────────────────────────────

async def run_agent(
    user_message: str,
    session_id: str,
    conversation_history: list[dict],
    relevant_memories: list[dict],
) -> AsyncGenerator[dict, None]:
    """
    Main Director agent loop. Yields SSE event dicts.
    Runs tool-calling loop until Gemini stops calling tools, then yields final text.
    """
    try:
        client = get_gemini_client()  # Vertex AI — same client as pipeline

        # Build initial context injection
        memory_context = ""
        if relevant_memories:
            mem_lines = [f"- [{m.get('type','note')}] {m.get('content','')}" for m in relevant_memories[:5]]
            memory_context = "\n\nİlgili hafıza:\n" + "\n".join(mem_lines)

        # Build Gemini contents from conversation history
        contents: list[types.Content] = []

        for turn in conversation_history[-20:]:
            role = turn["role"]
            content = turn["content"]
            if role == "user":
                contents.append(types.Content(role="user", parts=[types.Part(text=content)]))
            elif role == "assistant":
                contents.append(types.Content(role="model", parts=[types.Part(text=content)]))

        # Add current user message with memory context
        full_user_msg = user_message
        if memory_context:
            full_user_msg = full_user_msg + memory_context
        contents.append(types.Content(role="user", parts=[types.Part(text=full_user_msg)]))

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=GEMINI_TOOLS,
            temperature=0.3,
        )

        # Tool calling loop
        max_iterations = 10
        iteration = 0
        final_text = ""

        while iteration < max_iterations:
            iteration += 1

            t0 = time.time()
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL_PRO,
                contents=contents,
                config=config,
            )
            duration_ms = int((time.time() - t0) * 1000)

            # Trace this Director call to Langfuse
            try:
                usage = getattr(response, "usage_metadata", None)
                in_tok = getattr(usage, "prompt_token_count", None) if usage else None
                out_tok = getattr(usage, "candidates_token_count", None) if usage else None
                last_user_text = user_message if iteration == 1 else f"[tool_results iteration {iteration}]"
                out_text = ""
                if response.candidates:
                    for part in (response.candidates[0].content.parts or []):
                        if hasattr(part, "text") and part.text:
                            out_text += part.text
                _trace_generation(
                    name="director_chat",
                    model=settings.GEMINI_MODEL_PRO,
                    prompt_input=last_user_text,
                    output=out_text,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    metadata={"session_id": session_id, "iteration": iteration, "duration_ms": duration_ms},
                )
            except Exception:
                pass  # Tracing failure never blocks the agent

            candidate = response.candidates[0] if response.candidates else None
            if not candidate:
                yield {"type": "error", "message": "No response from Gemini"}
                return

            # Collect all parts
            text_parts = []
            function_calls = []

            for part in (candidate.content.parts or []):
                if hasattr(part, "text") and part.text:
                    text_parts.append(part.text)
                if hasattr(part, "function_call") and part.function_call:
                    function_calls.append(part.function_call)

            if not function_calls:
                # No more tool calls — this is the final response
                final_text = "\n".join(text_parts).strip()
                break

            # Add model's response (with function calls) to contents
            contents.append(candidate.content)

            # Execute each function call and collect results
            tool_response_parts = []

            for fc in function_calls:
                tool_name = fc.name
                tool_args = dict(fc.args) if fc.args else {}

                yield {"type": "tool_call", "tool": tool_name, "args": tool_args}

                # Execute
                try:
                    result = _dispatch_tool(tool_name, tool_args)
                except Exception as e:
                    result = {"error": str(e)}

                summary = _result_summary(result, tool_name)
                yield {"type": "tool_result", "tool": tool_name, "summary": summary}

                # Serialize result
                result_str = json.dumps(result, ensure_ascii=False, default=str)
                if len(result_str) > 8000:
                    result_str = result_str[:8000] + "...[truncated]"

                tool_response_parts.append(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"result": result_str},
                    )
                )

            # Add tool results to contents
            contents.append(types.Content(role="user", parts=tool_response_parts))

        if not final_text:
            final_text = "Analiz tamamlandı."

        yield {"type": "text", "text": final_text}
        yield {"type": "done"}

    except Exception as e:
        print(f"[DirectorAgent] Error: {e}")
        yield {"type": "error", "message": str(e)}
