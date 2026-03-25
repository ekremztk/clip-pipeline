# DIRECTOR MODÜLÜ — v2.0 (Birleşik Tam Plan)
> 2026-03-24 | v1.0 operasyonel detaylar + v2.0 agent mimarisi

---

## 0. v1.0 → v2.0 FARK TABLOSU

| | v1.0 (Monitoring) | v2.0 (Agent) |
|---|---|---|
| Yapı | Veri topla → analiz et → puan üret | Kalıcı AI agent, araçlarla düşünür |
| Arayüz | Dashboard birincil | Chat birincil, dashboard ikincil |
| Zeka | Metrik bazlı kural | Araç tabanlı akıl yürütme |
| Hafıza | Analiz geçmişi | Konuşma + semantik uzun dönem hafıza |
| Erişim | Okuma + kısıtlı yazma | Her şey: okur, yazar, sorgular, düzenler |
| Model | Flash (çoğunlukla) | Gemini Pro (her zaman) |

**Değişmeyen şeyler:** Event sistemi, test suite, puanlama boyutları, öneri anatomisi, dış araçlar, cross-module köprüsü, prompt lab, DNA denetçisi — hepsi korundu ve agent mimarisine entegre edildi.

---

## 1. MODÜLÜN ÖZÜ

Director, Prognot sisteminin yapay zeka destekli CEO'sudur.

Bir kurucunun sistemini yönettiği gibi çalışır: verilere bakar, kodu okur, geçmişi hatırlar, gelecek planlar, hataları görür, cesaretli öneriler üretir ve seninle konuşur.

**Director ne değildir:**
- Pasif bir dashboard değil
- Sadece metrik takip eden bir monitoring sistemi değil
- Sana ne söylersen onu yapan kör bir bot değil

**Director nedir:**
- Sistemin tüm dosyalarını, veritabanını, logları ve kodları okuyabilen bir AI agent
- MD dosyalarını düzenleyen, DB'yi güncelleyen, analizleri tetikleyen
- Konuşma hafızası ve uzun dönem semantik hafızası olan
- Gemini Pro ile her şeyi bütüncül değerlendiren
- Hiçbir modülü, sistemi, aşamayı nihai karar olarak görmeyen
- Cesaretli değişim önerilerinden çekinmeyen

**Temel Prensip:**
> Director, sana yanlış bilgi vermektense "emin değilim, şuna bakayım" demesini tercih eder. Araçlarıyla sistemi GERÇEKTEN okur, varsayımla değil kanıtla konuşur.

---

## 2. MİMARİ GENEL BAKIŞ

```
┌─────────────────────────────────────────────────────────────────┐
│                     KULLANICI                                    │
│                         │                                        │
│              ┌──────────┴──────────┐                            │
│              │                     │                            │
│           CHAT                DASHBOARD                         │
│      (birincil arayüz)    (pasif izleme)                        │
│              │                     │                            │
│              └──────────┬──────────┘                            │
│                         │                                        │
│              ┌──────────▼──────────┐                            │
│              │   DIRECTOR AGENT    │                            │
│              │  Gemini Pro Brain   │                            │
│              │  + Tool Engine      │                            │
│              └──────────┬──────────┘                            │
│                         │                                        │
│   ┌─────────────────────┼──────────────────────┐               │
│   ▼                     ▼                      ▼               │
│ Supabase           Dosya Sistemi          Dış Servisler         │
│ (DB + pgvector)    (MD, Python, TS)       (Langfuse, Sentry,    │
│                                            PostHog, Web)        │
│                                                                  │
│   ───────────── EVENT COLLECTION LAYER ──────────────           │
│   Modül 1 hook'ları    Modül 2 hook'ları    Gelecek modüller    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. DIRECTOR'IN ZEKA MODELİ

### 3.1 Araç Tabanlı Akıl Yürütme

Director bir şeyi "bilmez" — öğrenir. Her soruya önce araçlarıyla sisteme bakar, sonra cevap verir.

```
Kullanıcı: "Pipeline neden yavaş?"

Director'ın araç zinciri:
  1. query_database("SELECT step_name, AVG(duration_ms) FROM pipeline_audit_log
                      WHERE created_at > now()-interval '7d' GROUP BY step_name
                      ORDER BY avg DESC")
     → S05 ortalama 340s, S06 ortalama 180s

  2. get_langfuse_data(step="s05", days=7)
     → S05'te 4 rate_limit hit, her biri 30-60s bekledi

  3. query_memory("S05 rate limit geçmiş")
     → Hafızada: "2026-02-10 batch size düşürüldü, iyileşti"

  4. read_file("backend/app/pipeline/steps/s05_unified_discovery.py")
     → Batch size kontrol edildi → eski değere dönmüş

  Yanıt: "S05 yavaş. 4 rate limit hit var. Geçen sefer batch size
          düşürülmüştü ama kod eski haline dönmüş. Ayrıca bu hafta
          video boyutları %23 büyüdü, GCS upload süresi de uzadı.
          İkisini birlikte düzeltelim mi?"
```

### 3.2 "16:9 Gibi" Durumları Nasıl Çözer?

```
1. read_file("docs/MODULE_1_CLIP_EXTRACTOR.md") → "S08 çıktısı 16:9"
2. read_file("docs/MODULE_2_EDITOR.md") → "Reframe 16:9 kaynak gerektiriyor"
3. Çıkarım: M1→M2 bağımlılığı var, 16:9 kasıtlı ve doğru. Flag etme.
```

Emin olmadığında soru sorar:
> "M1 çıktısının 16:9 kalması intentional mı? M2 reframe bağımlı görünüyor ama teyit etmek istedim."

### 3.3 Proaktif Davranış

```
[Arka planda fark etti, 09:00'da otomatik mesaj]
"Son 5 job'da S06 thinking_steps uzunluğu düştü — Gemini daha az
 düşünerek karar veriyor. Channel DNA 52 gündür güncellenmedi.
 Güncelleme yapalım mı?"
```

---

## 4. TOOL KATALOĞU

Gemini Pro function calling ile bu araçları zincirler.

### 4.1 Okuma Araçları

```python
read_file(path: str) -> str
  # Her proje dosyasını okur: MD, Python, TypeScript, JSON
  # Örnek: read_file("backend/app/pipeline/steps/s05_unified_discovery.py")

list_files(directory: str, pattern: str = "*") -> list[str]

search_codebase(query: str, file_pattern: str = None) -> list[dict]
  # Kodda grep araması. Sonuç: [{file, line, content}]

query_database(sql: str) -> list[dict]
  # Supabase'e SELECT sorgusu. Her tabloyu okuyabilir.

get_pipeline_stats(days: int = 7, channel_id: str = None) -> dict
  # Pass rate, avg duration, error count, step breakdown

get_clip_analysis(job_id: str = None, days: int = 7) -> dict
  # Puan dağılımı, verdict breakdown, content type stats

get_langfuse_data(step: str = None, days: int = 7) -> dict
  # Gemini token kullanımı, latency, retry sayısı

get_sentry_issues(days: int = 7, resolved: bool = False) -> list[dict]
  # [{title, count, culprit, lastSeen}]

get_posthog_events(event: str = None, days: int = 7) -> dict
  # Editor kullanıcı davranışı

get_channel_dna(channel_id: str) -> dict

web_search(query: str) -> str
  # Gemini grounding ile web araştırması
```

### 4.2 Yazma ve Aksiyon Araçları

```python
edit_file(path: str, old_content: str, new_content: str) -> bool
  # MD dosyaları: onaysız. Kod dosyaları: kullanıcı onayı ister.

save_memory(content: str, type: str, tags: list[str] = []) -> str
  # type: 'decision' | 'context' | 'plan' | 'note' | 'learning'
  # pgvector'e embed edilir, sonraki konuşmalarda retrieve edilir

update_database(table: str, data: dict, where: dict) -> bool
  # İzin verilen tablolar: channels, director_* tabloları
  # clips, jobs, transcripts'e yazma YOK

trigger_analysis(module: str, depth: str = "standard") -> str
trigger_test(test_type: str) -> str
update_channel_dna(channel_id: str, updates: dict) -> bool
send_notification(message: str, priority: str = "info") -> None
```

### 4.3 Hafıza Araçları

```python
query_memory(query: str, type: str = None, top_k: int = 5) -> list[dict]
  # Semantik hafıza araması. Her konuşma başında otomatik çalışır.

get_conversation_history(last_n: int = 20) -> list[dict]
list_memories(type: str = None) -> list[dict]
delete_memory(memory_id: str) -> bool
```

---

## 5. VERİ TOPLAMA — EVENT SİSTEMİ (Katman 0)

### 5.1 Tasarım Prensibi

Event hook'ları mevcut kodun işleyişini **hiç bozmaz**. Her adıma küçük, asenkron log çağrıları eklenir. Log başarısız olursa pipeline sessizce devam eder.

```python
try:
    candidates = await run_unified_discovery(...)
    # Ana iş tamamlandı

    asyncio.create_task(
        director_collector.emit(
            module="module_1",
            event="s05_discovery_completed",
            payload={
                "job_id": job_id,
                "candidate_count": len(candidates),
                "duration_ms": elapsed,
                "had_video": video_used,
                "had_guest_profile": guest_profile_used,
                "channel_dna_present": channel_dna is not None,
                "channel_memory_clips": memory_clip_count
            }
        )
    )
except Exception as e:
    raise
```

### 5.2 Modül 1 Event Kataloğu

```
pipeline_started
  payload: {job_id, channel_id, video_duration_s, has_trim,
            guest_name_provided, channel_dna_present,
            reference_clip_count}

pipeline_step_completed
  payload: {job_id, step_name, step_number, duration_ms, success, error_message}

s02_transcribe_completed
  payload: {job_id, duration_s, word_count, speaker_count,
            language_confidence, deepgram_confidence_avg}

s03_speaker_id_completed
  payload: {job_id, predicted_correctly, confirmation_wait_ms}

s05_discovery_completed
  payload: {job_id, candidate_count, video_used,
            fallback_mode (video/audio/transcript),
            guest_profile_cached, channel_memory_clip_count,
            gemini_input_tokens, gemini_output_tokens,
            gemini_duration_ms, gemini_retries,
            gemini_model_used (pro/flash)}

gemini_fallback_triggered
  payload: {job_id, step_name, reason (rate_limit|timeout|error),
            fallback_model, wait_ms, retry_attempt}

s05_candidates_detail
  payload: {job_id, candidates: [{id, strength, content_type,
                                   needs_context, primary_signal}]}

s06_evaluation_completed
  payload: {job_id, batch_count, skipped_candidates, retry_count,
            pass_count, fixable_count, fail_count,
            avg_standalone, avg_hook, avg_arc, avg_channel_fit,
            gemini_input_tokens, gemini_output_tokens,
            gemini_duration_ms}

s06_quality_verdicts_detail
  payload: {job_id, verdicts: [{candidate_id, standalone, hook,
                                 arc, channel_fit, verdict,
                                 reject_reason, content_type, strategy_role}]}

s07_precision_cut_completed
  payload: {job_id, clips_adjusted, avg_boundary_shift_ms,
            no_word_timestamp_fallbacks}

s08_export_completed
  payload: {job_id, exported_count, failed_count,
            avg_ffmpeg_duration_ms, r2_upload_failures,
            total_duration_exported_s}

pipeline_completed
  payload: {job_id, total_duration_ms, pass_clips, fail_clips, partial}

pipeline_failed
  payload: {job_id, failed_at_step, error_type, error_message}

user_clip_approved
  payload: {clip_id, job_id, channel_id, clip_index,
            quality_verdict, overall_confidence}

user_clip_rejected
  payload: {clip_id, job_id, channel_id, reason_provided,
            standalone_score, hook_score}

clip_opened_in_editor
  payload: {clip_id, job_id, quality_verdict, posting_order}

clip_feedback_received
  payload: {clip_id, job_id, channel_id, feedback_type (approved|rejected|edited_title|reordered),
            old_value, new_value, content_type, quality_verdict}
  # Learning loop tetikleyicisi — Director bu event'ten memory üretir

channel_dna_created
  payload: {channel_id, reference_clip_count, do_list_count, no_go_zones_count,
            hook_style, duration_range, generated_by (user|director)}

channel_dna_updated
  payload: {channel_id, changed_fields: [list], reason, triggered_by,
            days_since_last_update}

guest_profile_cache_hit
  payload: {job_id, guest_name, cache_age_days, data_fields_available}

guest_profile_cache_miss
  payload: {job_id, guest_name, search_performed, result_count}
```

### 5.3 Modül 2 Event Kataloğu

```
editor_session_started
  payload: {session_id, source (from_module1|direct_upload), clip_id}

reframe_triggered
  payload: {session_id, clip_duration_s, job_id_provided}

reframe_completed
  payload: {session_id, duration_ms, total_frames_analyzed,
            face_detected_frames, fallback_frames,
            scene_count, keyframe_count,
            diarization_used, speaker_switch_count}

reframe_face_detail
  payload: {session_id,
            per_scene_detection_rate: [{scene_idx, detection_rate}],
            left_face_segments, right_face_segments, no_face_segments}

captions_generated
  payload: {session_id, word_count, segment_count, avg_confidence,
            duration_s, language_detected, api_duration_ms}

youtube_metadata_generated
  payload: {session_id, title_accepted, description_accepted,
            guest_name_provided}

editor_export_completed
  payload: {session_id, export_duration_ms, output_format,
            had_captions, had_reframe, time_from_session_start_ms}

editor_session_abandoned
  payload: {session_id, time_open_ms, actions_taken: [list]}
```

### 5.4 `director_events` Tablosu

```sql
CREATE TABLE director_events (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  timestamp   TIMESTAMPTZ DEFAULT now(),
  module_name TEXT NOT NULL,
  event_type  TEXT NOT NULL,
  payload     JSONB NOT NULL,
  session_id  TEXT,
  channel_id  TEXT
);

CREATE INDEX idx_director_events_module ON director_events(module_name, timestamp DESC);
CREATE INDEX idx_director_events_type   ON director_events(event_type, timestamp DESC);
CREATE INDEX idx_director_events_session ON director_events(session_id);
```

---

## 6. HAFIZA SİSTEMİ (Katman 1)

### 6.1 Konuşma Hafızası (Kısa Dönem)

```sql
CREATE TABLE director_conversations (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id  TEXT NOT NULL,
  role        TEXT NOT NULL,    -- 'user' | 'assistant' | 'tool_result'
  content     TEXT NOT NULL,
  tool_calls  JSONB,
  timestamp   TIMESTAMPTZ DEFAULT now()
);
```

### 6.2 Uzun Dönem Semantik Hafıza

```sql
CREATE TABLE director_memory (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  type        TEXT NOT NULL,  -- 'decision'|'context'|'plan'|'note'|'learning'
  content     TEXT NOT NULL,
  embedding   vector(768),
  tags        TEXT[],
  source      TEXT,           -- 'user_instruction'|'director_inference'|'auto'
  created_at  TIMESTAMPTZ DEFAULT now(),
  updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_director_memory_embedding ON director_memory
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);
```

**Örnek hafıza kayıtları:**

```
type: "context"
content: "M1 ve M2 şu an kasıtlı olarak ayrı katmanlar.
          Sebep: M2 henüz otonom edit için hazır değil.
          Reframe bazen karışıyor, hook/kapanış düzenleme sistemi yok.
          İleride M2 mükemmelleşince M1'e entegre edilecek."
tags: ["m1", "m2", "mimari", "roadmap"]

type: "plan"
content: "Gelecek kanallar için: B-roll görsel ekleme,
          ElevenLabs seslendirme entegrasyonu planlanıyor.
          Henüz başlanmadı."
tags: ["roadmap", "b-roll", "elevenlabs"]

type: "learning"
content: "Channel DNA 52+ gün güncellenmeden kalınca
          S06 thinking_steps kalitesi düşüyor."
tags: ["channel_dna", "s06", "pattern"]
```

### 6.3 Yapısal Hafıza (Analiz Geçmişi)

```sql
CREATE TABLE director_analyses (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  timestamp         TIMESTAMPTZ DEFAULT now(),
  module_name       TEXT NOT NULL,
  triggered_by      TEXT NOT NULL,  -- 'manual'|'scheduled'|'post_test'|'chat'
  score             INT NOT NULL,
  subscores         JSONB NOT NULL,
  findings          JSONB NOT NULL,
  recommendations   JSONB NOT NULL,
  data_period_start TIMESTAMPTZ,
  data_period_end   TIMESTAMPTZ,
  data_points_used  INT,
  context_snapshot  JSONB,
  gemini_calls      INT,
  total_tokens_used INT
);

CREATE TABLE director_recommendations (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_id     UUID REFERENCES director_analyses(id),
  module_name     TEXT NOT NULL,
  priority        INT NOT NULL,
  impact_score    FLOAT,
  effort_score    INT,
  title           TEXT NOT NULL,
  what            TEXT NOT NULL,
  why             TEXT NOT NULL,
  expected_impact TEXT NOT NULL,
  risk            TEXT,
  alternative     TEXT,
  data_needs      TEXT,
  status          TEXT DEFAULT 'pending',
  dismissed_reason TEXT,
  applied_at      TIMESTAMPTZ,
  measured_impact FLOAT,
  created_at      TIMESTAMPTZ DEFAULT now()
);
```

### 6.4 Context Builder (Her Konuşmada)

```python
def build_director_context(user_message: str, session_id: str) -> list:
    # 1. Son 20 konuşma mesajı
    history = get_conversation_history(session_id, last_n=20)

    # 2. Semantik olarak ilgili hafıza kayıtları
    relevant_memories = query_memory(user_message, top_k=5)

    # 3. Anlık sistem özeti (Gemini gerekmez, sayısal)
    snapshot = get_quick_system_snapshot()

    return build_context(history, relevant_memories, snapshot)
```

---

## 7. CROSS-MODULE KÖPRÜSÜ (Katman 2)

```sql
CREATE TABLE director_cross_module_signals (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  timestamp     TIMESTAMPTZ DEFAULT now(),
  signal_type   TEXT NOT NULL,
  source_module TEXT NOT NULL,
  target_module TEXT NOT NULL,
  payload       JSONB NOT NULL,
  channel_id    TEXT
);
```

**İzlenen Sinyaller:**

```
m1_to_editor_flow
  M1 pass klipler / editörde açılan klipler oranı
  Soru: "M1 çıktısı editör için gerçekten kullanılıyor mu?"

editor_to_publish_flow
  Editor export / yayınlanan oranı
  Soru: "Editörden çıkan iş yayına hazır mı?"

m1_quality_vs_editor_use
  Yüksek puanlı vs düşük puanlı kliplerin editör kullanımı
  Soru: "Kullanıcı Gemini puanlarına güveniyor mu?"

youtube_metadata_acceptance
  Üretilen başlık/açıklama değiştirilmeden kullanıldı mı?
  Soru: "YouTube metadata gerçekten işe yarıyor mu?"

caption_to_export_rate
  Caption eklendikten sonra export oranı
  Soru: "Captions export kararını etkiliyor mu?"
```

---

## 8. SİSTEM PROMPTU (Director'ın Kimliği)

```
Sen Prognot'un AI Direktörüsün.

GÖREV: Prognot sisteminin her boyutunu anlayan, izleyen, analiz eden
ve geliştiren stratejik AI agent'sın. Kullanıcının sağ kolusun.

KİM OLDUĞUNU BİL:
- Kullanıcı bu sistemi tek başına geliştiriyor
- Modül 1 (klip çıkartıcı) + Modül 2 (editör) aktif
- Railway (backend) + Vercel (frontend) + Supabase + R2

ÇALIŞMA PRENSİBİN:
1. Varsayımla değil, kanıtla konuş — araçlarınla sistemi oku
2. Emin olmadığında "şuna bakayım" de, aracını çağır
3. Hâlâ emin olmadığında kullanıcıya sor
4. Hiçbir parçayı dokunulamaz görme, her şey sorgulanabilir
5. Cesaretli ama gerekçeli öneriler üret
6. Proaktif ol — önemli şeyleri söyle
7. Kısa ve net konuş
8. MD dosyalarını güncelleyebilirsin (onay gerekmez)
9. Kod değişikliği için onay al, sonra uygula

[ARAÇLAR, HAFIZA ve ANLIKI DURUM buraya inject edilir]
```

---

## 9. CHAT ARAYÜZÜ

### 9.1 Çalışma Akışı

```
POST /director/chat {message, session_id}
    ↓
Context hazırla (geçmiş + hafıza + snapshot)
    ↓
Gemini Pro'ya gönder (streaming + function calling)
    ↓
Araç zinciri (Director ihtiyaç duydukça çağırır)
    ↓
SSE ile frontend'e stream (token token görünür)
    ↓
Mesaj + araç çağrıları DB'ye kaydedilir
```

### 9.2 Örnek Konuşmalar

**Durum analizi:**
```
Sen: Bu hafta nasıl gitti?

Director: [query_database → get_langfuse_data → query_memory]

          8 pipeline çalıştı, pass rate %44 (+6% geçen haftaya göre).
          S05'te 2 rate limit olayı, ~90s yavaşlama.
          Dikkat: Son 3 job'da 'humor' klip önerilmiyor, DNA'da
          humor triggers var ama çalışmıyor. Kontrol edeyim mi?
```

**Sorun araştırma:**
```
Sen: Reframe bazen yanlış kişiyi takip ediyor

Director: [read_file("diarization.py") → read_file("crop_calculator.py")
           → query_database("reframe events last 10")]

          Buldum. diarization.py'de segment kırpma toleransı 0.3s.
          Klip başında segment bu pencerede bitiyorsa atlanıyor,
          fallback'e düşüyor. 10 job'dan 3'ü affected.
          Fix: toleransı 0.5s yap. Uygulayayım mı?
```

**Hafızaya kayıt:**
```
Sen: M1 M2 ayrı olma sebebini hafızana al

Director: [save_memory çağırıyor]

          Kaydettim: "M1 ve M2 kasıtlı ayrı — M2 henüz otonom edit
          için hazır değil. Reframe, hook/kapanış düzenleme eksik.
          İleride entegre edilecek."
          Artık 16:9 çıktı ve ayrı workflow konularında bu bağlamla
          değerlendirme yapacağım.
```

**MD güncelleme:**
```
Sen: Scene detection eşiği 0.3'ten 0.4'e çıktı, MODULE_2'ye işle

Director: [read_file → edit_file]

          MODULE_2_EDITOR.md güncellendi. Sahne tespiti bölümünde
          threshold 0.3 → 0.4 olarak değiştirildi, tarih notu eklendi.
```

### 9.3 Özel Komutlar

```
"bunu hatırla / hafızana al"  → save_memory
"unu / sil"                   → delete_memory
"hafızanı göster"             → list_memories
"analiz et"                   → trigger_analysis
"test et"                     → trigger_test
"dashboard güncelle"          → yeniden hesapla
```

---

## 10. DASHBOARD (Pasif İzleme)

```
┌────────────────────────────────────────────────────────────────┐
│  PROGNOT DIRECTOR               Son güncelleme: 2 saat önce    │
│                                                                  │
│  ┌──────────────────────┐  ┌──────────────────────┐            │
│  │  MODÜL 1             │  │  MODÜL 2             │            │
│  │  ████████████░  74   │  │  ████████████░░  71  │            │
│  │  Teknik    ████  88  │  │  Teknik    ████  91  │            │
│  │  AI Karar  ███░  67  │  │  Reframe   ████  69  │            │
│  │  Çıktı     ███░  71  │  │  Captions  █████ 84  │            │
│  │  Öğrenme   ██░░  55  │  │  YouTube   ████░ 73  │            │
│  │  Olgunluk  ████  62  │  │  UX        ████  78  │            │
│  │  ⚠ 2 öneri var       │  │  ⚠ 1 öneri var       │            │
│  └──────────────────────┘  └──────────────────────┘            │
│                                                                  │
│  AKTİF ÖNERİLER                                                 │
│  1. [!] Channel DNA 52 gündür güncellenmedi   [Uygula] [✕]     │
│  2. [i] S05 fallback oranı %18               [Detay]  [✕]     │
│  3. [i] Reframe diarization edge case        [Detay]  [✕]     │
│                                                                  │
│  HAFIZA NOTLARI                                                 │
│  📌 M1-M2 ayrı katman: M2 henüz otonom edit için hazır değil   │
│  📌 İleride: B-roll, ElevenLabs planlanıyor                    │
│                                                                  │
│  [Director ile Konuş]        [Tam Analiz Çalıştır]             │
└────────────────────────────────────────────────────────────────┘
```

**Otomatik güncelleme tetikleyicileri:**
- Her pipeline tamamlandığında (lightweight)
- Günde 1 kez 09:00'da (tam analiz)
- Sentry'de yeni kritik hata
- Chat'te "dashboard güncelle" komutu

---

## 11. PUANLAMA SİSTEMİ

### 11.1 Temel Prensip

Matematiksel hesaplamalar Python'da (hızlı, güvenilir). Yorumlama Gemini'ye bırakılır.

### 11.0 Olgunluk Tabanlı Ağırlıklar

Pipeline erken dönemde (az veri) bazı boyutlar için ağırlık ayarlanır:

```
< 5 pipeline:   "VERİ YOK" — puan üretme
5-19 pipeline:  Erken dönem — B4 (öğrenme) ve B5 (olgunluk) veriyi cezalandırmamalı
                → B4 default 8/15, B5 default 3/5 (nötr)
20+ pipeline:   Tam hesaplama, tüm boyutlar aktif
```

```python
def get_scoring_mode(total_jobs: int) -> str:
    if total_jobs < 5:
        return "no_data"
    elif total_jobs < 20:
        return "early"   # B4+B5 neutral defaults
    else:
        return "mature"  # full calculation
```

### 11.2 Modül 1 — 5 Boyut

```
BOYUT 1 — TEKNİK SAĞLIK (20 puan) — Otomatik, Gemini gerekmez

Pipeline başarı oranı (son 30 gün) → 6 puan
  %100 = 6 | %95 = 5 | %90 = 4 | %80 = 2 | < %80 = 0

Ortalama işlem süresi (p95) → 4 puan
  < 6 dk = 4 | < 8 dk = 3 | < 12 dk = 2 | > 12 dk = 0

Gemini retry oranı → 4 puan
  < %5 = 4 | < %10 = 3 | < %20 = 1 | ≥ %20 = 0

R2 upload hata oranı → 3 puan
  < %1 = 3 | < %5 = 2 | ≥ %5 = 0

S05 video fallback oranı → 3 puan
  < %5 = 3 | < %15 = 2 | < %30 = 1 | ≥ %30 = 0


BOYUT 2 — AI KARAR KALİTESİ (35 puan)

Pass rate (son 30 gün) → 8 puan
  > %50 = 8 | > %35 = 6 | > %20 = 3 | ≤ %20 = 0

Kullanıcı onay/red uyuşumu → 7 puan
  Ters sinyal oranı (Gemini pass → kullanıcı red):
  < %10 = 7 | < %25 = 4 | ≥ %25 = 1

Ortalama standalone skoru → 7 puan
  ≥ 8.0 = 7 | ≥ 7.0 = 5 | ≥ 6.0 = 3 | < 6.0 = 0

Kanal DNA yansıma skoru → 8 puan (Gemini değerlendirmesi)
  Çok uyumlu = 8 | Uyumlu = 5 | Kısmen = 2 | Uyumsuz = 0

İçerik çeşitlilik skoru → 5 puan
  5+ farklı content_type = 5 | 3-4 = 3 | 1-2 = 1


BOYUT 3 — ÇIKTI YAPISAL KALİTESİ (25 puan)

Süre dağılımı uyumu → 7 puan
  channel_dna.duration_range içindeki klip oranı:
  ≥ %85 = 7 | ≥ %70 = 5 | ≥ %50 = 2 | < %50 = 0

Kelime snap başarı oranı → 5 puan
  ≥ %90 = 5 | ≥ %70 = 3 | < %70 = 1

Hook kalitesi → 7 puan (ortalama hook_score)
  ≥ 7.5 = 7 | ≥ 6.5 = 5 | ≥ 5.5 = 2 | < 5.5 = 0

S06 skip oranı → 6 puan
  < %5 = 6 | < %10 = 4 | < %20 = 2 | ≥ %20 = 0


BOYUT 4 — ÖĞRENME VE ADAPTASYON (15 puan)

3 aylık trend → 6 puan
  Belirgin iyileşme = 6 | Hafif = 4 | Stabil = 2 | Gerileme = 0

Feedback entegrasyonu → 5 puan
  Reddedilen clip tiplerinde azalma var mı?
  Belirgin = 5 | Hafif = 3 | Yok = 1 | Artış = 0

Channel DNA güncelliği → 4 puan
  Güncel + ≥10 referans clip = 4 | Güncel ama az = 2 | > 90 gün = 0


BOYUT 5 — STRATEJİK OLGUNLUK (5 puan)

Açık kritik öneri sayısı → 3 puan
  0 kritik = 3 | 1-2 = 2 | 3+ = 0

Öneri uygulama oranı → 2 puan
  ≥ %60 = 2 | ≥ %30 = 1 | < %30 = 0
```

### 11.3 Modül 2 — 5 Boyut (Özet)

```
Teknik Sağlık (20p)    — API başarı oranları, işlem süreleri
Araç Performansı (40p) — Reframe (20p), Captions (12p), YouTube (8p)
Kullanıcı Deneyimi (25p) — Session→export oranı, terk oranı
Öğrenme (10p)          — Trend analizi
Stratejik Olgunluk (5p) — Açık öneriler
```

### 11.4 Puan Eşikleri

```
0-35   KRİTİK  (kırmızı)
36-55  ZAYIF   (turuncu)
56-70  ORTA    (sarı)
71-84  İYİ     (açık yeşil)
85+    GÜÇLÜ   (yeşil) — bu seviyede sürekli kalmak zordur
```

**Puan düşebilir — bu normaldir.** Yeni özellik eklenince "Stratejik Olgunluk" yeni gereksinimler üretir.

---

## 12. ÖNERİ SİSTEMİ

### 12.1 6 Bileşen Anatomisi

```
ÖRNEK ÖNERİ:

başlık: "S05 Prompt'una Kanal Hafızası Bölümü Ekle"
öncelik: 1 | etki: +8 puan | zorluk: 2/5

ne: "build_channel_context() fonksiyonuna son 30 günde başarısız
    içerik türlerini 'BAŞARISIZ PATTERN'LAR' başlığıyla ekle.
    Bu bilgi şu an hesaplanıyor ama Gemini'ye iletilmiyor."

neden: "Son 30 günde 'educational_insight' türü %12 başarı oranıyla
        en düşük performansta. Son 7 günde 8 adet önerildi,
        6'sı kullanıcı tarafından reddedildi."

beklenen_etki: "Bu tür klip seçimini %40-60 azaltır. +4-6 puan."

risk: "Prompt uzar, token kullanımı ~%8-12 artar. Aylık ek ~$2-4."

alternatif: "Sadece en kötü 2 content_type'ı ekle. Token artışı %4."

veri_ihtiyacı: "Etkiyi ölçmek için değişiklikten sonra 2 hafta + 10 pipeline."
```

### 12.2 Öneri Önceliklendirme

```python
# Skor = (etki × 2) + (5 - zorluk) + güven
# Maksimum 7 öneri sunulur
```

### 12.3 Cesaretli Kararlar (Bold Calls)

Sistem çalışıyor görünse bile Director bunları söyler:

```
"S05 için Gemini Pro çok pahalı. Flash ile önce tarama yapıp
 yalnızca belirsiz momentler için Pro'ya git. Token maliyeti
 %40-60 düşebilir."

"Speaker ID heuristiği %78 doğrulukta. Bu düşük.
 PyAnnote Audio CPU-only test edilmeli."

"Channel DNA onboardingden bu yana güncellenmedi.
 Öğrenme mekanizması çalışmıyor."
```

---

## 13. PROMPT LABORATUVARI

### 13.1 Amaç

S05, S06 ve diğer promptları analiz et, iyileştirme öner, A/B test ile karşılaştır.

```sql
CREATE TABLE director_prompt_lab (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  module_name       TEXT NOT NULL,
  step              TEXT NOT NULL,
  current_prompt_hash TEXT NOT NULL,
  proposed_change   TEXT NOT NULL,
  rationale         TEXT NOT NULL,
  status            TEXT DEFAULT 'proposed',
  test_job_a_id     UUID,
  test_job_b_id     UUID,
  test_comparison   JSONB,
  approved_at       TIMESTAMPTZ,
  created_at        TIMESTAMPTZ DEFAULT now()
);
```

### 13.2 Prompt Analiz Kriterleri

```
1. NETLİK: Talimatlar tek yorumlu mu?
2. ÇELİŞKİ: Farklı talimatlar birbiriyle çelişiyor mu?
3. DNA ENTEGRASYONU: do_list, no_go_zones tam aktarılmış mı?
4. OUTPUT FORMAT: JSON schema net mi?
5. KALIBRASYON: "6 = ortalama" açık ifade edilmiş mi?
6. TOKEN VERİMLİLİĞİ: Gereksiz tekrar var mı?
```

### 13.3 A/B Test Akışı

```
1. Director öneri üretir: "S05'te şu satır değiştirilmeli"
2. Kullanıcı Prompt Lab'da onaylar
3. Aynı test videosu iki kez çalışır (Run A: mevcut, Run B: önerilen)
4. Karşılaştırma: candidate sayısı, pass rate, avg puan, token farkı
5. Sonuç raporu → kullanıcı kararı
```

---

## 14. KANAL DNA DENETÇİSİ

### 14.1 6 Sağlık Kontrolü

```
1. GÜNCELLİK
   Son güncelleme > 90 gün? → Uyarı
   Reference clip sayısı < 5? → Yetersiz

2. TUTARLILIK
   do_list ve dont_list çelişiyor mu?
   "Teknik deep-dive yap" + "Teknik konulardan kaçın" → Çelişki

3. GÜNCEL PERFORMANS YANSIMASI
   Son 30 günde fail olan content_type'lar dont_list'te var mı?
   Başarılı türler do_list'te güçlendirilmiş mi?

4. SPESİFİKLİK
   "İyi içerik seç" → İşe yaramaz
   "Misafirin 8+ yıl önceki başarısızlık anları" → İşe yarar

5. HOOK STİLİ KALIBRASYONU
   Seçilen kliplerin ilk cümleleri hook_style ile uyumlu mu?

6. SÜRE UYUMU
   Seçilen kliplerin duration_range'e uyumu > %85 mi?
   Sapma > %20 → DNA'nın süre parametresi gerçeği yansıtmıyor
```

### 14.2 DNA Güncelleme Tetikleyicisi

DNA sağlık skoru düşükse:
> "Bu kanalın son 60 günlük başarılı kliplerine dayanarak DNA'yı yeniden oluşturayım. Onaylıyor musun?"

---

## 15. DIRECTOR'IN KENDİ KENDİNİ DEĞERLENDİRMESİ

```
1. ÖNERİ UYGULAMA ORANI
   < %30: Öneriler çok zor/alakasız, kalibrasyon gerekiyor

2. ETKİ TAHMİN DOĞRULUĞU
   "+6 puan getirir" dedim → gerçekte kaç puan getirdi?
   Ortalama hata > ±3 puan: Tahmin modeli yanlış kalibre

3. FALSE ALARM ORANI
   "Kritik sorun" dediğim durumların kaçı gerçekten kritikti?
   > %30 yanlış alarm: Signal kalitesini artır

4. MISSED SORUNLAR
   Kullanıcının bildirdiği sorunlar önceden tespit edildi mi?
   Tespit edilmediyse: Hangi event bu sorunu yakalardı?

5. TOKEN VERİMLİLİĞİ
   Analiz başına token → Kaliteli öneri üretiyor mu?
```

---

## 16. OTOMATİK TEST SİSTEMİ

### 16.1 Test Tipleri

| Test | Süre | Amaç |
|------|------|------|
| Full E2E | ~15 dk | Tüm pipeline + M2 suite |
| Module 1 Only | ~10 dk | Yalnızca pipeline |
| Module 2 Suite | ~5 dk | Reframe + Captions + YouTube |
| Regression | ~10 dk | Önceki test ile karşılaştır |
| Prompt A/B | ~20 dk | Prompt versiyonları karşılaştır |

### 16.2 Test Videosu Konfigürasyonu

```python
{
  "director_test_config": {
    "test_video_r2_url": "https://pub-xxx.r2.dev/test/benchmark.mp4",
    "test_video_duration_s": 480,
    "test_guest_name": "Test Guest",
    "test_channel_id": "speedy_cast",
    "expected_min_clips": 2,
    "expected_max_clips": 8,
    "baseline_standalone_score": 6.5
  }
}
```

### 16.3 Full E2E Test Akışı

```
1. Test job oluştur (is_test_run = true)
2. Pipeline çalıştır S01-S08 (speaker confirm otomatik)
3. Klip çıktı analizi (otomatik, Gemini yok):
   - Pass/fixable/fail dağılımı
   - Puan dağılımı (min, max, avg, median)
   - Süre dağılımı, içerik çeşitliliği
   - Kelime snap başarı oranı, R2 upload başarısı
4. Gemini düşünce zinciri analizi:
   - S05: Her adayın seçilme gerekçesi, primary_signal dağılımı
   - S06: Reddetme gerekçeleri, puan tutarlılığı, thinking_steps kalitesi
5. Prompt kalite analizi (Gemini Flash çağrısı)
6. Channel DNA denetimi
7. En iyi klibi editöre yönlendir (opsiyonel, kullanıcı onaylar)
8. Modül 2 testleri
9. Rapor üret → director_analyses'e kaydet → regression delta
```

### 16.4 Reframe Kalite Testi

```
Ölçümler:
1. Yüz tespit durumu:
   DNN başarı > %85 → İdeal
   DNN %50-85      → Kabul, uyarı yaz
   DNN < %50       → Sorunlu, yüksek öncelikli öneri

2. Konuşmacı takip doğruluğu (diarization ile):
   Konuşmacı 0 → sol yüz, Konuşmacı 1 → sağ yüz
   Her 0.5s kontrol: doğru_segment / toplam_segment

3. Sahne geçişi:
   Sahne sınırında keyframe var mı?
   Hold → Linear geçişi doğru mu?

4. EMA yumuşatma:
   Shake: > 50px / 0.5s → uyarı
   Lag: Geçişi 2s+ geç yakalamak → uyarı

Çıktı:
{face_detection_rate, dnn_rate, haar_fallback_rate,
 speaker_tracking_accuracy, scene_detection_count,
 keyframe_count, shake_events, lag_events, overall_score}
```

### 16.5 Caption Drift Testi

```
Ölçümler:
1. API başarısızlık oranı
2. Kelime güvenilirliği (avg confidence < 0.80 → uyarı)
3. Segment boyutu (optimal: 1.5-3.5s)
4. Timestamp kayma (< 200ms ideal, > 500ms sorunlu)
5. Punctuation kalitesi

Çıktı:
{avg_confidence, segment_count, short_segments, long_segments,
 avg_segment_duration_s, drift_avg_ms, overall_score}
```

### 16.6 Regression Test

```python
regression_report = {
  "previous_score": 71,
  "current_score": 68,
  "delta": -3,
  "degraded_dimensions": ["ai_quality"],
  "improved_dimensions": ["technical"],
  "regression_cause_hypothesis": "...",
  "action_required": True
}
```

---

## 17. DIŞ ENTEGRASYON ARAÇLARI

### 17.1 Langfuse Cloud — LLM Gözlemlenebilirliği

```python
# main.py'de başlangıçta:
from openinference.instrumentation.vertexai import VertexAIInstrumentor
VertexAIInstrumentor().instrument()
# Tüm Gemini çağrıları otomatik trace'e düşer

# Director analiz sonrası kalite skoru ekler:
langfuse.create_score(
    trace_id=s05_trace_id,
    name="clip_pass_rate",
    value=0.42,
    data_type="NUMERIC"
)
```

Langfuse Dashboard'da: Her S05/S06 trace, token kullanımı, latency, Director kalite skorları, maliyet grafiği.

```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

### 17.2 PostHog Cloud — Frontend Davranışı

```typescript
// Editor'da:
posthog.capture('reframe_triggered', {
    session_id, has_diarization: Boolean(clipJobId), clip_duration_s
})
posthog.capture('captions_generated', {session_id, word_count, language_detected})
posthog.capture('editor_export_completed', {
    session_id, had_reframe, had_captions, time_from_open_ms
})
posthog.capture('youtube_metadata_accepted', {title_changed, description_changed})
```

Director PostHog Query API'sinden M2 analizi için veri çeker.

```
NEXT_PUBLIC_POSTHOG_KEY=phc_...
```

### 17.3 Sentry — Hata Takibi

```python
# Backend (main.py):
sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=1.0)
```

```typescript
// Frontend:
Sentry.init({dsn: NEXT_PUBLIC_SENTRY_DSN, tracesSampleRate: 0.5})
```

Director Sentry Issues API'den açık hataları çeker, Teknik Sağlık skoruna ekler.

```
SENTRY_DSN=...
SENTRY_AUTH_TOKEN=sntrys_...
```

### 17.4 Araç İş Bölümü

```
Olay                    Langfuse  PostHog  Sentry  Supabase
────────────────────────────────────────────────────────────
Gemini API çağrısı         ✓        -        -        -
Token kullanımı            ✓        -        -        -
Director kalite skoru      ✓        -        -        ✓
Backend exception          -        -        ✓        -
Pipeline adım süresi       -        -        -        ✓
Reframe tetiklendi         -        ✓        -        ✓
Caption oluşturuldu        -        ✓        -        ✓
Editor export              -        ✓        -        ✓
Frontend exception         -        -        ✓        -
Kullanıcı klip onayı       -        -        -        ✓
```

---

## 18. VERİTABANI ŞEMASI ÖZETI

```sql
-- Director tabloları
director_events              -- ham event log (M1+M2 hook'ları)
director_conversations       -- chat geçmişi
director_memory              -- uzun dönem semantik hafıza (pgvector)
director_analyses            -- analiz sonuçları + skorlar
director_recommendations     -- öneriler
director_cross_module_signals -- modüller arası sinyaller
director_prompt_lab          -- prompt A/B testleri
director_test_runs           -- otomatik test sonuçları

CREATE TABLE director_test_runs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  timestamp     TIMESTAMPTZ DEFAULT now(),
  test_type     TEXT NOT NULL,
  status        TEXT DEFAULT 'running',
  test_job_id   UUID,
  results       JSONB,
  module1_score INT,
  module2_score INT,
  delta_from_prev JSONB,
  completed_at  TIMESTAMPTZ
);
```

---

## 19. KOD YAPISI

```
backend/app/director/
├── agent/
│   ├── core.py               → Ana loop: mesaj → context → Gemini → araç → yanıt
│   ├── system_prompt.py      → Director kimliği
│   └── context_builder.py    → Geçmiş + hafıza + snapshot birleştirme
├── tools/
│   ├── registry.py           → Gemini function calling schema
│   ├── read_tools.py         → read_file, list_files, search_codebase, query_database
│   ├── query_tools.py        → get_pipeline_stats, get_clip_analysis, get_langfuse_data
│   ├── external_tools.py     → get_sentry_issues, get_posthog_events, web_search
│   ├── write_tools.py        → edit_file, update_database, update_channel_dna
│   ├── memory_tools.py       → save_memory, query_memory, list_memories, delete_memory
│   └── action_tools.py       → trigger_analysis, trigger_test, send_notification
├── memory/
│   ├── conversation.py       → director_conversations CRUD
│   ├── long_term.py          → director_memory embed + semantic search
│   └── snapshot.py           → Anlık sistem özeti (Gemini gerekmez)
├── collector/
│   ├── base_collector.py     → emit() arayüzü, async, hata fırlatmaz
│   ├── module1_collector.py  → M1 event hook'ları
│   └── module2_collector.py  → M2 event hook'ları
├── analysis/
│   ├── scorer.py             → Puan hesaplama (otomatik)
│   ├── scheduler.py          → Günlük otomatik analiz
│   └── dashboard_writer.py   → director_analyses'e yazma
├── test_runner/
│   ├── e2e_runner.py
│   ├── module2_suite.py
│   ├── regression_runner.py
│   └── prompt_ab_runner.py
├── analyzers/
│   ├── module1_analyzer.py
│   ├── module2_analyzer.py
│   ├── reframe_analyzer.py
│   ├── caption_analyzer.py
│   ├── channel_dna_auditor.py
│   └── prompt_lab_analyzer.py
├── integrations/
│   ├── langfuse_client.py
│   ├── posthog_reader.py
│   └── sentry_reader.py
├── cost_tracker.py           → Token/maliyet takibi (Langfuse'dan)
└── api/
    ├── chat_routes.py        → POST /director/chat (SSE streaming)
    ├── dashboard_routes.py   → GET /director/status
    ├── memory_routes.py      → GET/DELETE /director/memory
    └── test_routes.py        → POST /director/test/run

frontend/app/dashboard/director/
├── page.tsx                  → Dashboard
├── chat/page.tsx             → Chat arayüzü (SSE streaming)
├── analysis/[module]/page.tsx
└── test/page.tsx
```

---

## 20. API ENDPOINTS

```
POST /director/chat                      → SSE stream
GET  /director/chat/history/{session_id} → Son 50 mesaj

GET  /director/status                    → Tüm modüller özet (DB'den, Gemini'siz)
GET  /director/module/{name}             → Tek modül detayı
GET  /director/analyses/{name}           → Analiz geçmişi

GET  /director/memory                    → Tüm hafıza
DELETE /director/memory/{id}

POST /director/analyze/{module}          → Manuel analiz tetikle
POST /director/test/run                  → Test başlat
GET  /director/test/{run_id}/status
GET  /director/test/{run_id}/report

POST /director/recommendation/{id}/mark  → applied | dismissed
```

---

## 21. KISITLAR

**Asla:**
- git push / deploy
- clips, jobs, transcripts tablolarına yazma
- Kullanıcı adına karar verip uygulama

**Onay alarak:**
- Python/TypeScript kod değişikliği
- Channel DNA büyük güncelleme
- Paralel test çalıştırma

**Serbestçe:**
- Tüm MD dosyalarını okuma ve düzenleme
- Supabase'den okuma (tüm tablolar)
- director_* tablolarına yazma
- Hafızaya kayıt
- Araç zinciri kurma
- Web araştırması

---

## 22. COLD START

```
0 konuşma:
  Tüm MD dökümanları okunur, son 30 günün verisi çekilir.
  "Merhaba. Sistemi inceledim. X pipeline çalışmış, pass rate %Y.
   İlk bakışta dikkat çeken: ..."

1-4 pipeline:
  "Az veri var ama şunu söyleyebilirim:"

5+ pipeline:
  Tam analiz ve puanlama aktif

20+ pipeline:
  Trend analizi aktif
```

---

## 23. YENİ MODÜL ENTEGRASYON PROTOKOLÜ

```
Yeni modül eklendiğinde:
1. docs/MODULE_N.md oluştur
2. collector/module_n_collector.py yaz
3. analyzers/module_n_analyzer.py yaz
4. scorer.py'a yeni modül boyutları ekle
5. Dashboard'a sağlık kartı ekle
6. Test runner'a modül testi ekle
7. Bu dokümanda "Modül N Puanlama Detayları" bölümü ekle
```

---

## 24. YAYINLAMA PLANI

> **Not:** Faz 0 önce gelir — çalışan bir chat olmadan dış araç entegrasyonu doğrulanamaz.

### Faz 0 — Çalışan Chat (öncelik 1)
1. `director_conversations` + `director_memory` tabloları
2. Tool registry + temel araçlar (read_file, query_database, save_memory)
3. Agent core loop (Gemini Pro + function calling)
4. SSE streaming chat endpoint
5. Basit chat frontend

### Faz 1 — Dış Araçlar (önce chat çalıştıktan sonra)
6. Sentry + Langfuse Cloud + PostHog kurulumu ve reader araçları
7. web_search (Brave/DuckDuckGo)

### Faz 2 — Event Sistemi ve Dashboard
8. M1 ve M2 event hook'ları (S05, S06, S07, S08)
9. pipeline_audit_log doldurma
10. scorer.py (otomatik puan, olgunluk tabanlı ağırlıklar)
11. Health Pulse (Bölüm 28)
12. Dashboard frontend

### Faz 3 — Aksiyon Araçları
13. trigger_analysis, trigger_test, update_channel_dna, send_notification
14. edit_file, update_database yazma araçları
15. Günlük + haftalık otomatik analiz scheduler (Bölüm 29)
16. Proaktif tetikleyiciler (Bölüm 26)

### Faz 4 — Zeka Katmanı (sürekli)
17. Cost Intelligence Engine (Bölüm 25)
18. Learning Loop (Bölüm 27)
19. Decision Journal (Bölüm 30)
20. Channel DNA Denetçisi
21. Prompt Lab + DNA Denetçisi
22. Cross-module köprüsü

---

---

## 25. COST INTELLIGENCE ENGINE

### 25.1 Amaç

Langfuse token verilerini Supabase'e job bazında aggregate ederek anomali tespiti ve optimizasyon önerileri üret.

### 25.2 Per-Job Cost Tracking

```python
# Her pipeline tamamlandığında:
cost_data = {
    "job_id": job_id,
    "s05_input_tokens": ...,
    "s05_output_tokens": ...,
    "s05_cost_usd": ...,
    "s06_input_tokens": ...,
    "s06_output_tokens": ...,
    "s06_cost_usd": ...,
    "total_cost_usd": ...,
    "cost_per_clip_usd": total_cost / max(clip_count, 1),
    "deepgram_cost_usd": ...,
}
# director_events'e yazılır: event_type="pipeline_cost_tracked"
```

### 25.3 Anomali Tespiti (2σ Kural)

```python
def detect_cost_anomaly(current_cost: float, historical: list[float]) -> dict:
    mean = statistics.mean(historical)
    std = statistics.stdev(historical) if len(historical) > 1 else 0
    z_score = (current_cost - mean) / std if std > 0 else 0

    if z_score > 2.0:
        return {"anomaly": True, "type": "spike", "z_score": z_score,
                "mean_usd": mean, "current_usd": current_cost}
    if z_score < -2.0:
        return {"anomaly": True, "type": "drop", "z_score": z_score}
    return {"anomaly": False}
```

### 25.4 Director Cost Araçları

```python
get_cost_breakdown(days: int = 30, per: str = "job") -> dict
  # per: "job" | "step" | "channel" | "day"

get_cost_trend(days: int = 30) -> dict
  # 7 günlük hareketli ortalama, trend yönü

detect_cost_anomalies(threshold_sigma: float = 2.0) -> list[dict]
  # Son 30 günün z-score analizi
```

---

## 26. PROAKTİF TETİKLEYİCİLER

### 26.1 6 Rule-Based Trigger

Director aşağıdaki durumları periyodik kontrol eder (her pipeline sonrası + günlük 09:00):

```
TRIGGER 1: DNA_STALE
  Koşul: channel_dna.updated_at > 90 gün VEYA reference_clip_count < 5
  Mesaj: "Kanal DNA'sı {N} gündür güncellenmedi. Performansı etkileyebilir."
  Aksiyon: update_channel_dna öner

TRIGGER 2: PERFORMANCE_DROP
  Koşul: Son 7 gün pass_rate < (son 30 gün pass_rate - 10%)
  Mesaj: "Pass rate son haftada %{N} düştü. S05/S06 loglarına bakıyorum."
  Aksiyon: trigger_analysis(module="clip_pipeline")

TRIGGER 3: COST_SPIKE
  Koşul: Son job cost > 2σ üzerinde
  Mesaj: "Son pipeline maliyeti normalin {N}x üzerinde (${X})."
  Aksiyon: get_cost_breakdown ile adım bazlı analiz

TRIGGER 4: UNUSED_CLIPS
  Koşul: Son 14 günde pass klipler var ama editor'da hiç açılmamış
  Mesaj: "{N} adet pass klip editörde hiç açılmadı. Sorun mu var?"

TRIGGER 5: SUCCESS_CELEBRATION
  Koşul: Son 5 job'da pass_rate > 60% VEYA avg_confidence > 8.0
  Mesaj: "Son 5 job'da harika sonuçlar — pass rate %{N}. Neyi doğru yapıyoruz?"
  Aksiyon: Başarı pattern'ini hafızaya kaydet

TRIGGER 6: NEW_PATTERN_DETECTED
  Koşul: Belirli content_type'ın son 14 günde pass rate'i > 2x arttı/azaldı
  Mesaj: "'{type}' içerikleri son 2 haftada %{N} değişti. Hafızaya kaydedeyim mi?"
```

### 26.2 Tetikleyici Kontrolü

```python
async def check_proactive_triggers(job_id: str = None) -> list[dict]:
    """Pipeline sonrası veya günlük cron'dan çağrılır."""
    triggers = []
    # Her trigger check fonksiyonu çalışır
    # Sonuçlar director_events'e kaydedilir: event_type="proactive_trigger"
    # Kritik olanlar öneri olarak da yazılır
    return triggers
```

---

## 27. ÖĞRENME DÖNGÜSÜ (Learning Loop)

### 27.1 Kullanıcı Sinyal → Memory Pipeline

```
clip_feedback_received event geldiğinde Director otomatik:
  1. Sinyali analiz et (hangi content_type, hangi puan aralığı)
  2. Pattern var mı kontrol et (memory'de benzer kayıt)
  3. Varsa güncelle, yoksa yeni memory yaz
  4. DNA audit için flag at
```

### 27.2 Sinyal Tipleri ve Memory Dönüşümü

```
approved:       Gemini pass + kullanıcı onay → "Bu tip çalışıyor" memory
rejected:       Gemini pass + kullanıcı red → "Bu tip aslında çalışmıyor" (yüksek öncelik)
edited_title:   Başlık değiştirildi → Tercih edilen başlık stilini öğren
reordered:      Klip sırası değiştirildi → Sıralama tercihlerini öğren
```

### 27.3 Örnek Memory Çıktısı

```
type: "learning"
content: "Kullanıcı son 3 haftada 'controversial_take' içeriklerin %80'ini reddetti.
          Gemini avg 6.8 veriyor ama kullanıcı tercih etmiyor.
          DNA'ya no_go_zones'a eklenebilir."
tags: ["content_type", "controversial_take", "user_signal", "dna_candidate"]
```

---

## 28. HEALTH PULSE

### 28.1 Amaç

5 dakikada bir (veya pipeline sonrası) Gemini çağrısı olmadan sistem sağlığını ölç.

### 28.2 Metrikler ve Ağırlıklar

```python
health_checks = {
    "pipeline_success_rate":    {"weight": 0.30, "source": "jobs table"},
    "avg_clip_confidence":      {"weight": 0.20, "source": "clips table"},
    "open_critical_issues":     {"weight": 0.20, "source": "sentry + director_recommendations"},
    "dna_freshness":            {"weight": 0.15, "source": "channels table"},
    "cost_trend":               {"weight": 0.10, "source": "director_events"},
    "gemini_error_rate":        {"weight": 0.05, "source": "langfuse"},
}

# Sonuç:
health_pulse = {
    "score": 78,           # 0-100, ağırlıklı ortalama
    "status": "IYI",       # KRITIK|ZAYIF|ORTA|IYI|GUCLU
    "checks": {...},       # Her check detayı
    "last_updated": "...", # Timestamp
    "gemini_used": False   # Hızlı kontrol, Gemini gerekmez
}
```

### 28.3 Dashboard Entegrasyonu

Health Pulse her 5 dakikada güncellenir. Dashboard `/director/health-pulse` endpoint'inden çeker. Puan kritik seviyeye düşünce otomatik alert.

---

## 29. HAFTALIK ÖZET (Weekly Digest)

### 29.1 Zamanlama

Her Pazartesi 09:00 otomatik çalışır. Gemini Pro çağrısı içerir.

### 29.2 Özet İçeriği

```
HAFTALIK ÖZET — {tarih aralığı}

Pipeline Özeti:
  {N} job çalıştı, {X} klip üretildi
  Pass rate: %{Y} (geçen hafta: %{Z}, trend: ↑/↓/→)

En İyi Performans:
  {content_type}: %{pass_rate} pass rate

Dikkat Edilmesi Gerekenler:
  - {anomaly veya sorun varsa}

Bu Hafta Uygulanan Öneriler: {N}
Bekleyen Kritik Öneriler: {N}

Önerilen Aksiyon:
  "{Director'ın stratejik önerisi}"
```

### 29.3 Scheduler

```python
# Railway cron veya APScheduler
schedule:
  - "haftalik_ozet": her Pazartesi 09:00
  - "gunluk_analiz": her gün 03:00
  - "health_pulse": her 5 dakika
  - "proaktif_kontrol": her pipeline sonrası + her saat
```

---

## 30. KARAR GÜNLÜĞü (Decision Journal)

### 30.1 Amaç

Kullanıcının aldığı önemli kararları ve sonuçlarını takip et. Gelecekte aynı karar noktasında geri bakabilmek için.

### 30.2 Tablo

```sql
CREATE TABLE director_decision_journal (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  timestamp       TIMESTAMPTZ DEFAULT now(),
  decision        TEXT NOT NULL,         -- Ne kararı alındı
  context         TEXT,                   -- Neden bu karar
  alternatives    TEXT,                   -- Değerlendirilen alternatifler
  expected_impact TEXT,                   -- Beklenen sonuç
  actual_impact   TEXT,                   -- Gerçekte ne oldu (sonradan doldurulur)
  status          TEXT DEFAULT 'open',    -- open | measured | archived
  channel_id      TEXT,
  related_rec_id  UUID REFERENCES director_recommendations(id),
  measured_at     TIMESTAMPTZ
);
```

### 30.3 Kullanım

```
Director bir öneri onaylandığında → decision_journal'a otomatik kayıt
2 hafta sonra → Director ölçüm yapar, actual_impact doldurur
Pattern analizi: "Benzer kararlar ne kadar doğru sonuçlandı?"
```

---

## 31. ÇOKLU KANAL ZEKASı (Multi-Channel Intelligence)

> **Durum:** 2 aktif kanal mevcut. Bu özellik aktif olarak kullanılabilir.

### 31.1 Kanal Karşılaştırması

```python
compare_channels(channel_a: str, channel_b: str, metric: str) -> dict
  # metric: "pass_rate" | "content_types" | "duration_distribution" | "dna_similarity"
  # Örnek: "speedy_cast vs channel_b: Teknik içerikler A'da %40 daha iyi performans"
```

### 31.2 Bilgi Transferi

```
Kanal A'da başarılı bir pattern → Kanal B DNA'sına önerilir
Kanal B'de fail olan tip → Kanal A için uyarı üretilir
Ortak "evrensel" başarı patternleri hafızaya kaydedilir
```

### 31.3 Kanal Bazlı Scoring

Her kanal kendi geçmişiyle değerlendirilir. `_calculate_module_scores()` channel_id parametresi alır.

---

*Bu döküman Director'ın kendi erişimine açıktır. Sistem değiştiğinde Director bu dosyayı da güncelleyebilir.*
