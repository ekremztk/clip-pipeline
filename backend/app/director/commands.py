"""
Director Slash Commands — predefined tool chains triggered by /command.

Each command maps to a prompt that Director executes with full tool access.
"""

SLASH_COMMANDS: list[dict] = [
    # ── System Analysis ──
    {
        "command": "/sistem-analizi",
        "label": "Sistem Analizi",
        "description": "Tum sistemi analiz et, 5 boyutlu skor hesapla",
        "icon": "chart",
        "category": "analiz",
        "prompt": (
            "Kapsamli bir sistem analizi yap. Sirasiya su araclari kullan:\n"
            "1. get_pipeline_stats (son 30 gun)\n"
            "2. get_clip_analysis (son 30 gun)\n"
            "3. calculate_system_score\n"
            "4. get_langfuse_data\n"
            "Sonuclari 5 boyutta (Teknik Saglik, AI Karar Kalitesi, Cikti Kalitesi, "
            "Ogrenme, Stratejik Olgunluk) degerlendir ve somut oneriler sun."
        ),
    },
    {
        "command": "/saglik",
        "label": "Saglik Durumu",
        "description": "Hizli sistem sagligi kontrolu",
        "icon": "heart",
        "category": "analiz",
        "prompt": (
            "Hizli bir sistem sagligi kontrolu yap. get_pipeline_stats ve get_clip_analysis kullan. "
            "Pipeline basari orani, son hatalar, ortalama sure ve klip kalitesini raporla. "
            "Kritik bir sorun varsa vurgula."
        ),
    },
    {
        "command": "/maliyet",
        "label": "Maliyet Analizi",
        "description": "AI ve transkripsiyon maliyetlerini analiz et",
        "icon": "dollar",
        "category": "analiz",
        "prompt": (
            "Detayli maliyet analizi yap:\n"
            "1. get_langfuse_data ile AI maliyetlerini cek\n"
            "2. get_deepgram_usage ile transkripsiyon maliyetlerini cek\n"
            "3. detect_cost_anomalies ile anormal harcamalari bul\n"
            "4. forecast_monthly_cost ile ay sonu projeksiyonu yap\n"
            "Tasarruf onerileri sun."
        ),
    },
    {
        "command": "/hatalar",
        "label": "Hata Analizi",
        "description": "Son hatalari ve cozum onerilerini goster",
        "icon": "alert",
        "category": "analiz",
        "prompt": (
            "Son hatalari analiz et:\n"
            "1. get_sentry_issues ile Sentry hatalarini cek\n"
            "2. get_pipeline_stats ile pipeline hatalarini incele\n"
            "3. get_railway_logs ile son deployment loglarini kontrol et\n"
            "Her hata icin olasi nedeni ve cozum onerisi sun."
        ),
    },

    # ── Pipeline ──
    {
        "command": "/pipeline",
        "label": "Pipeline Durumu",
        "description": "Aktif ve son pipeline'lari goster",
        "icon": "play",
        "category": "pipeline",
        "prompt": (
            "Pipeline durumunu raporla:\n"
            "1. get_active_pipelines ile aktif isleri goster\n"
            "2. get_pipeline_stats (son 7 gun) ile genel performansi ozetle\n"
            "3. Basarisiz pipeline varsa nedenlerini analiz et."
        ),
    },
    {
        "command": "/klip-kalitesi",
        "label": "Klip Kalitesi",
        "description": "Klip pass rate, confidence ve icerik dagilimi",
        "icon": "star",
        "category": "pipeline",
        "prompt": (
            "Klip kalitesini detayli analiz et:\n"
            "1. get_clip_analysis (son 30 gun)\n"
            "2. get_pass_rate_trend ile trend analizi\n"
            "Pass/fixable/fail dagilimi, ortalama confidence, en iyi ve en kotu icerik tiplerini raporla."
        ),
    },
    {
        "command": "/test-pipeline",
        "label": "Test Pipeline Baslat",
        "description": "Test amacli bir pipeline baslat",
        "icon": "flask",
        "category": "pipeline",
        "prompt": (
            "Kullanici test pipeline baslatmak istiyor. Oncelikle:\n"
            "1. get_active_pipelines ile aktif is var mi kontrol et\n"
            "2. Kullaniciya maliyet bilgisini (yaklasik $0.05-0.15 per run) hatırlat\n"
            "3. Onay aldiktan sonra create_test_pipeline ile baslat"
        ),
    },

    # ── DNA & Channel ──
    {
        "command": "/dna",
        "label": "Channel DNA",
        "description": "Kanal DNA'sini goster ve denetle",
        "icon": "dna",
        "category": "kanal",
        "prompt": (
            "Channel DNA analizi yap:\n"
            "1. query_database ile tum kanallari listele\n"
            "2. Her kanalin DNA'sini get_channel_dna ile cek\n"
            "3. audit_channel_dna ile 6-nokta saglik kontrolu yap\n"
            "Eksik veya guncel olmayan alanlari raporla."
        ),
    },
    {
        "command": "/kanal-karsilastir",
        "label": "Kanal Karsilastirma",
        "description": "Tum kanallari yan yana karsilastir",
        "icon": "columns",
        "category": "kanal",
        "prompt": (
            "Tum kanallari karsilastir:\n"
            "1. cross_channel_analysis ile kanal bazli metrikleri cek\n"
            "En iyi/en kotu performans gosteren kanallari belirle. "
            "Cross-pollination onerileri sun."
        ),
    },

    # ── Research & Recommendations ──
    {
        "command": "/oneri",
        "label": "Oneri Olustur",
        "description": "Sistemi arastir ve gelistirme onerileri olustur",
        "icon": "lightbulb",
        "category": "oneri",
        "prompt": (
            "Kapsamli bir analiz yapip oneriler olustur:\n"
            "1. get_pipeline_stats + get_clip_analysis ile mevcut durumu oku\n"
            "2. get_langfuse_data ile maliyet verisini cek\n"
            "3. get_pass_rate_trend ile trend analizi yap\n"
            "4. web_search ile benzer sistemlerdeki best practice'leri arastir\n"
            "5. create_recommendation ile en az 3 somut, cesur oneri olustur\n"
            "Her oneri icin etki ve implementasyon zorlugu belirt."
        ),
    },
    {
        "command": "/arastir",
        "label": "Internet Arastirmasi",
        "description": "Belirli bir konuyu internette arastir",
        "icon": "search",
        "category": "oneri",
        "prompt": (
            "Kullanicinin belirtecegi konuyu internette arastir. "
            "web_search ve fetch_url araclarini kullanarak detayli bilgi topla. "
            "Sonuclari Prognot sistemine uygulanabilecek sekilde ozetle.\n\n"
            "Hangi konuyu arastirmami istiyorsun?"
        ),
    },

    # ── Memory & Self ──
    {
        "command": "/hafiza",
        "label": "Hafiza Yonetimi",
        "description": "Kayitli hafizalari goster ve yonet",
        "icon": "brain",
        "category": "hafiza",
        "prompt": (
            "Hafiza kayitlarimi goster:\n"
            "1. list_memories ile tum kayitlari listele\n"
            "Tip bazinda grupla (decision, context, plan, note, learning). "
            "Eski veya gecersiz kayitlar varsa temizlik onerisi sun."
        ),
    },
    {
        "command": "/kendini-analiz-et",
        "label": "Director Oz-Analizi",
        "description": "Director kendi yeteneklerini ve limitlerini analiz etsin",
        "icon": "eye",
        "category": "hafiza",
        "prompt": (
            "Kendi yeteneklerini analiz et:\n"
            "1. get_director_self_analysis ile tool envanterini cek\n"
            "2. API entegrasyonlarinin durumunu kontrol et\n"
            "3. Hafiza kullanimi ve limitlerini raporla\n"
            "Eksik yetenekler ve gelistirme onerileri sun."
        ),
    },

    # ── Costs & Forecasting ──
    {
        "command": "/tahmin",
        "label": "Tahmin ve Projeksiyon",
        "description": "Maliyet ve kapasite tahminleri",
        "icon": "trending",
        "category": "tahmin",
        "prompt": (
            "Sistem tahminlerini hesapla:\n"
            "1. forecast_monthly_cost ile ay sonu maliyet projeksiyonu\n"
            "2. forecast_pipeline_volume ile kullanim trendi\n"
            "3. forecast_capacity ile kapasite durumu\n"
            "Riskleri ve onerileri raporla."
        ),
    },
    {
        "command": "/risk",
        "label": "Risk Degerlendirmesi",
        "description": "Sistem risklerini ve bagimlilik etkilerini analiz et",
        "icon": "shield",
        "category": "tahmin",
        "prompt": (
            "Sistem risklerini degerlendir:\n"
            "1. get_dependency_map ile bagimlillik haritasini cek\n"
            "2. check_dependency_impact ile kritik servislerin etkisini analiz et (gemini_pro, deepgram, supabase, r2_storage)\n"
            "3. predict_failure_risk ile pipeline risk seviyesini hesapla\n"
            "Tek nokta arizalari (SPOF) ve onlem onerileri sun."
        ),
    },

    # ── Prompt & AI ──
    {
        "command": "/prompt-analiz",
        "label": "Prompt Performansi",
        "description": "S05/S06 prompt performansini analiz et",
        "icon": "code",
        "category": "ai",
        "prompt": (
            "Prompt performansini analiz et:\n"
            "1. analyze_prompt_performance (s05) ve analyze_prompt_performance (s06)\n"
            "2. suggest_prompt_improvement (s05) ve suggest_prompt_improvement (s06)\n"
            "Zayif icerik tipleri, confidence calibration ve kesfedilen klip sayisini raporla. "
            "Somut prompt iyilestirme onerileri sun."
        ),
    },

    # ── Code ──
    {
        "command": "/kod-tara",
        "label": "Kod Taramasi",
        "description": "Kod tabaninda zayif noktalari ve iyilestirme firsatlarini bul",
        "icon": "file",
        "category": "kod",
        "prompt": (
            "Kod tabanini tara:\n"
            "1. read_file ile kritik dosyalari oku (orchestrator.py, s05, s06, agent.py)\n"
            "2. search_codebase ile hata paternleri ara (bare except, TODO, FIXME, hardcoded)\n"
            "3. Buldugun sorunlari kategorize et (guvenlik, performans, bakim)\n"
            "Somut iyilestirme onerileri sun."
        ),
    },
    {
        "command": "/dosya-oku",
        "label": "Dosya Oku",
        "description": "Belirli bir dosyayi oku ve analiz et",
        "icon": "file",
        "category": "kod",
        "prompt": (
            "Hangi dosyayi okumami istiyorsun? "
            "Dosya yolunu belirt (ornek: backend/app/pipeline/steps/s05_unified_discovery.py)"
        ),
    },
]


def get_commands() -> list[dict]:
    """Return all available slash commands."""
    return SLASH_COMMANDS


def find_command(text: str) -> dict | None:
    """Find a command matching the given text (e.g. '/sistem-analizi')."""
    text = text.strip().lower()
    for cmd in SLASH_COMMANDS:
        if cmd["command"] == text:
            return cmd
    return None


def get_command_categories() -> list[dict]:
    """Return commands grouped by category."""
    cats: dict[str, list[dict]] = {}
    for cmd in SLASH_COMMANDS:
        cat = cmd.get("category", "diger")
        if cat not in cats:
            cats[cat] = []
        cats[cat].append(cmd)

    cat_labels = {
        "analiz": "Analiz",
        "pipeline": "Pipeline",
        "kanal": "Kanal & DNA",
        "oneri": "Oneri & Arastirma",
        "hafiza": "Hafiza & Self",
        "tahmin": "Tahmin & Risk",
        "ai": "AI & Prompt",
        "kod": "Kod",
    }
    return [{"category": k, "label": cat_labels.get(k, k), "commands": v} for k, v in cats.items()]
