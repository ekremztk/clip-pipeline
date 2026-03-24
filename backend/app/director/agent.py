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
from typing import AsyncGenerator, Any
from google import genai
from google.genai import types

from app.config import settings
from app.director.tools import database as db_tools
from app.director.tools import filesystem as fs_tools
from app.director.tools import memory as mem_tools
from app.director.tools import langfuse as lf_tools
from app.director.tools import sentry as sentry_tools
from app.director.tools import posthog as ph_tools
from app.director.tools import railway as railway_tools

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
- Kod dosyalarını düzenlemek için kullanıcı onayı gerekir
- Kilitli dosyalar: reframer.py, memory/, next.config.js, s01-s04 pipeline adımları

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
        name="edit_file",
        description="Replace text in a file. MD files: immediate. Code files: returns requires_confirmation=True, agent asks user before proceeding.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "path": types.Schema(type="STRING"),
                "old_content": types.Schema(type="STRING"),
                "new_content": types.Schema(type="STRING"),
            },
            required=["path", "old_content", "new_content"]
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
]

GEMINI_TOOLS = [types.Tool(function_declarations=TOOL_DECLARATIONS)]

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
    elif name == "edit_file":
        return fs_tools.edit_file(args["path"], args["old_content"], args["new_content"])
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
        client = genai.Client(api_key=settings.GEMINI_API_KEY)

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

            response = client.models.generate_content(
                model=settings.GEMINI_MODEL_PRO,
                contents=contents,
                config=config,
            )

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
