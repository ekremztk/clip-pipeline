"""
Director Slash Commands — predefined tool chains triggered by /command.

Each command maps to a prompt that makes Director use real data queries,
NOT pre-packaged summary functions. Director must form its own intelligent
opinion based on raw data, not auto-computed formulas.
"""

SLASH_COMMANDS: list[dict] = [

    # ── Analiz ──────────────────────────────────────────────────────────
    {
        "command": "/sistem-analizi",
        "label": "Sistem Analizi",
        "description": "Tam sistem analizi yap, tüm boyutlarda gerçek veriyi değerlendir",
        "icon": "chart",
        "category": "analiz",
        "prompt": (
            "Sistemi CEO gözüyle analiz et. Hiçbir hazır fonksiyon kullanma — "
            "her soruyu kendi SQL sorgularınla cevapla.\n\n"
            "Sırasıyla şunları yap:\n\n"
            "1. PIPELINE DURUMU:\n"
            "   query_database ile çalıştır:\n"
            "   SELECT status, COUNT(*) as cnt, "
            "   ROUND(AVG(EXTRACT(EPOCH FROM (completed_at - started_at))/60) "
            "   FILTER (WHERE status='completed' AND started_at IS NOT NULL AND completed_at IS NOT NULL)::NUMERIC,1) as avg_min "
            "   FROM jobs WHERE created_at > now() - interval '30 days' GROUP BY status\n\n"
            "2. KLİP KALİTESİ:\n"
            "   query_database ile çalıştır:\n"
            "   SELECT quality_status, COUNT(*) as cnt, "
            "   ROUND(AVG(confidence*10)::NUMERIC,2) as avg_conf, "
            "   ROUND(AVG(standalone_score)::NUMERIC,2) as avg_standalone "
            "   FROM clips WHERE created_at > now() - interval '30 days' "
            "   GROUP BY quality_status ORDER BY cnt DESC\n\n"
            "3. İÇERİK TİPİ DAĞILIMI:\n"
            "   query_database ile çalıştır:\n"
            "   SELECT content_type, COUNT(*) as cnt FROM clips "
            "   WHERE created_at > now() - interval '30 days' "
            "   GROUP BY content_type ORDER BY cnt DESC LIMIT 10\n\n"
            "4. SON HATALAR:\n"
            "   query_database ile çalıştır:\n"
            "   SELECT step_name, COUNT(*) as errors FROM pipeline_audit_log "
            "   WHERE success = false AND created_at > now() - interval '7 days' "
            "   GROUP BY step_name ORDER BY errors DESC\n\n"
            "5. KANAL BAZLI PERFORMANS:\n"
            "   query_database ile çalıştır:\n"
            "   SELECT j.channel_id, COUNT(DISTINCT j.id) as jobs, COUNT(c.id) as clips "
            "   FROM jobs j LEFT JOIN clips c ON c.job_id = j.id "
            "   WHERE j.created_at > now() - interval '30 days' GROUP BY j.channel_id\n\n"
            "6. S05 ve S06 pipeline adımlarını analiz et:\n"
            "   read_file ile backend/app/pipeline/steps/s05_unified_discovery.py oku — "
            "   prompt kalitesi, model, output parse mantığını değerlendir\n\n"
            "Tüm verileri topladıktan sonra:\n"
            "- Sistemin güçlü olduğu noktaları somut kanıtlarla belirt\n"
            "- Kritik sorunları sırala (kör formül değil, gördüğün gerçek veriye dayandır)\n"
            "- En az 2 create_recommendation ile somut ve uygulanabilir öneri kaydet\n"
            "- trigger_analysis ile bu analizi director_analyses tablosuna kaydet"
        ),
    },
    {
        "command": "/analiz-calistir",
        "label": "Analiz Çalıştır",
        "description": "Kapsamlı sistem araştırması — tüm kaynaklardan veri topla, derinlemesine analiz et",
        "icon": "chart",
        "category": "analiz",
        "prompt": (
            "Prognot sisteminin TAM VE DERİN analizini yap. "
            "Bu bir araştırma protokolü — her adımı sırayla uygula, veri toplamadan sonuç çıkarma.\n\n"

            "## ADIM 1 — PIPELINE SAĞLIĞI\n"
            "query_database:\n"
            "SELECT status, COUNT(*) as cnt, "
            "ROUND(AVG(EXTRACT(EPOCH FROM (completed_at-started_at))/60) "
            "FILTER (WHERE status='completed' AND started_at IS NOT NULL AND completed_at IS NOT NULL)::NUMERIC,1) as avg_min "
            "FROM jobs WHERE created_at > now() - interval '7 days' GROUP BY status\n\n"

            "## ADIM 2 — KLİP KALİTESİ DAĞILIMI\n"
            "query_database:\n"
            "SELECT quality_status, COUNT(*) as cnt, "
            "ROUND(AVG(confidence*10)::NUMERIC,2) as avg_conf, "
            "ROUND(AVG(standalone_score)::NUMERIC,2) as standalone, "
            "ROUND(AVG(hook_score)::NUMERIC,2) as hook, "
            "ROUND(AVG(arc_score)::NUMERIC,2) as arc "
            "FROM clips WHERE created_at > now() - interval '7 days' "
            "GROUP BY quality_status ORDER BY cnt DESC\n\n"

            "## ADIM 3 — PASS RATE TRENDİ (bu hafta vs geçen hafta)\n"
            "query_database:\n"
            "SELECT "
            "COUNT(*) FILTER (WHERE created_at > now()-interval '7 days') as clips_this_week, "
            "COUNT(*) FILTER (WHERE quality_status='passed' AND created_at > now()-interval '7 days') as passed_this_week, "
            "COUNT(*) FILTER (WHERE created_at BETWEEN now()-interval '14 days' AND now()-interval '7 days') as clips_last_week, "
            "COUNT(*) FILTER (WHERE quality_status='passed' AND created_at BETWEEN now()-interval '14 days' AND now()-interval '7 days') as passed_last_week "
            "FROM clips\n\n"

            "## ADIM 4 — PIPELINE HATALARI (son 7 gün)\n"
            "query_database:\n"
            "SELECT step_name, COUNT(*) as errors, "
            "MAX(error_message) as sample_error "
            "FROM pipeline_audit_log "
            "WHERE success = false AND created_at > now() - interval '7 days' "
            "GROUP BY step_name ORDER BY errors DESC\n\n"

            "## ADIM 5 — MALİYET ANALİZİ\n"
            "query_database:\n"
            "SELECT step_name, "
            "ROUND(SUM((token_usage->>'cost_usd')::FLOAT)::NUMERIC,4) as total_cost, "
            "COUNT(*) as runs, "
            "ROUND(AVG((token_usage->>'input_tokens')::INT)::NUMERIC,0) as avg_input_tok "
            "FROM pipeline_audit_log "
            "WHERE token_usage IS NOT NULL AND token_usage::text != '{}' "
            "AND created_at > now() - interval '7 days' "
            "GROUP BY step_name ORDER BY total_cost DESC\n\n"

            "## ADIM 6 — İÇERİK TİPİ PERFORMANSI\n"
            "query_database:\n"
            "SELECT content_type, COUNT(*) as cnt, "
            "ROUND(AVG(confidence*10)::NUMERIC,2) as avg_conf, "
            "COUNT(*) FILTER (WHERE quality_status='passed') as passed "
            "FROM clips WHERE created_at > now() - interval '7 days' "
            "GROUP BY content_type ORDER BY cnt DESC LIMIT 10\n\n"

            "## ADIM 7 — KANAL BAZLI PERFORMANS\n"
            "query_database:\n"
            "SELECT j.channel_id, COUNT(DISTINCT j.id) as jobs, "
            "COUNT(c.id) as clips, "
            "ROUND(COUNT(c.id)::NUMERIC/NULLIF(COUNT(DISTINCT j.id),0),1) as clips_per_job, "
            "ROUND(AVG(c.confidence*10)::NUMERIC,2) as avg_conf "
            "FROM jobs j LEFT JOIN clips c ON c.job_id = j.id "
            "WHERE j.created_at > now() - interval '7 days' "
            "GROUP BY j.channel_id ORDER BY clips DESC\n\n"

            "## ADIM 8 — S05/S06 PROMPT KALİTESİNİ OKU\n"
            "read_own_file ile backend/app/pipeline/prompts/unified_discovery.py oku. "
            "Prompt'un güçlü ve zayıf noktalarını not et. "
            "Sonra read_own_file ile backend/app/pipeline/prompts/batch_evaluation.py oku. "
            "Pass rate %14 gibi düşükse — bu prompt'larda hangi eşik değerleri var, neden bu kadar klip eleniyor?\n\n"

            "## ADIM 9 — LANGFUSE MALİYET VERİSİ\n"
            "get_langfuse_data(days=7) — Gemini maliyet ve token trend verisi.\n\n"

            "## ADIM 10 — DİRECTOR HAFIZASINI KONTROL ET\n"
            "query_database:\n"
            "SELECT type, COUNT(*) as cnt, MAX(created_at) as last_entry "
            "FROM director_memory GROUP BY type ORDER BY cnt DESC\n\n"
            "Sonra list_memories ile son 5 hafıza kaydına bak.\n\n"

            "## ADIM 11 — ÖNCEKİ ANALİZLERE BAK\n"
            "query_database:\n"
            "SELECT id, module_name, score, triggered_by, timestamp "
            "FROM director_analyses ORDER BY timestamp DESC LIMIT 5\n\n"

            "## ADIM 12 — BEKLEYEN ÖNERİLER\n"
            "query_database:\n"
            "SELECT title, module_name, priority, status, created_at "
            "FROM director_recommendations "
            "WHERE status = 'pending' ORDER BY priority ASC, created_at DESC LIMIT 10\n\n"

            "## ADIM 13 — EDİTÖR DAVRANIŞI (approval/rejection sinyalleri)\n"
            "query_database:\n"
            "SELECT user_approved, COUNT(*) as cnt, "
            "ROUND(AVG(confidence*10)::NUMERIC,2) as avg_conf "
            "FROM clips WHERE created_at > now() - interval '7 days' "
            "GROUP BY user_approved\n\n"

            "## ADIM 14 — SENTEZ VE BULGULAR\n"
            "Tüm verileri topladıktan sonra şunları yap:\n"
            "1. Sistemin en kritik 3 sorununu kanıtla destekle (hangi adımdan, hangi sayı)\n"
            "2. Sistemin en güçlü 2 yönünü kanıtla belirt\n"
            "3. Pass rate neden düşük/yüksek? — S06 threshold'larına ve gerçek score dağılımına bakarak kök neden analizi yap\n"
            "4. Maliyet/kalite dengesini değerlendir\n"
            "5. Director'ın kendi körlüklerini (kopuk API'ler, hafıza eksikliği) dürüstçe raporla\n\n"

            "## ADIM 15 — AKSIYONLAR\n"
            "Bulgulara göre EN AZ 5 create_recommendation çağır — her biri somut, ölçülebilir, bu sisteme özel olmalı. "
            "Genel tavsiyeler yasak. 'S06'daki standalone_score eşiğini 7'den 6'ya düşür' gibi spesifik ol.\n"
            "Son olarak save_memory ile bu analizin en kritik bulgusunu kaydet (type='analysis_insight').\n"
            "trigger_analysis ile de bu analizi director_analyses tablosuna kaydet."
        ),
    },

    {
        "command": "/saglik",
        "label": "Sistem Sağlığı",
        "description": "Son 48 saat gerçek pipeline ve hata durumu",
        "icon": "heart",
        "category": "analiz",
        "prompt": (
            "Son 48 saatin sistem sağlığını kontrol et. Gerçek veriye bak:\n\n"
            "1. Son 48 saatteki joblar:\n"
            "   query_database: SELECT id, status, channel_id, error_message, "
            "   ROUND(EXTRACT(EPOCH FROM (completed_at-started_at))/60::NUMERIC,1) as dur_min, "
            "   created_at FROM jobs "
            "   WHERE created_at > now() - interval '48 hours' ORDER BY created_at DESC\n\n"
            "2. Pipeline hata logları:\n"
            "   query_database: SELECT step_name, error_message, created_at "
            "   FROM pipeline_audit_log "
            "   WHERE (success = false OR status = 'failed') "
            "   AND created_at > now() - interval '48 hours' "
            "   ORDER BY created_at DESC LIMIT 20\n\n"
            "3. Son çıkan kliplerin kalitesi:\n"
            "   query_database: SELECT quality_status, confidence, "
            "   standalone_score, hook_score, content_type, created_at "
            "   FROM clips "
            "   WHERE created_at > now() - interval '48 hours' ORDER BY created_at DESC\n\n"
            "Bulguları yorumla. İyi giden ne, dikkat gerektiren ne? "
            "Eğer kritik bir sorun varsa kırmızı bayrak kaldır ve "
            "create_recommendation ile kaydet."
        ),
    },
    {
        "command": "/maliyet",
        "label": "Maliyet Analizi",
        "description": "Gerçek AI ve transkripsiyon maliyetleri",
        "icon": "dollar",
        "category": "analiz",
        "prompt": (
            "Maliyetleri gerçek kaynaklardan analiz et:\n\n"
            "1. get_langfuse_data (days=30) ile Gemini maliyetlerini çek\n"
            "2. get_deepgram_usage (days=30) ile Deepgram maliyetlerini çek\n"
            "3. Job başına maliyet:\n"
            "   query_database: SELECT job_id, "
            "   SUM((token_usage->>'cost_usd')::FLOAT) as cost_usd, "
            "   COUNT(*) as steps "
            "   FROM pipeline_audit_log "
            "   WHERE token_usage IS NOT NULL AND token_usage::text != '{}' "
            "   AND created_at > now() - interval '30 days' "
            "   GROUP BY job_id ORDER BY cost_usd DESC LIMIT 10\n\n"
            "4. Adım bazında maliyet:\n"
            "   query_database: SELECT step_name, "
            "   ROUND(SUM((token_usage->>'cost_usd')::FLOAT)::NUMERIC,4) as total_cost, "
            "   COUNT(*) as runs "
            "   FROM pipeline_audit_log "
            "   WHERE token_usage IS NOT NULL AND token_usage::text != '{}' "
            "   AND created_at > now() - interval '30 days' "
            "   GROUP BY step_name ORDER BY total_cost DESC\n\n"
            "Toplam maliyeti hesapla, en pahalı adımları belirle, "
            "maliyet azaltma fırsatlarını somut olarak öner. "
            "Ay sonu projeksiyon yap."
        ),
    },
    {
        "command": "/hatalar",
        "label": "Hata Analizi",
        "description": "Pipeline ve sistem hataları, kök neden analizi",
        "icon": "alert",
        "category": "analiz",
        "prompt": (
            "Tüm hata kaynaklarını araştır:\n\n"
            "1. Pipeline hataları:\n"
            "   query_database: SELECT step_name, error_message, COUNT(*) as cnt "
            "   FROM pipeline_audit_log "
            "   WHERE (success = false OR status = 'failed') "
            "   AND created_at > now() - interval '7 days' "
            "   GROUP BY step_name, error_message ORDER BY cnt DESC LIMIT 20\n\n"
            "2. Failed joblar:\n"
            "   query_database: SELECT id, channel_id, error_message, created_at "
            "   FROM jobs WHERE status = 'failed' "
            "   AND created_at > now() - interval '7 days' ORDER BY created_at DESC\n\n"
            "3. get_sentry_issues ile uygulama hatalarını çek\n\n"
            "4. get_railway_logs ile son deployment loglarına bak\n\n"
            "Her hata için:\n"
            "- Kök nedeni tahmin et (rastgele değil, log mesajına bakarak)\n"
            "- Düzeltme önerisi sun\n"
            "Kritik hata varsa create_recommendation ile kaydet."
        ),
    },

    # ── Pipeline ─────────────────────────────────────────────────────────
    {
        "command": "/pipeline",
        "label": "Pipeline Durumu",
        "description": "Aktif joblar ve son pipeline performansı",
        "icon": "play",
        "category": "pipeline",
        "prompt": (
            "Pipeline durumunu gerçek verilerle raporla:\n\n"
            "1. Aktif / bekleyen joblar:\n"
            "   query_database: SELECT id, status, channel_id, current_step, "
            "   progress_pct, created_at FROM jobs "
            "   WHERE status NOT IN ('completed','failed') ORDER BY created_at DESC\n\n"
            "2. Son 7 günün tamamlanan jobları:\n"
            "   query_database: SELECT channel_id, status, "
            "   ROUND(EXTRACT(EPOCH FROM (completed_at-started_at))/60::NUMERIC,1) as dur_min, "
            "   clip_count, created_at FROM jobs "
            "   WHERE status = 'completed' AND created_at > now() - interval '7 days' "
            "   ORDER BY created_at DESC LIMIT 15\n\n"
            "3. Adım bazında süre (sadece yeni pipeline):\n"
            "   query_database: SELECT step_name, "
            "   ROUND(AVG(duration_ms)/1000::NUMERIC,1) as avg_s, COUNT(*) as runs "
            "   FROM pipeline_audit_log "
            "   WHERE step_name IN ('s01_audio_extract','s02_transcribe','s03_speaker_id',"
            "'s04_labeled_transcript','s05_unified_discovery','s06_batch_evaluation',"
            "'s07_precision_cut','s08_export') "
            "   AND created_at > now() - interval '7 days' "
            "   GROUP BY step_name ORDER BY step_name\n\n"
            "Darboğaz var mı? Hangi adım en uzun sürüyor? Bunu yorumla."
        ),
    },
    {
        "command": "/klip-kalitesi",
        "label": "Klip Kalitesi",
        "description": "Clip confidence, quality_status, içerik tipi dağılımı",
        "icon": "star",
        "category": "pipeline",
        "prompt": (
            "Klip kalitesini derinlemesine analiz et:\n\n"
            "1. Genel kalite dağılımı:\n"
            "   query_database: SELECT quality_status, COUNT(*) as cnt, "
            "   ROUND(AVG(confidence*10)::NUMERIC,2) as avg_conf, "
            "   ROUND(AVG(standalone_score)::NUMERIC,2) as standalone, "
            "   ROUND(AVG(hook_score)::NUMERIC,2) as hook "
            "   FROM clips WHERE created_at > now() - interval '30 days' "
            "   GROUP BY quality_status ORDER BY cnt DESC\n\n"
            "2. İçerik tipi bazında performans:\n"
            "   query_database: SELECT content_type, COUNT(*) as cnt, "
            "   ROUND(AVG(confidence*10)::NUMERIC,2) as avg_conf, "
            "   COUNT(*) FILTER (WHERE quality_status='passed') as passed "
            "   FROM clips WHERE created_at > now() - interval '30 days' "
            "   GROUP BY content_type ORDER BY cnt DESC\n\n"
            "3. Süre dağılımı (ideal range 30-180s):\n"
            "   query_database: SELECT "
            "   COUNT(*) FILTER (WHERE duration_s < 30) as too_short, "
            "   COUNT(*) FILTER (WHERE duration_s BETWEEN 30 AND 60) as short, "
            "   COUNT(*) FILTER (WHERE duration_s BETWEEN 60 AND 120) as medium, "
            "   COUNT(*) FILTER (WHERE duration_s BETWEEN 120 AND 180) as long_clip, "
            "   COUNT(*) FILTER (WHERE duration_s > 180) as too_long "
            "   FROM clips WHERE created_at > now() - interval '30 days'\n\n"
            "4. En düşük ve en yüksek scoring klipler:\n"
            "   query_database: SELECT id, content_type, confidence, "
            "   standalone_score, hook_score, quality_status "
            "   FROM clips WHERE created_at > now() - interval '30 days' "
            "   ORDER BY confidence ASC LIMIT 5\n\n"
            "Kalite sorununu yorumla: hangi content_type zayıf, neden? "
            "S06 batch evaluation prompt'u bunu iyileştirebilir mi?"
        ),
    },
    {
        "command": "/test-pipeline",
        "label": "Test Pipeline Başlat",
        "description": "Onay alarak test pipeline başlat",
        "icon": "flask",
        "category": "pipeline",
        "prompt": (
            "Test pipeline başlatmadan önce kontrol yap:\n\n"
            "1. query_database: SELECT COUNT(*) as aktif FROM jobs "
            "   WHERE status NOT IN ('completed','failed')\n\n"
            "Aktif job varsa kullanıcıyı bilgilendir. Yoksa:\n"
            "Test başlatmak için onay iste — maliyet yaklaşık $0.05-0.15. "
            "Onay gelirse create_test_pipeline çağır, sonra "
            "get_test_pipeline_status ile takip et."
        ),
    },

    # ── DNA & Kanal ───────────────────────────────────────────────────────
    {
        "command": "/dna",
        "label": "Channel DNA",
        "description": "Kanal DNA'sını gerçek klip performansıyla karşılaştır",
        "icon": "dna",
        "category": "kanal",
        "prompt": (
            "Kanal DNA analizi yap — DNA'yı gerçek performans verileriyle karşılaştır:\n\n"
            "1. Kanalları listele:\n"
            "   query_database: SELECT id, display_name FROM channels\n\n"
            "2. Her kanal için DNA'yı çek: get_channel_dna\n\n"
            "3. DNA'da tanımlanan içerik tipleri ile gerçek üretilen içerik tiplerini karşılaştır:\n"
            "   query_database: SELECT channel_id, content_type, COUNT(*) as cnt, "
            "   ROUND(AVG(confidence*10)::NUMERIC,2) as avg_conf "
            "   FROM clips WHERE created_at > now() - interval '30 days' "
            "   GROUP BY channel_id, content_type ORDER BY channel_id, cnt DESC\n\n"
            "4. audit_channel_dna ile 6-nokta sağlık kontrolü yap\n\n"
            "DNA'da yazılan hedefler ile gerçekte üretilen içerik arasındaki uçurumu belirt. "
            "DNA güncel değilse update_channel_dna öner (değişiklik yapmadan sadece öner)."
        ),
    },
    {
        "command": "/kanal-karsilastir",
        "label": "Kanal Karşılaştırma",
        "description": "Kanalları gerçek metriklerle yan yana karşılaştır",
        "icon": "columns",
        "category": "kanal",
        "prompt": (
            "Tüm kanalları gerçek verilerle karşılaştır:\n\n"
            "1. Kanal bazında job ve clip performansı:\n"
            "   query_database: SELECT j.channel_id, "
            "   COUNT(DISTINCT j.id) as jobs, COUNT(c.id) as clips, "
            "   ROUND(COUNT(c.id)::NUMERIC/NULLIF(COUNT(DISTINCT j.id),0),1) as clips_per_job, "
            "   ROUND(AVG(c.confidence*10)::NUMERIC,2) as avg_conf "
            "   FROM jobs j LEFT JOIN clips c ON c.job_id = j.id "
            "   WHERE j.created_at > now() - interval '30 days' "
            "   GROUP BY j.channel_id ORDER BY clips DESC\n\n"
            "2. İçerik tipi dağılımı kanal bazında:\n"
            "   query_database: SELECT channel_id, content_type, COUNT(*) as cnt "
            "   FROM clips WHERE created_at > now() - interval '30 days' "
            "   GROUP BY channel_id, content_type ORDER BY channel_id, cnt DESC\n\n"
            "Kanallar arasındaki farkları yorumla. "
            "Hangi kanal neden daha iyi/kötü performans gösteriyor?"
        ),
    },

    # ── Öneri & Araştırma ────────────────────────────────────────────────
    {
        "command": "/oneriler",
        "label": "Aktif Öneriler",
        "description": "Aktif önerileri listele, hangilerinin çözüldüğünü kontrol et",
        "icon": "check-circle",
        "category": "oneri",
        "prompt": (
            "Aktif önerileri incele ve hangileri artık geçerli değil kontrol et:\n\n"
            "1. Mevcut aktif önerileri listele:\n"
            "   query_database: SELECT id, title, module_name, category, priority, created_at "
            "   FROM director_recommendations WHERE status = 'pending' ORDER BY priority ASC\n\n"
            "2. Öneri sayısını ve dağılımını gör:\n"
            "   query_database: SELECT category, COUNT(*) as cnt, "
            "   MIN(priority) as min_priority FROM director_recommendations "
            "   WHERE status = 'pending' GROUP BY category ORDER BY min_priority ASC\n\n"
            "3. Her kritik/yüksek öncelikli öneri (priority <= 2) için kontrol et:\n"
            "   - query_database ile ilgili metriklere bak (jobs, clips, errors)\n"
            "   - Sorun hâlâ geçerli mi? Yoksa düzeldi mi?\n\n"
            "4. Son 7 günlük job ve hata durumu:\n"
            "   get_pipeline_stats(days=7)\n\n"
            "Sonuçları şu formatta ver:\n"
            "- **Hâlâ Geçerli**: Sorun devam eden öneriler (neden devam ettiğini say)\n"
            "- **Çözüldü / Eskidi**: Artık geçerli olmayan öneriler (Tamamlandı işaretlenebilir)\n"
            "- **Öncelik Değişimi**: Şu an kritikleşen veya azalan öneriler\n\n"
            "Her 'çözüldü' önerisi için neyi kontrol ettiğini belirt."
        ),
    },
    {
        "command": "/oneri",
        "label": "Öneri Oluştur",
        "description": "Gerçek verilere dayalı akıllı geliştirme önerileri",
        "icon": "lightbulb",
        "category": "oneri",
        "prompt": (
            "Sistemi gerçekten araştırıp kanıta dayalı öneriler oluştur:\n\n"
            "1. Son 30 günün job ve clip özeti:\n"
            "   query_database: SELECT status, COUNT(*) FROM jobs "
            "   WHERE created_at > now() - interval '30 days' GROUP BY status\n\n"
            "2. En düşük confidence'lı content type'lar:\n"
            "   query_database: SELECT content_type, "
            "   ROUND(AVG(confidence*10)::NUMERIC,2) as avg_conf, COUNT(*) as cnt "
            "   FROM clips WHERE created_at > now() - interval '30 days' "
            "   GROUP BY content_type ORDER BY avg_conf ASC LIMIT 5\n\n"
            "3. S05 ve S06 adımlarının süre trendi:\n"
            "   query_database: SELECT step_name, "
            "   ROUND(AVG(duration_ms)/1000::NUMERIC,1) as avg_s "
            "   FROM pipeline_audit_log "
            "   WHERE step_name IN ('s05_unified_discovery','s06_batch_evaluation') "
            "   AND created_at > now() - interval '30 days' GROUP BY step_name\n\n"
            "4. En yüksek maliyetli adım:\n"
            "   query_database: SELECT step_name, "
            "   ROUND(SUM((token_usage->>'cost_usd')::FLOAT)::NUMERIC,4) as total_cost "
            "   FROM pipeline_audit_log "
            "   WHERE token_usage IS NOT NULL AND token_usage::text != '{}' "
            "   AND created_at > now() - interval '30 days' "
            "   GROUP BY step_name ORDER BY total_cost DESC LIMIT 5\n\n"
            "5. web_search ile 'YouTube shorts clip extraction AI quality improvement 2025' ara\n\n"
            "Topladığın kanıtlara dayanarak EN AZ 3 somut öneri oluştur. "
            "Her biri için create_recommendation çağır. "
            "Genel tavsiyeler verme — sadece bu sistemin bu verisine özel ol."
        ),
    },
    {
        "command": "/arastir",
        "label": "İnternet Araştırması",
        "description": "Belirtilen konuyu araştır, Prognot'a uygula",
        "icon": "search",
        "category": "oneri",
        "prompt": (
            "Araştırma yapacağım. Önce sistemi tanımak için:\n"
            "query_database: SELECT id, display_name FROM channels\n\n"
            "Sonra hangi konuyu araştırmamı istiyorsun? "
            "web_search ve fetch_url ile derinlemesine araştırıp "
            "Prognot sistemine nasıl uygulanabileceğini açıklayacağım."
        ),
    },

    # ── Hafıza & Self ─────────────────────────────────────────────────────
    {
        "command": "/hafiza",
        "label": "Hafıza Yönetimi",
        "description": "Kayıtlı hafızaları göster",
        "icon": "brain",
        "category": "hafiza",
        "prompt": (
            "Hafıza kayıtlarımı göster:\n"
            "1. list_memories ile tüm kayıtları listele\n"
            "2. query_database: SELECT COUNT(*) as total, type "
            "   FROM director_memory GROUP BY type ORDER BY total DESC\n\n"
            "Tip bazında grupla. Eksik hafıza alanları varsa belirt "
            "(örn: kanal kararları, sistem öğrenmeleri kayıt altında mı?)"
        ),
    },
    {
        "command": "/kendini-analiz-et",
        "label": "Director Öz-Analizi",
        "description": "Director kendi yeteneklerini ve eksiklerini değerlendirir",
        "icon": "eye",
        "category": "hafiza",
        "prompt": (
            "Kendi yeteneklerini ve sınırlarını dürüstçe değerlendir:\n\n"
            "1. get_director_self_analysis ile araç envanteri ve API durumunu çek\n\n"
            "2. director_analyses tablosunu kontrol et:\n"
            "   query_database: SELECT COUNT(*) as analysis_count, "
            "   MAX(timestamp) as last_analysis FROM director_analyses\n\n"
            "3. Öneri geçmişine bak:\n"
            "   query_database: SELECT status, COUNT(*) as cnt "
            "   FROM director_recommendations GROUP BY status\n\n"
            "4. Hafıza kullanımı:\n"
            "   query_database: SELECT type, COUNT(*) FROM director_memory GROUP BY type\n\n"
            "Şu an hangi görevleri GERÇEKTEN yapabiliyorsun? "
            "Hangi entegrasyonlar kopuk? "
            "Sistemin potansiyelinin ne kadarını kullanabiliyorsun ve neden?"
        ),
    },

    # ── Tahmin & Risk ─────────────────────────────────────────────────────
    {
        "command": "/tahmin",
        "label": "Tahmin & Projeksiyon",
        "description": "Maliyet ve kapasite projeksiyonları",
        "icon": "trending",
        "category": "tahmin",
        "prompt": (
            "Gerçek verilere dayalı projeksiyon yap:\n\n"
            "1. Son 30 günün iş hacmi:\n"
            "   query_database: SELECT "
            "   DATE_TRUNC('week', created_at) as week, "
            "   COUNT(*) as jobs, SUM(clip_count) as clips "
            "   FROM jobs WHERE created_at > now() - interval '30 days' "
            "   GROUP BY week ORDER BY week\n\n"
            "2. forecast_monthly_cost ile maliyet tahmini\n"
            "3. forecast_pipeline_volume ile hacim tahmini\n"
            "4. forecast_capacity ile kapasite durumu\n\n"
            "Haftalık trende bakarak gerçekçi bir ay sonu tahmini yap. "
            "Büyüme hızı hesapla."
        ),
    },
    {
        "command": "/risk",
        "label": "Risk Değerlendirmesi",
        "description": "Gerçek hata loglarına dayalı sistem riski",
        "icon": "shield",
        "category": "tahmin",
        "prompt": (
            "Sistem risklerini gerçek kanıtlarla değerlendir:\n\n"
            "1. Son 7 günün hata oranı adım bazında:\n"
            "   query_database: SELECT step_name, "
            "   COUNT(*) as total, "
            "   COUNT(*) FILTER (WHERE success = false) as errors, "
            "   ROUND(COUNT(*) FILTER (WHERE success = false)::NUMERIC / "
            "   NULLIF(COUNT(*),0) * 100, 1) as error_rate_pct "
            "   FROM pipeline_audit_log "
            "   WHERE created_at > now() - interval '7 days' "
            "   GROUP BY step_name ORDER BY error_rate_pct DESC\n\n"
            "2. get_dependency_map ile servis bağımlılıklarını çek\n\n"
            "3. Kritik servisler için etki analizi:\n"
            "   check_dependency_impact('gemini_pro')\n"
            "   check_dependency_impact('deepgram')\n"
            "   check_dependency_impact('supabase')\n\n"
            "4. Retry sayısı yüksek joblar:\n"
            "   query_database: SELECT id, retry_count, status, error_message "
            "   FROM jobs WHERE retry_count > 0 "
            "   ORDER BY retry_count DESC LIMIT 10\n\n"
            "Tek nokta arızaları (SPOF) ve en kritik risk faktörlerini listele."
        ),
    },

    # ── AI & Prompt ───────────────────────────────────────────────────────
    {
        "command": "/prompt-analiz",
        "label": "Prompt Performansı",
        "description": "S05/S06 prompt kalitesini gerçek çıktılarla değerlendir",
        "icon": "code",
        "category": "ai",
        "prompt": (
            "Prompt performansını gerçek data ile analiz et:\n\n"
            "1. S05 ve S06 Langfuse verisini çek: get_langfuse_data (step='s05', days=30)\n\n"
            "2. S05 token kullanımı ve süre:\n"
            "   query_database: SELECT "
            "   ROUND(AVG(duration_ms)/1000::NUMERIC,1) as avg_s, "
            "   ROUND(AVG((token_usage->>'input_tokens')::INT)::NUMERIC,0) as avg_input_tok, "
            "   ROUND(AVG((token_usage->>'output_tokens')::INT)::NUMERIC,0) as avg_output_tok "
            "   FROM pipeline_audit_log "
            "   WHERE step_name = 's05_unified_discovery' "
            "   AND created_at > now() - interval '30 days'\n\n"
            "3. Job başına keşfedilen aday sayısı:\n"
            "   query_database: SELECT j.id, j.total_candidates_found, "
            "   j.total_candidates_evaluated, j.clip_count "
            "   FROM jobs j WHERE j.status = 'completed' "
            "   AND j.created_at > now() - interval '30 days' "
            "   ORDER BY j.created_at DESC LIMIT 10\n\n"
            "4. S05 ve S06 prompt dosyalarını oku:\n"
            "   read_file: backend/app/pipeline/prompts/s05_discovery_prompt.py\n"
            "   (veya benzer isimli prompt dosyasını bul: "
            "   list_files: backend/app/pipeline/prompts/)\n\n"
            "Adaylara bakarak: kaç aday keşfediliyor, kaçı değerlendirmeye giriyor, "
            "kaçı son klip oluyor? Bu huni dar mı?"
        ),
    },

    # ── Kod ──────────────────────────────────────────────────────────────
    {
        "command": "/kod-tara",
        "label": "Kod Taraması",
        "description": "Pipeline kodunu tara, zayıf noktaları bul",
        "icon": "file",
        "category": "kod",
        "prompt": (
            "Kod tabanını tara — sadece okuma, öneri ver:\n\n"
            "1. search_codebase ile tüm bare except'leri bul: query='except Exception'\n"
            "2. search_codebase ile TODO/FIXME'leri bul: query='TODO|FIXME'\n"
            "3. search_codebase ile hardcoded değerleri bul: query='speedy_cast'\n"
            "4. read_file: backend/app/pipeline/steps/s05_unified_discovery.py\n"
            "5. read_file: backend/app/pipeline/orchestrator.py\n\n"
            "Her bulguyu kategorize et: güvenlik, performans, bakım, bug riski. "
            "En kritik 3 sorunu öne çıkar ve create_recommendation ile kaydet."
        ),
    },
    {
        "command": "/dosya-oku",
        "label": "Dosya Oku",
        "description": "Belirtilen dosyayı oku ve yorumla",
        "icon": "file",
        "category": "kod",
        "prompt": (
            "Hangi dosyayı okumamı istiyorsun? "
            "Tam yolu söyle (örn: backend/app/pipeline/steps/s06_batch_evaluation.py). "
            "read_file ile okuyup içeriği analiz edeceğim."
        ),
    },
]


def get_commands() -> list[dict]:
    return SLASH_COMMANDS


def find_command(text: str) -> dict | None:
    text = text.strip().lower()
    for cmd in SLASH_COMMANDS:
        if cmd["command"] == text:
            return cmd
    return None


def get_command_categories() -> list[dict]:
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
        "oneri": "Öneri & Araştırma",
        "hafiza": "Hafıza & Self",
        "tahmin": "Tahmin & Risk",
        "ai": "AI & Prompt",
        "kod": "Kod",
    }
    return [{"category": k, "label": cat_labels.get(k, k), "commands": v} for k, v in cats.items()]
