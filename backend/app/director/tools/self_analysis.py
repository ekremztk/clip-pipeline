"""Director self-analysis tool — Director inspects its own capabilities and limitations."""

import os


def get_director_self_analysis() -> dict:
    """
    Director analyzes itself:
    - Tool inventory with categories
    - API integration status
    - Memory and recommendation counts
    - Current limitations (with severity)
    - Self-improvement recommendations
    - What it can/cannot write to
    """
    try:
        # ── Tool Inventory ──────────────────────────────────
        tools = [
            {"name": "read_file",               "category": "filesystem",      "status": "active"},
            {"name": "list_files",              "category": "filesystem",      "status": "active"},
            {"name": "search_codebase",         "category": "filesystem",      "status": "active"},
            {"name": "query_database",          "category": "database",        "status": "active"},
            {"name": "get_pipeline_stats",      "category": "database",        "status": "active"},
            {"name": "get_clip_analysis",       "category": "database",        "status": "active"},
            {"name": "get_channel_dna",         "category": "database",        "status": "active"},
            {"name": "get_recent_events",       "category": "database",        "status": "active"},
            {"name": "save_memory",             "category": "memory",          "status": "active"},
            {"name": "query_memory",            "category": "memory",          "status": "active"},
            {"name": "list_memories",           "category": "memory",          "status": "active"},
            {"name": "create_recommendation",   "category": "action",          "status": "active"},
            {"name": "get_langfuse_data",       "category": "monitoring",      "status": "active"},
            {"name": "get_sentry_issues",       "category": "monitoring",      "status": "active"},
            {"name": "get_posthog_events",      "category": "monitoring",      "status": "active"},
            {"name": "get_railway_status",      "category": "infrastructure",  "status": "active"},
            {"name": "get_railway_logs",        "category": "infrastructure",  "status": "active"},
            {"name": "get_deepgram_usage",      "category": "monitoring",      "status": "active"},
            {"name": "web_search",              "category": "internet",        "status": "active"},
            {"name": "fetch_url",               "category": "internet",        "status": "active"},
            {"name": "get_director_self_analysis", "category": "self",         "status": "active"},
        ]

        # ── Integration Status ──────────────────────────────
        integrations = {
            "vertex_ai": {
                "active": bool(os.getenv("GCP_PROJECT")),
                "purpose": "Gemini Pro — Director'ın düşünme motoru",
                "note": None,
            },
            "langfuse": {
                "active": bool(os.getenv("LANGFUSE_SECRET_KEY")),
                "purpose": "AI maliyet ve performans takibi",
                "note": None if os.getenv("LANGFUSE_SECRET_KEY") else "LANGFUSE_SECRET_KEY eksik",
            },
            "sentry": {
                "active": bool(os.getenv("SENTRY_DSN")),
                "purpose": "Hata yakalama ve izleme",
                "note": None if os.getenv("SENTRY_AUTH_TOKEN") else "SENTRY_AUTH_TOKEN eksik — hata listesi API erişimi yok",
            },
            "posthog": {
                "active": bool(os.getenv("POSTHOG_API_KEY")),
                "purpose": "Frontend kullanıcı davranışı analizi",
                "note": None if os.getenv("POSTHOG_PROJECT_ID") else "POSTHOG_PROJECT_ID eksik",
            },
            "railway": {
                "active": bool(os.getenv("RAILWAY_API_TOKEN")),
                "purpose": "Deployment izleme ve log erişimi",
                "note": None,
            },
            "deepgram": {
                "active": bool(os.getenv("DEEPGRAM_API_KEY")),
                "purpose": "Transkripsiyon servisi maliyetleri",
                "note": None,
            },
            "brave_search": {
                "active": bool(os.getenv("BRAVE_SEARCH_API_KEY")),
                "purpose": "Kapsamlı internet araması",
                "note": None if os.getenv("BRAVE_SEARCH_API_KEY") else "BRAVE_SEARCH_API_KEY eksik — DuckDuckGo fallback aktif (kısıtlı)",
            },
            "supabase": {
                "active": bool(os.getenv("SUPABASE_URL")),
                "purpose": "Ana veritabanı",
                "note": None,
            },
        }

        # ── Memory & Recommendation Counts ─────────────────
        try:
            from app.director.tools.memory import list_memories
            memories = list_memories()
            memory_count = len(memories) if isinstance(memories, list) else 0
        except Exception:
            memory_count = 0

        try:
            from app.services.supabase_client import get_client
            client = get_client()
            recs = client.table("director_recommendations").select("id,status").execute()
            all_recs = recs.data or []
            total_recs = len(all_recs)
            pending_recs = sum(1 for r in all_recs if r.get("status") == "pending")
        except Exception:
            total_recs = 0
            pending_recs = 0

        # ── Limitations ─────────────────────────────────────
        limitations = [
            {
                "title": "Kod yazma yetkisi yok",
                "detail": "Read-only modundayım. Kod değişikliklerini öneri olarak sunarım, kullanıcı uygular.",
                "severity": "medium",
                "workaround": "Önerileri detaylı açıkla, hangi dosya hangi satır değişmeli belirt.",
            },
            {
                "title": "DB yazma kısıtlı",
                "detail": "Sadece director_memory, director_recommendations, director_conversations, director_events tablolarına yazabiliyorum.",
                "severity": "low",
                "workaround": "Mevcut yazma yetkileri analiz ve hafıza için yeterli.",
            },
            {
                "title": "Otomatik zamanlama yok",
                "detail": "Cron/scheduler entegrasyonu yok. Analizler manuel tetikleniyor.",
                "severity": "high",
                "workaround": "Kullanıcı periyodik olarak 'tam analiz çalıştır' diyebilir veya harici cron /director/run-analysis endpoint'ini çağırabilir.",
            },
            {
                "title": "Dashboard real-time güncelleme yok",
                "detail": "Analiz sonuçları dashboard'a otomatik yansımıyor. Manuel refresh gerekiyor.",
                "severity": "medium",
                "workaround": "Analiz sonrası kullanıcıya 'Dashboard'ı yenile' diyorum.",
            },
        ]

        if not os.getenv("BRAVE_SEARCH_API_KEY"):
            limitations.append({
                "title": "İnternet araması kısıtlı",
                "detail": "Brave Search API key yok. DuckDuckGo fallback — abstract ve related topics verir, tam web araması değil.",
                "severity": "medium",
                "workaround": "search.brave.com'dan ücretsiz tier al, BRAVE_SEARCH_API_KEY env var olarak ekle.",
            })

        if not os.getenv("SENTRY_AUTH_TOKEN"):
            limitations.append({
                "title": "Sentry hata listesi erişimi yok",
                "detail": "Sentry SDK aktif (hataları yakalar) ama REST API'ye erişemiyorum. SENTRY_AUTH_TOKEN eksik.",
                "severity": "medium",
                "workaround": "sentry.io → Settings → Auth Tokens → Create, Railway'e SENTRY_AUTH_TOKEN ekle.",
            })

        # ── Self-Improvement Recommendations ────────────────
        self_recommendations = [
            {
                "priority": 1,
                "title": "BRAVE_SEARCH_API_KEY ekle",
                "category": "internet_access",
                "why": "Güncel araçları, kütüphaneleri, entegrasyon seçeneklerini araştırmak için kaliteli internet araması şart. DuckDuckGo fallback çok kısıtlı.",
                "how": "search.brave.com → Ücretsiz API key (2000 sorgu/ay). Railway env var: BRAVE_SEARCH_API_KEY",
                "impact": "yüksek",
                "effort": "5 dakika",
            },
            {
                "priority": 2,
                "title": "Gece analiz cron'u kur",
                "category": "automation",
                "why": "Her gece 03:00'da otomatik sistem taraması: pipeline stats, klip kalitesi, maliyet analizi, öneriler güncelleme.",
                "how": "Railway → Add Cron Service → Schedule: 0 3 * * * → Command: curl -X POST https://[backend]/director/run-analysis",
                "impact": "yüksek",
                "effort": "15 dakika",
            },
            {
                "priority": 3,
                "title": "SENTRY_AUTH_TOKEN ekle",
                "category": "monitoring",
                "why": "Hata detaylarını, stack trace'leri ve frekansları görebilmek için API erişimi lazım.",
                "how": "sentry.io → Settings → Auth Tokens → Create Token → Railway'e SENTRY_AUTH_TOKEN ekle",
                "impact": "orta",
                "effort": "5 dakika",
            },
            {
                "priority": 4,
                "title": "Hafıza seeding — sistem bağlamı yükle",
                "category": "memory",
                "why": f"Şu an {memory_count} hafıza kaydım var. Sistem dokümantasyonu ve kararları hafızama yüklenmeli ki daha iyi analiz yapayım.",
                "how": "Bana 'hafızana sistem bağlamını yükle' de — CLAUDE.md, DIRECTOR_MODULE.md, kritik kararlar save_memory ile kaydedeyim.",
                "impact": "yüksek",
                "effort": "1 saat (otomatik)",
            },
            {
                "priority": 5,
                "title": "Pipeline event hook'ları",
                "category": "monitoring",
                "why": "S05, S06 gibi adımlar tamamlandığında Director'a event gönderilmeli. Şu an pipeline telemetri kör.",
                "how": "Her pipeline adımına director_events'e INSERT ekle. Başarı/başarısızlık/süre bilgisi.",
                "impact": "orta",
                "effort": "2 saat",
            },
        ]

        active_integrations = sum(1 for v in integrations.values() if v.get("active"))

        return {
            "summary": {
                "total_tools": len(tools),
                "memory_records": memory_count,
                "total_recommendations_created": total_recs,
                "pending_recommendations": pending_recs,
                "active_integrations": active_integrations,
                "total_integrations": len(integrations),
                "readiness_score": round((active_integrations / len(integrations)) * 100),
            },
            "tools_by_category": {
                cat: [t["name"] for t in tools if t["category"] == cat]
                for cat in sorted(set(t["category"] for t in tools))
            },
            "integrations": integrations,
            "limitations": limitations,
            "self_recommendations": self_recommendations,
            "write_access": {
                "allowed": [
                    "director_memory", "director_recommendations", "director_conversations",
                    "director_events", "director_analyses", "director_decision_journal",
                    "director_test_runs", "director_cross_module_signals",
                    "channels.channel_dna (merge update — sadece dna alanı)",
                ],
                "blocked": ["jobs", "clips", "transcripts", "pipeline_audit_log", "channels (diğer alanlar)"],
            },
        }

    except Exception as e:
        print(f"[DirectorSelfAnalysis] error: {e}")
        return {"error": str(e)}
