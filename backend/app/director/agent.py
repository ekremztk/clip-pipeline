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

import hashlib
import json
import time
from typing import AsyncGenerator, Any
from google.genai import types

from app.config import settings
from app.director.config import MAX_ITERATIONS_PER_SESSION, MAX_RESULT_CHARS
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

## ARAÇ KULLANIM KURALLARI

ARAÇ KULLANMA — doğrudan cevap ver:
- Selamlaşma, teşekkür, onaylama ("merhaba", "tamam", "teşekkürler", "harika")
- Bu konuşmada zaten araçla öğrendiğin bilgiyi tekrar soruyorsa
- Genel programlama/AI bilgisi soruları
- Kullanıcı sana bilgi VERİYORSA (kaydet ama tarama yapma)
- Fikir, beyin fırtınası, öneri istiyorsa

ARAÇ KULLAN — sisteme bak:
- Spesifik metrik, hata araştırması, güncel durum, dosya içeriği
- Kanal/klip/job/kod hakkında veri
- "Neden çalışmıyor?", "Bu kodda sorun var mı?", "Kaliteyi kontrol et" gibi istekler

ALTIN KURAL: Soruyu araç çağırmadan cevaplayabiliyorsan ÇAĞIRMA.
Aynı aracı aynı argümanlarla HİÇBİR ZAMAN iki kez çağırma.

## KOD ERİŞİM HARİTAN

### Kendi kodlarını okumak için (HER ZAMAN ÇALIŞIR):
`read_own_file` aracını kullan — Docker veya local fark etmez:
  - read_own_file("director/agent.py")          — bu dosya
  - read_own_file("director/router.py")         — API endpoint'leri
  - read_own_file("director/tools/database.py") — DB araçları
  - read_own_file("director/proactive.py")      — proaktif tetikleyiciler
  - read_own_file("director/learning.py")       — öğrenme döngüsü
  - read_own_file("pipeline/orchestrator.py")   — pipeline akışı
  - read_own_file("api/routes/feedback.py")     — feedback API
  - read_own_file("api/routes/clips.py")        — clips API

`get_code_structure(scope="director")` → tüm director dosyalarını listele
`get_code_structure(scope="all")` → projenin tam kod haritası

### Klasik read_file (local'de çalışır, Docker'da path prefix farklı olabilir):
  - backend/app/director/... (local)
  - app/director/... (Docker)

### Frontend (Vercel'de deploy edilir, lokal geliştirmede erişilebilir):
  get_code_structure(scope="frontend") → mevcut olup olmadığını gösterir

### Veritabanı erişimi:
  ✅ OKUMA: Tüm tablolar (query_database ile SELECT)
  ✅ YAZMA: director_* tabloları + channels.channel_dna
  ❌ YAZMA: jobs, clips, transcripts, pipeline_audit_log

## KOD İNCELEME PROTOKOLÜ

Bir şey yanlış gittiğinde veya kod kalitesi sorulduğunda:
1. `get_code_structure(scope="director")` ile dosya haritasını al
2. `read_own_file("director/[ilgili dosya].py")` ile kodu oku
3. `search_codebase(query="[aradığın pattern]", file_pattern="*.py")` ile sistemde ara
4. Bulguları kanıta dayalı raporla: hangi dosya, hangi satır, ne sorun

Hata var dediğinde önce kodu oku. Varsayımla hata bulma.

## ARAÇ KULLANIM REHBERİ

### Pipeline Test Araçları
- create_test_pipeline: Sadece kullanıcı "pipeline başlat/test et" dediğinde. Onay al. Günde max 5.
- get_test_pipeline_status: max 3 kez poll yap.
- analyze_test_results: Sadece pipeline completed olduğunda.

### A/B Test Araçları
- start_ab_test: "2x maliyet" uyarısını kullanıcıya ver, onay al.
- compare_ab_test: Her iki run tamamlandığında.

### Tahmin Araçları
- forecast_monthly_cost / forecast_pipeline_volume: Tahmin olduğunu belirt.
- predict_failure_risk: Pipeline öncesinde risk değerlendirmesi.

## ANALİZ METODOLOJİSİ

Bir analiz yapman istendiğinde veya sorun araştırırken şu protokolü uygula:

### Veri Toplama Sırası (her zaman bu sırayla)
1. **Pipeline sağlığı** → jobs tablosu: status dağılımı, başarı oranı, ortalama süre
2. **Klip kalitesi** → clips tablosu: quality_status, confidence, standalone/hook/arc score dağılımları
3. **Hata logları** → pipeline_audit_log: son 7 günün başarısız adımları
4. **Maliyet** → pipeline_audit_log.token_usage + get_langfuse_data
5. **Kod kalitesi** → read_own_file ile ilgili adım dosyalarını oku (S05, S06 prompt'ları dahil)
6. **Hafıza** → query_memory ile geçmiş bulgulara bak, tekrar araştırma yapma

### Analiz Kalitesi Kuralları
- **Sayı olmadan sonuç yok.** "Pass rate düşük" diyorsan yanında sayıyı söyle.
- **Kök neden bul.** "S06 çok eleme yapıyor" → S06 batch_evaluation.py'yi oku, threshold'lara bak.
- **Kendi körlerini bil.** Langfuse 429 dönüyorsa "maliyet verisi yok" de, tahmin etme.
- **Hafızayı güncelle.** Her önemli bulgu → save_memory(type='analysis_insight').
- **Öneri spesifikliği.** "Promptu iyileştir" değil, "standalone_score eşiğini 7'den 6'ya düşür, çünkü X% klip 6.5-7.0 arasında kalıyor" gibi.

### Kör Noktalar (bunları her zaman test et)
- Langfuse API: 429 veriyorsa kopuk. get_langfuse_data sonucunda "error" var mı kontrol et.
- Deepgram Usage API: 403 verebilir, kopuksa "maliyet verisi yok" de.
- Sentry: 400/401 verebilir, hata listesi yoksa belirt.
- Director hafızası: query_database SELECT COUNT(*) FROM director_memory — boşsa "sıfırdan başlıyorum" de.
- trigger_analysis: Bu araç formül hesaplıyor (aritmetik), gerçek AI analizi değil.

## Temel Prensipler

1. **Araçlarla düşün.** "S05 yavaş görünüyor" → önce query_database ile gerçek süreleri bak.
2. **Kodu oku.** Hata bulduğunda read_own_file ile doğrula. "Satır X'te Y var" → kaynak göster.
3. **Kasıtlı tasarım kararlarını tanı.** Şüphe duyduğunda docs/ oku.
4. **Hafıza kullan.** query_memory ile geçmişe bak, öğrendiklerini save_memory ile kaydet.
5. **Cesur ol.** Sistem seviyesi değişiklikler öner.
6. **Sonuçları kaydet.** Önemli bulgular → create_recommendation + save_memory.

## Sistem Yapısı

- **Module 1**: 8-adımlı pipeline (S01-S08), Gemini Pro ile klip keşfi ve değerlendirme
- **Module 2**: Editor (OpenCut), Reframe (yüz takibi), Auto Captions (Deepgram)
- **Stack**: Railway (FastAPI) + Vercel (Next.js) + Supabase + Cloudflare R2
- **Models**: gemini-3.1-pro-preview (S05, S06), gemini-2.5-flash (diğerleri)
- **Director araçları**: ~45 fonksiyon — DB, filesystem, memory, monitoring, prediction, A/B test

## Dokümanlar

- docs/MODULE_1_CLIP_EXTRACTOR.md
- docs/MODULE_2_EDITOR.md
- docs/SYSTEM_CORE.md
- docs/DIRECTOR_MODULE.md

## Kısıtlamalar

- Railway CPU-only — PyTorch/TensorFlow/WhisperX yok
- DATABASE_URL port 6543 olmalı (5432 değil)
- Kod değişikliği yapma yetkisi yok — öneriler sun, kullanıcı uygular
- Kilitli: reframer.py, app/memory/, next.config.js, s01-s04 pipeline adımları

Türkçe konuş. Kısa ve net ol. Hata/sorun bulduğunda dosya:satır referansı ver."""

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
        name="get_code_structure",
        description="Get a full tree of all project source files. Use this to discover what files exist before reading them. scope: all | director | pipeline | api | frontend",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "scope": types.Schema(type="STRING", description="all | director | pipeline | api | frontend. Default: all"),
            }
        )
    ),
    types.FunctionDeclaration(
        name="read_own_file",
        description="Read any backend/app source file using runtime path — always works regardless of Docker or local. Use module_path relative to backend/app/. Examples: 'director/agent.py', 'pipeline/orchestrator.py', 'api/routes/feedback.py', 'director/tools/database.py'",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "module_path": types.Schema(type="STRING", description="Path relative to backend/app/, e.g. 'director/agent.py'"),
            },
            required=["module_path"]
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
                "what": types.Schema(type="STRING", description="Concrete action: what exactly should be done"),
                "why": types.Schema(type="STRING", description="Reasoning: why this matters, evidence from data"),
                "expected_impact": types.Schema(type="STRING", description="What will improve and by how much if implemented"),
                "priority": types.Schema(type="INTEGER", description="1=critical, 2=high, 3=medium, 4=low, 5=nice-to-have"),
                "effort": types.Schema(type="STRING", description="Implementation effort estimate, e.g. '2 saat', '1 gün'"),
                "risk": types.Schema(type="STRING", description="Potential risks or downsides"),
                "description": types.Schema(type="STRING", description="Additional context or implementation notes"),
            },
            required=["module_name", "title", "what", "why", "expected_impact", "priority"]
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
        description="Calculates a formula-based 5-dimension score from current DB metrics and saves to director_analyses. NOTE: This is arithmetic, not AI analysis. Use query_database + read_own_file for real investigation.",
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
    types.FunctionDeclaration(
        name="create_test_pipeline",
        description="Start a test pipeline run with a video (is_test_run=True). Use get_test_pipeline_status to monitor progress.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "channel_id": types.Schema(type="STRING", description="Channel. Default: speedy_cast"),
                "title": types.Schema(type="STRING", description="Test run title"),
                "guest_name": types.Schema(type="STRING"),
                "video_url": types.Schema(type="STRING", description="R2 URL or leave empty for default test video"),
            },
        )
    ),
    types.FunctionDeclaration(
        name="get_test_pipeline_status",
        description="Get detailed status of a running or completed test pipeline.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"job_id": types.Schema(type="STRING")},
            required=["job_id"]
        )
    ),
    types.FunctionDeclaration(
        name="analyze_test_results",
        description="Deep analysis of a completed test pipeline.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"job_id": types.Schema(type="STRING")},
            required=["job_id"]
        )
    ),
    types.FunctionDeclaration(
        name="get_active_pipelines",
        description="List all currently running or queued pipelines.",
        parameters=types.Schema(type="OBJECT", properties={})
    ),
    types.FunctionDeclaration(
        name="forecast_monthly_cost",
        description="Project end-of-month cost (Gemini + Railway).",
        parameters=types.Schema(type="OBJECT", properties={})
    ),
    types.FunctionDeclaration(
        name="forecast_pipeline_volume",
        description="Pipeline usage trend and next-30-day projection.",
        parameters=types.Schema(type="OBJECT", properties={})
    ),
    types.FunctionDeclaration(
        name="predict_failure_risk",
        description="Predict pipeline failure risk based on video duration and channel history.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "video_duration_s": types.Schema(type="NUMBER"),
                "channel_id": types.Schema(type="STRING"),
            },
        )
    ),
    types.FunctionDeclaration(
        name="forecast_capacity",
        description="Check system capacity — DB table sizes and growth warnings.",
        parameters=types.Schema(type="OBJECT", properties={})
    ),
    types.FunctionDeclaration(
        name="get_editor_engagement_stats",
        description="Which clip quality verdicts are most opened in the editor? Breakdown by pass/fixable/fail.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"channel_id": types.Schema(type="STRING")},
            required=["channel_id"]
        )
    ),
    types.FunctionDeclaration(
        name="get_clips_opened_but_not_published",
        description="List clips that were opened in editor but never published — potential waste.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"channel_id": types.Schema(type="STRING")},
            required=["channel_id"]
        )
    ),
    types.FunctionDeclaration(
        name="get_editor_conversion_rate",
        description="What percentage of clips opened in editor actually get published?",
        parameters=types.Schema(
            type="OBJECT",
            properties={"channel_id": types.Schema(type="STRING")},
            required=["channel_id"]
        )
    ),
    types.FunctionDeclaration(
        name="start_ab_test",
        description="Start an A/B test — runs two parallel pipelines with the same video. Costs 2x. Ask user confirmation first.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "test_name": types.Schema(type="STRING", description="Name for this A/B test"),
                "channel_id": types.Schema(type="STRING", description="Channel ID, default: speedy_cast"),
                "video_url": types.Schema(type="STRING", description="R2 video URL or leave empty for default"),
                "description": types.Schema(type="STRING", description="What this test is comparing"),
            },
            required=["test_name"]
        )
    ),
    types.FunctionDeclaration(
        name="compare_ab_test",
        description="Compare results of a completed A/B test. Both runs must be finished.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"test_id": types.Schema(type="STRING", description="Test ID from start_ab_test")},
            required=["test_id"]
        )
    ),
    types.FunctionDeclaration(
        name="check_dependency_impact",
        description="Analyze what breaks if a service/component goes down. E.g. 'gemini_pro', 'r2_storage', 'deepgram'.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"component": types.Schema(type="STRING", description="Service name: r2_storage, deepgram, gemini_pro, supabase, etc.")},
            required=["component"]
        )
    ),
    types.FunctionDeclaration(
        name="get_dependency_map",
        description="Get the full system dependency map — all services and their dependents.",
        parameters=types.Schema(type="OBJECT", properties={})
    ),
    types.FunctionDeclaration(
        name="get_cross_module_signals",
        description="Fetch recent cross-module signal flow (M1->M2 and back) from the database.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "channel_id": types.Schema(type="STRING"),
                "days": types.Schema(type="INTEGER", description="Look-back period, default 7"),
            }
        )
    ),
    types.FunctionDeclaration(
        name="create_execution_plan",
        description="Generate a step-by-step implementation plan for a recommendation. Shows files, actions, and risk levels.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"recommendation_id": types.Schema(type="STRING", description="Recommendation ID to plan")},
            required=["recommendation_id"]
        )
    ),
    types.FunctionDeclaration(
        name="analyze_prompt_performance",
        description="Analyze how prompt versions perform for a pipeline step (S05/S06). Shows weekly trends.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "step": types.Schema(type="STRING", description="Pipeline step: s05 or s06"),
                "days": types.Schema(type="INTEGER", description="Look-back period, default 30"),
            }
        )
    ),
    types.FunctionDeclaration(
        name="suggest_prompt_improvement",
        description="Analyze current performance and suggest specific prompt improvements based on weak content types, confidence calibration, and discovery volume.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "step": types.Schema(type="STRING", description="Pipeline step: s05 or s06"),
            }
        )
    ),
    types.FunctionDeclaration(
        name="cross_channel_analysis",
        description="Compare ALL channels side-by-side: pass rate, cost, volume, content types. Shows rankings and cross-pollination suggestions.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "days": types.Schema(type="INTEGER", description="Look-back period, default 30"),
            }
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


def _sanitize_json(obj):
    """Recursively convert Decimal/datetime to JSON-safe types."""
    from decimal import Decimal
    import datetime
    if isinstance(obj, dict):
        return {k: _sanitize_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_json(v) for v in obj]
    elif isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    return obj


def _trigger_analysis(module: str, depth: str = "standard") -> dict:
    """Run on-demand analysis using the 5-dimension scorer, save to director_analyses."""
    try:
        from app.services.supabase_client import get_client
        from app.director.analysis.scorer import calculate_scores

        days = 60 if depth == "deep" else 30
        scores = calculate_scores(days=days)

        pipeline = db_tools.get_pipeline_stats(days)

        overall_score = scores.get("overall_score")
        if overall_score is None:
            return {"ok": True, "module": module, "overall_score": None,
                    "reason": "Not enough data for scoring"}

        client = get_client()
        analysis_row = _sanitize_json({
            "module_name": module,
            "triggered_by": "chat",
            "score": overall_score,
            "subscores": scores.get("dimensions", {}),
            "findings": [
                {"key": "pipeline_summary", "data": pipeline.get("summary", {})},
                {"key": "scorer_dimensions", "data": scores.get("dimensions", {})},
            ],
            "recommendations": [],
            "data_points_used": scores.get("data_points", 0),
        })
        res = client.table("director_analyses").insert(analysis_row).execute()
        analysis_id = res.data[0].get("id") if res.data else None

        return {
            "ok": True,
            "analysis_id": analysis_id,
            "module": module,
            "overall_score": overall_score,
            "dimensions": scores.get("dimensions", {}),
            "data_points": scores.get("data_points", 0),
            "period_days": days,
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
    elif name == "get_code_structure":
        return fs_tools.get_code_structure(args.get("scope", "all"))
    elif name == "read_own_file":
        return fs_tools.read_own_file(args["module_path"])
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
            what=args["what"],
            why=args["why"],
            expected_impact=args["expected_impact"],
            priority=args.get("priority", 3),
            effort=args.get("effort", ""),
            risk=args.get("risk", ""),
            description=args.get("description", ""),
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
    elif name == "create_test_pipeline":
        from app.director.tools.pipeline_executor import create_test_job
        return create_test_job(video_url=args.get("video_url"), channel_id=args.get("channel_id", "speedy_cast"),
                               title=args.get("title", "Director Test Run"), guest_name=args.get("guest_name"))
    elif name == "get_test_pipeline_status":
        from app.director.tools.pipeline_executor import get_test_pipeline_status
        return get_test_pipeline_status(args["job_id"])
    elif name == "analyze_test_results":
        from app.director.tools.pipeline_executor import analyze_test_results
        return analyze_test_results(args["job_id"])
    elif name == "get_active_pipelines":
        from app.director.tools.pipeline_executor import get_active_pipelines
        return get_active_pipelines()
    elif name == "forecast_monthly_cost":
        from app.director.predictive.forecaster import forecast_monthly_cost
        return forecast_monthly_cost()
    elif name == "forecast_pipeline_volume":
        from app.director.predictive.forecaster import forecast_pipeline_volume
        return forecast_pipeline_volume()
    elif name == "predict_failure_risk":
        from app.director.predictive.forecaster import predict_failure_risk
        return predict_failure_risk(args.get("video_duration_s"), args.get("channel_id"))
    elif name == "forecast_capacity":
        from app.director.predictive.forecaster import forecast_capacity
        return forecast_capacity()
    elif name == "get_editor_engagement_stats":
        from app.director.tools.editor_intelligence import get_editor_engagement_stats
        return get_editor_engagement_stats(args["channel_id"])
    elif name == "get_clips_opened_but_not_published":
        from app.director.tools.editor_intelligence import get_clips_opened_but_not_published
        return get_clips_opened_but_not_published(args["channel_id"])
    elif name == "get_editor_conversion_rate":
        from app.director.tools.editor_intelligence import get_editor_conversion_rate
        return get_editor_conversion_rate(args["channel_id"])
    elif name == "start_ab_test":
        from app.director.tools.ab_test import start_ab_test
        return start_ab_test(
            test_name=args["test_name"],
            channel_id=args.get("channel_id", "speedy_cast"),
            video_url=args.get("video_url"),
            description=args.get("description", ""),
        )
    elif name == "compare_ab_test":
        from app.director.tools.ab_test import compare_ab_test
        return compare_ab_test(args["test_id"])
    elif name == "check_dependency_impact":
        from app.director.dependency_graph import check_dependency_impact
        return check_dependency_impact(args["component"])
    elif name == "get_dependency_map":
        from app.director.dependency_graph import get_full_dependency_map
        return get_full_dependency_map()
    elif name == "get_cross_module_signals":
        from app.director.dependency_graph import get_cross_module_signals
        return get_cross_module_signals(args.get("channel_id"), args.get("days", 7))
    elif name == "create_execution_plan":
        from app.director.execution_planner import create_execution_plan
        return create_execution_plan(args["recommendation_id"])
    elif name == "analyze_prompt_performance":
        from app.director.tools.prompt_lab import analyze_prompt_performance
        return analyze_prompt_performance(step=args.get("step", "s05"), days=args.get("days", 30))
    elif name == "suggest_prompt_improvement":
        from app.director.tools.prompt_lab import suggest_prompt_improvement
        return suggest_prompt_improvement(step=args.get("step", "s05"))
    elif name == "cross_channel_analysis":
        from app.director.tools.cross_channel import cross_channel_analysis
        return cross_channel_analysis(days=args.get("days", 30))
    else:
        return {"error": f"Unknown tool: {name}"}


def _smart_truncate(result: Any, tool_name: str, max_chars: int = MAX_RESULT_CHARS) -> str:
    """Truncate tool results intelligently, preserving structure."""
    try:
        if isinstance(result, list) and len(result) > 20:
            return json.dumps({
                "total_count": len(result),
                "first_10": result[:10],
                "last_5": result[-5:],
                "note": f"{len(result)} sonuçtan 15'i gösteriliyor"
            }, ensure_ascii=False, default=str)
        result_str = json.dumps(result, ensure_ascii=False, default=str)
        if len(result_str) > max_chars:
            return result_str[:max_chars] + f"...[truncated, {len(result_str)} chars total]"
        return result_str
    except Exception:
        return str(result)[:max_chars]


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
    use_tools: bool = True,
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
            tools=GEMINI_TOOLS if use_tools else None,
            temperature=0.3,
        )

        # Tool calling loop
        max_iterations = MAX_ITERATIONS_PER_SESSION
        iteration = 0
        final_text = ""
        _tool_call_hashes: set[str] = set()
        _consecutive_errors = 0
        _MAX_CONSECUTIVE_ERRORS = 4  # stop spiraling if tools keep failing

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

                # Dedup guard
                call_key = f"{tool_name}:{hashlib.md5(json.dumps(tool_args, sort_keys=True).encode()).hexdigest()}"
                if call_key in _tool_call_hashes:
                    result = {"note": "Bu araç aynı argümanlarla zaten çağrıldı. Mevcut sonucu kullan."}
                    yield {"type": "tool_call", "tool": tool_name, "args": tool_args}
                    yield {"type": "tool_result", "tool": tool_name, "summary": "duplicate — skipped"}
                else:
                    _tool_call_hashes.add(call_key)
                    yield {"type": "tool_call", "tool": tool_name, "args": tool_args}

                    # Execute
                    try:
                        result = _dispatch_tool(tool_name, tool_args)
                    except Exception as e:
                        result = {"error": str(e)}

                    # Track consecutive errors to stop runaway debug spirals
                    if isinstance(result, dict) and "error" in result:
                        _consecutive_errors += 1
                        if _consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
                            summary = _result_summary(result, tool_name)
                            yield {"type": "tool_result", "tool": tool_name, "summary": summary}
                            final_text = (
                                f"⚠️ Araç çağrıları art arda {_consecutive_errors} kez hata döndürdü, "
                                f"döngü durduruldu. Son hata: {result.get('error', 'bilinmiyor')}\n"
                                "Lütfen sorunun ne olduğunu söyleyin ya da daha spesifik bir komut deneyin."
                            )
                            yield {"type": "text", "text": final_text}
                            yield {"type": "done"}
                            return
                    else:
                        _consecutive_errors = 0

                    summary = _result_summary(result, tool_name)
                    yield {"type": "tool_result", "tool": tool_name, "summary": summary}

                # Serialize result
                result_str = _smart_truncate(result, tool_name)

                tool_response_parts.append(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"result": result_str},
                    )
                )

            # Add tool results to contents
            contents.append(types.Content(role="user", parts=tool_response_parts))

        if not final_text:
            final_text = f"Analiz tamamlandı ({iteration} iterasyon, {len(_tool_call_hashes)} araç çağrısı)."

        yield {"type": "text", "text": final_text}
        yield {"type": "done"}

    except Exception as e:
        print(f"[DirectorAgent] Error: {e}")
        yield {"type": "error", "message": str(e)}
