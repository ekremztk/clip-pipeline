# DIRECTOR MODÜLÜ — Tam Sistem Planı
> Versiyon 1.0 — Planlama Aşaması | 2026-03-24
> Bu döküman Director modülünün nihai tasarım belgesidir.

---

## 0. TASLAKTAN NELER ALINDI, NELER DEĞİŞTİ

### Alınanlar
- Katmanlı mimari yaklaşımı (veri toplama → hafıza → analiz zinciri)
- 5 boyutlu puanlama sistemi (revize edildi)
- Öneri anatomisi (6 bileşen)
- Sağlık kartı arayüz konsepti
- Cross-module sinyaller fikri
- Director'ın kendi kendini değerlendirmesi

### Değiştirilenler
- **K0-K5 sinyalleri kaldırıldı** — Mevcut sistemimizde bu kavram yok. Onun yerine gerçek veri kaynaklarımız kullanılır: `channel_dna`, `guest_profiles`, `reference_clips`, `channel_memory`.
- **"Minimum 30 çalışma" cold start** → Minimum 5 çalışma (küçük örneklem uyarısıyla göster, susturma).
- **"Direktor hiçbir iş yapmaz"** prensibi yumuşatıldı — Director test modunda API'leri doğrudan çağırır, klibi editöre yönlendirir, analiz raporları oluşturur. Yayınlamaz ama test eder.
- **4 Gemini çağrısı → 2-4 adaptif** — Basit analizde 2 çağrı yeterli. Pro model yalnızca kod analizi ve derin değerlendirmede kullanılır; geri kalanı Flash.

### Eklenenler
- **Langfuse Cloud** — Her Gemini çağrısını izler, token/maliyet takibi, Director kalite skorları ekleme
- **PostHog Cloud** — Frontend editör davranış analitiği (caption, reframe, export eylemleri)
- **Sentry** — Railway backend + Vercel frontend hata takibi
- Otomatik test suite (E2E, Modül 2, Regression, Prompt testi)
- Reframe frame bazlı kalite analizi
- Caption drift analizi
- Kanal DNA sağlık denetimi
- Prompt Laboratuvarı
- İnternet araştırması (Gemini grounding)
- Model maliyet takibi
- Gelecek modül entegrasyon protokolü

---

## 1. MODÜLÜN ÖZÜ

Director, Prognot'un tüm sistemlerini analiz eden, test eden, sorgulayan ve "gerçekte ne durumdasın?" sorusunu yanıtlayan üst katman bir modüldür.

**Director ne değildir:**
- Bir monitoring sistemi değil (Grafana gibi pasif izleme yapmaz)
- Bir deployment aracı değil
- Bir içerik üretme modülü değil

**Director nedir:**
- Sistemin tamamını tanıyan ve sorgulayan bir stratejik akıl
- Test edilmemiş varsayımları test eden bir kalite kontrolcüsü
- Cesaretli değişim önerileri üretmekten çekinmeyen bir danışman
- Her modülün promptlarını, kararlarını, çıktı kalitesini ve öğrenme hızını ölçen bir analist

**Temel Prensip:**
> Hiçbir modül, hiçbir sistem, hiçbir aşama nihai karar değildir. Sistem çalışıyor görünse bile Director gerçekte ne döndüğünü bilecek ve mevcut mimariye meydan okumaktan çekinmeyecektir.

---

## 2. MİMARİ GENEL BAKIŞ

```
┌─────────────────────────────────────────────────────────────────┐
│                        PROGNOT SİSTEMİ                          │
│                                                                  │
│  Modül 1                  Modül 2               Gelecek...       │
│  [Klip Çıkartıcı]        [Editör]              [Content Finder] │
│       │                      │                       │           │
│       ▼                      ▼                       ▼           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    KATMAN 0                               │   │
│  │             EVENT COLLECTION LAYER                        │   │
│  │         (her modülde ince event hook'ları)                │   │
│  └─────────────────────────┬────────────────────────────────┘   │
│                             ▼                                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    KATMAN 1                               │   │
│  │                  HAFIZA SİSTEMİ                           │   │
│  │          Yapısal (Supabase) + Semantik (pgvector)         │   │
│  └─────────────────────────┬────────────────────────────────┘   │
│                             ▼                                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    KATMAN 2                               │   │
│  │               CROSS-MODULE KÖPRÜSÜ                        │   │
│  │           (modüller arası veri ilişkileri)                 │   │
│  └─────────────────────────┬────────────────────────────────┘   │
│                             ▼                                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    KATMAN 3                               │   │
│  │                  ANALİZ ZİNCİRİ                           │   │
│  │    Test Runner + Gemini Zinciri + Öneri Motoru            │   │
│  └─────────────────────────┬────────────────────────────────┘   │
│                             ▼                                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  DIRECTOR DASHBOARD                        │   │
│  │          Sağlık Kartları | Testler | Öneriler             │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. KATMAN 0 — VERİ TOPLAMA (Event System)

### 3.1 Tasarım Prensibi

Event hook'ları mevcut kodun işleyişini **hiç bozmaz**. Her adıma küçük, synchronous olmayan log çağrıları eklenir. Eğer log başarısız olursa, pipeline sessizce devam eder.

```python
# Örnek: S05'e event hook ekleme
try:
    candidates = await run_unified_discovery(...)
    # Ana iş burada bitiyor — başarılı

    # Director hook — asenkron, hata fırlatmaz
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
    # Pipeline hatası burada işleniyor
    raise
```

### 3.2 Modül 1 Event Kataloğu

```
pipeline_started
  payload: {job_id, channel_id, video_duration_s, has_trim, guest_name_provided, channel_dna_present}

pipeline_step_completed
  payload: {job_id, step_name, step_number, duration_ms, success, error_message}

s02_transcribe_completed
  payload: {job_id, duration_s, word_count, speaker_count, language_confidence, deepgram_confidence_avg}

s03_speaker_id_completed
  payload: {job_id, predicted_correctly (post-confirm'e göre), confirmation_wait_ms}

s05_discovery_completed
  payload: {job_id, candidate_count, video_used, fallback_mode (video/audio/transcript),
            guest_profile_cached, channel_memory_clip_count, gemini_input_tokens,
            gemini_output_tokens, gemini_duration_ms, gemini_retries}

s05_candidates_detail
  payload: {job_id, candidates: [{id, strength, content_type, needs_context, primary_signal}]}

s06_evaluation_completed
  payload: {job_id, batch_count, skipped_candidates, retry_count,
            pass_count, fixable_count, fail_count,
            avg_standalone, avg_hook, avg_arc, avg_channel_fit,
            gemini_input_tokens, gemini_output_tokens, gemini_duration_ms}

s06_quality_verdicts_detail
  payload: {job_id, verdicts: [{candidate_id, standalone, hook, arc, channel_fit,
                                 verdict, reject_reason, content_type, strategy_role}]}

s07_precision_cut_completed
  payload: {job_id, clips_adjusted, avg_boundary_shift_ms, no_word_timestamp_fallbacks}

s08_export_completed
  payload: {job_id, exported_count, failed_count, avg_ffmpeg_duration_ms,
            r2_upload_failures, total_duration_exported_s}

pipeline_completed
  payload: {job_id, total_duration_ms, pass_clips, fail_clips, partial}

pipeline_failed
  payload: {job_id, failed_at_step, error_type, error_message}

user_clip_approved
  payload: {clip_id, job_id, channel_id, clip_index, quality_verdict, overall_confidence}

user_clip_rejected
  payload: {clip_id, job_id, channel_id, reason_provided, standalone_score, hook_score}

clip_opened_in_editor
  payload: {clip_id, job_id, quality_verdict, posting_order}
```

### 3.3 Modül 2 Event Kataloğu

```
editor_session_started
  payload: {session_id, source (from_module1 | direct_upload), clip_id (if from module1)}

reframe_triggered
  payload: {session_id, clip_duration_s, job_id_provided (diarization available)}

reframe_completed
  payload: {session_id, duration_ms, total_frames_analyzed, face_detected_frames,
            fallback_frames (haar cascade used), scene_count, keyframe_count,
            diarization_used, speaker_switch_count}

reframe_face_detail
  payload: {session_id, per_scene_detection_rate: [{scene_idx, detection_rate}],
            left_face_segments, right_face_segments, no_face_segments}

captions_generated
  payload: {session_id, word_count, segment_count, avg_confidence, duration_s,
            language_detected, api_duration_ms}

youtube_metadata_generated
  payload: {session_id, title_accepted (kullanıcı değiştirdi mi), description_accepted,
            guest_name_provided}

editor_export_completed
  payload: {session_id, export_duration_ms, output_format, had_captions, had_reframe,
            time_from_session_start_ms}

editor_session_abandoned
  payload: {session_id, time_open_ms, actions_taken: [list]}
```

### 3.4 Veritabanı Tablosu: `director_events`

```sql
CREATE TABLE director_events (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  timestamp     TIMESTAMPTZ DEFAULT now(),
  module_name   TEXT NOT NULL,   -- 'module_1' | 'module_2' | 'director'
  event_type    TEXT NOT NULL,
  payload       JSONB NOT NULL,
  session_id    TEXT,            -- pipeline için job_id, editor için session uuid
  channel_id    TEXT
);

-- Index'ler
CREATE INDEX idx_director_events_module ON director_events(module_name, timestamp DESC);
CREATE INDEX idx_director_events_type ON director_events(event_type, timestamp DESC);
CREATE INDEX idx_director_events_session ON director_events(session_id);
```

---

## 4. KATMAN 1 — HAFIZA SİSTEMİ

### 4.1 Yapısal Hafıza: `director_analyses`

```sql
CREATE TABLE director_analyses (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  timestamp             TIMESTAMPTZ DEFAULT now(),
  module_name           TEXT NOT NULL,    -- 'module_1' | 'module_2' | 'system'
  triggered_by          TEXT NOT NULL,    -- 'manual' | 'scheduled' | 'post_test' | 'threshold'
  score                 INT NOT NULL,     -- 0-100
  subscores             JSONB NOT NULL,   -- {technical, ai_quality, output, learning, maturity}
  findings              JSONB NOT NULL,   -- bulgular listesi
  recommendations       JSONB NOT NULL,   -- öneri listesi [{id, priority, title, what, why, ...}]
  data_period_start     TIMESTAMPTZ,      -- analiz edilen dönem başlangıcı
  data_period_end       TIMESTAMPTZ,      -- analiz edilen dönem sonu
  data_points_used      INT,              -- kaç event/pipeline kullanıldı
  context_snapshot      JSONB,            -- analiz anındaki sistem durumu özeti
  gemini_calls          INT,              -- kaç Gemini çağrısı yapıldı
  total_tokens_used     INT
);
```

```sql
CREATE TABLE director_recommendations (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_id       UUID REFERENCES director_analyses(id),
  module_name       TEXT NOT NULL,
  priority          INT NOT NULL,        -- 1 (en önemli) - 7 (en az)
  impact_score      FLOAT,              -- beklenen puan artışı
  effort_score      INT,                -- 1 (kolay) - 5 (zor)
  title             TEXT NOT NULL,
  what              TEXT NOT NULL,       -- ne yapılacak (spesifik)
  why               TEXT NOT NULL,       -- hangi veriye dayanıyor
  expected_impact   TEXT NOT NULL,       -- beklenen etki (sayısal)
  risk              TEXT,                -- risk açıklaması
  alternative       TEXT,                -- alternatif yol
  data_needs        TEXT,                -- etkiyi ölçmek için ne gerekli
  status            TEXT DEFAULT 'pending',   -- pending | applied | dismissed | partial
  dismissed_reason  TEXT,
  applied_at        TIMESTAMPTZ,
  measured_impact   FLOAT,              -- gerçekleşen puan değişimi (applied sonrası)
  created_at        TIMESTAMPTZ DEFAULT now()
);
```

### 4.2 Semantik Hafıza (pgvector)

```sql
CREATE TABLE director_memory_embeddings (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_id   UUID REFERENCES director_analyses(id),
  content_type  TEXT NOT NULL,    -- 'finding' | 'recommendation' | 'analysis_summary' | 'test_result'
  content       TEXT NOT NULL,    -- embed edilecek metin
  embedding     vector(768),
  module_name   TEXT,
  score_at_time INT,
  created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_director_memory_embedding ON director_memory_embeddings
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);
```

**Nasıl kullanılır:**
Yeni analiz yapılırken mevcut durumun özeti embed edilir ve şu sorgu çalışır:

```python
# "Şu ana en çok benzeyen geçmiş durumları bul"
similar_past = supabase.rpc('match_director_memory', {
    'query_embedding': current_state_embedding,
    'match_threshold': 0.78,
    'match_count': 3,
    'module_filter': 'module_1'
}).execute()

# Bulunan benzer geçmiş durumlar Gemini'nin analiz çağrısına ek context olarak eklenir
```

---

## 5. KATMAN 2 — CROSS-MODULE KÖPRÜSÜ

```sql
CREATE TABLE director_cross_module_signals (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  timestamp       TIMESTAMPTZ DEFAULT now(),
  signal_type     TEXT NOT NULL,
  source_module   TEXT NOT NULL,
  target_module   TEXT NOT NULL,
  payload         JSONB NOT NULL,
  channel_id      TEXT
);
```

**İzlenen Sinyaller:**

```
m1_to_editor_flow
  Her klip için: Modül 1'den çıkan klip editöre açıldı mı?
  Hesaplama: COUNT(clip_opened_in_editor) / COUNT(pass_clips)
  Soru: "Modül 1'in çıkardığı kliplerin editör için gerçek değeri ne?"

editor_to_publish_flow
  Editörden export edilen klipler yayınlandı mı?
  Hesaplama: COUNT(published) / COUNT(editor_export_completed)
  Soru: "Editörden çıkan iş yayına hazır kalitede mi?"

m1_quality_vs_editor_use
  Yüksek puanlı kliplerin mi yoksa düşük puanlı olanların mı editörde daha çok açıldığı
  Soru: "Kullanıcı Gemini'nin puanlarına güveniyor mu?"

youtube_metadata_acceptance
  Üretilen başlık/açıklama değiştirilmeden mi kullanıldı?
  Soru: "YouTube metadata üretimi gerçekten işe yarıyor mu?"

caption_to_export_rate
  Caption eklendikten sonra export oranı nedir?
  Soru: "Captions eklemek export kararını etkiliyor mu?"
```

---

## 6. OTOMATİK TEST SİSTEMİ

Bu, Director'ın en kritik özelliğidir. Sistem çalışıyor gibi görünse de gerçekte ne çıkardığını, hangi kalitede çalıştığını tek tuşla ölçer.

### 6.1 Test Tipleri

| Test | Tetikleyici | Süre | Amaç |
|------|------------|------|------|
| Full E2E Test | Manuel | ~15 dk | Tüm sistemi uçtan uca test eder |
| Module 1 Only | Manuel | ~10 dk | Yalnızca pipeline kalitesini ölçer |
| Module 2 Suite | Manuel | ~5 dk | Reframe + Captions + YouTube test eder |
| Regression Test | Manuel / Otomatik | ~10 dk | Önceki test sonuçlarıyla karşılaştırır |
| Prompt A/B Test | Manuel | ~20 dk | Mevcut prompt vs önerilen promptu karşılaştırır |

### 6.2 Test Videosu Konfigürasyonu

```python
# Supabase settings tablosunda tutulur
{
  "director_test_config": {
    "test_video_r2_url": "https://pub-xxx.r2.dev/test/benchmark_video.mp4",
    "test_video_duration_s": 480,     # 8 dakika ideal test süresi
    "test_video_title": "Director Benchmark Video",
    "test_guest_name": "Test Guest",
    "test_channel_id": "speedy_cast",
    "expected_min_clips": 2,           # başarılı testte en az bu kadar klip çıkmalı
    "expected_max_clips": 8,
    "baseline_standalone_score": 6.5   # kabul edilebilir minimum ortalama
  }
}
```

Kullanıcı dashboard'dan test videosunu değiştirebilir.

### 6.3 Full E2E Test Pipeline'ı

```
TEST BAŞLAT (tek tuş)
  ↓
1. TEST JOB OLUŞTUR
   - Konfigürasyondaki test videosunu kullan
   - job_id = test_job_{timestamp}
   - is_test_run = true (director_events'e not düşülür)
   ↓
2. PIPELINE ÇALIŞTIR (S01-S08)
   - Normal pipeline tam olarak çalışır
   - Director tüm event'leri izler
   - Speaker confirmation: test modunda otomatik onay (predicted_map kullan)
   ↓
3. KLİP ÇIKTI ANALİZİ
   Sayısal ölçümler (Gemini gerekmez):
   - Toplam aday sayısı
   - Pass / fixable / fail dağılımı
   - Puan dağılımı (min, max, avg, median)
   - Süre dağılımı
   - İçerik türü çeşitliliği
   - Kelime snap başarı oranı (word_timestamps kullanıldı mı?)
   - R2 yükleme başarı oranı
   ↓
4. GEMİNİ DÜŞÜNCE ZİNCİRİ ANALİZİ
   S05 candidates_detail event'inden:
   - Her adayın seçilme gerekçesini oku (reason alanı)
   - primary_signal dağılımını analiz et
   - needs_context = true olan adayların oranı

   S06 quality_verdicts_detail event'inden:
   - Reddetme gerekçelerini kategorize et
   - Puan dağılımının tutarlılığını kontrol et
   - Benzer içerik türlerinde tutarlı puanlama var mı?
   - thinking_steps'in kalitesini Gemini ile değerlendir
   ↓
5. PROMPT KALİTE ANALİZİ (Gemini Flash çağrısı)
   Gönderilecek:
   - S05 ve S06 prompt'larının özeti (tam metin değil)
   - Bu testten çıkan klipler + verdikleri gerekçeler
   - Channel DNA'nın ne kadarı Gemini kararlarına yansıdı

   Sorular:
   - Prompt açık ve anlaşılır mı?
   - Gemini kararları kanal DNA'sıyla uyumlu mu?
   - Reddedilen kliplerin gerekçeleri mantıklı mı?
   - Prompt'ta çelişkili talimatlar var mı?
   ↓
6. KANAL DNA KALİTE ANALİZİ
   (Detaylar bölüm 11'de)
   ↓
7. EN İYİ KLİBİ EDITÖRE YÖNLENDİR (opsiyonel, kullanıcı onaylar)
   Test raporunda "Bu klibi editörde test et" butonu
   Kullanıcı onaylarsa → Editor URL'sine yönlendir
   ↓
8. MODÜL 2 TESTLERİ (Editor'daki kliple)
   ↓
9. TEST RAPORU OLUŞTUR
   - Puan hesapla (Katman 3 analiz zinciri)
   - Önerileri üret
   - Supabase'e kaydet (director_analyses)
   - Önceki test sonuçlarıyla karşılaştır (delta)
```

### 6.4 Modül 2 Test Suite

Reframe ve Caption testleri için ayrı test klibi kullanılabilir (veya E2E'den gelen en iyi klip).

#### Reframe Kalite Testi

```
TEST VİDEOSU: 2 konuşmacılı, bilinen konuşmacı geçişleri olan klip
BEKLENEN: Konuşmacı 0 = sol yüz, Konuşmacı 1 = sağ yüz

Ölçümler:

1. YÜZLERIN TESPIT DURUMU
   Toplam frame (0.5s örnekleme ile): N
   DNN ile tespit: X frame
   Haar fallback ile tespit: Y frame
   Hiç tespit yok: Z frame
   Başarı oranı = (X+Y) / N × 100

   UYARI EŞİKLERİ:
   > %85 DNN: İdeal
   50-85% DNN: Kabul edilebilir, uyarı yaz
   < %50 DNN: Sorunlu, yüksek öncelikli öneri üret

2. KONUŞMACI TAKİP DOĞRULUĞU
   Diarization verisi varsa:
   - Konuşmacı 0 segmentlerinde sol yüz takip ediliyor mu?
   - Konuşmacı 1 segmentlerinde sağ yüz takip ediliyor mu?
   - Geçiş noktalarında anlık kesim oluyor mu (EMA yerine snap)?

   Ölçüm: Beklenen_takip_yönü vs gerçekleşen_crop_x yönü karşılaştırması
   Her 0.5s'de bir kontrol: "doğru yanda mıyız?"
   Doğruluk oranı = doğru_segment_sayısı / toplam_segment_sayısı

3. SAHNE GEÇİŞİ TESTİ
   Tespit edilen sahne sayısı vs PySceneDetect'in bulduğu sayı
   Sahne sınırında keyframe var mı?
   Hold → Linear geçişi doğru mu?

4. EMA YUMUŞATMA KALİTESİ
   Aynı sahne içinde crop_x değişim hızı
   Çok hızlı değişim (shake): > 50px değişim / 0.5s = uyarı
   Çok yavaş değişim (lag): Konuşmacı geçişini 2s+ geç yakalamak = uyarı

5. FRAME KAÇIRMA TESTİ
   Belirlenen bir frame koordinatının
   keyframe interpolasyonuyla hesaplanan değeriyle karşılaştırması

Test çıktısı:
{
  "face_detection_rate": 0.87,
  "dnn_rate": 0.72,
  "haar_fallback_rate": 0.15,
  "speaker_tracking_accuracy": 0.91,
  "scene_detection_count": 4,
  "keyframe_count": 23,
  "avg_ema_smoothness": "good",
  "shake_events": 0,
  "lag_events": 1,
  "overall_reframe_score": 84
}
```

#### Caption Drift Testi

```
TEST SESİ: Bilinen transkripti olan klip (veya E2E testinden gelen klip)

Ölçümler:

1. API BAŞARISIZLIK ORANI
   Kaç kez Deepgram çağrısı yapıldı? Kaçı başarısız oldu?

2. KELIME GÜVENİLİRLİĞİ
   Deepgram'ın döndürdüğü confidence ortalaması
   < 0.80: Kalite düşük uyarısı

3. SEGMENT BOYUTU DAĞILIMI
   Çok kısa segmentler (< 1 saniye): okuma problemi
   Çok uzun segmentler (> 5 saniye): izleyici okuyamaz
   Optimal: 1.5-3.5 saniye arası

4. TIMESTAMP KAYMA TESTİ (bilinen transkriptle)
   Eğer test videosu için referans transcript varsa:
   Her kelimenin beklenen vs gerçekleşen timestamp farkını hesapla
   Ortalama kayma < 200ms: İdeal
   > 500ms: Drift problemi var

5. PUNCTUATION KALİTESİ
   Cümle sonlarında doğru noktalama var mı?
   Gereksiz kesim var mı?

Test çıktısı:
{
  "avg_confidence": 0.92,
  "segment_count": 18,
  "short_segments": 1,
  "long_segments": 0,
  "avg_segment_duration_s": 2.3,
  "drift_avg_ms": 87,       # bilinen transkript varsa
  "overall_caption_score": 89
}
```

### 6.5 Regression Test

Her yeni testin sonucu öncekiyle karşılaştırılır:

```python
regression_report = {
  "previous_score": 71,
  "current_score": 68,
  "delta": -3,
  "degraded_dimensions": ["ai_quality"],  # hangi boyut geriledi
  "improved_dimensions": ["technical"],
  "regression_cause_hypothesis": "S05 prompt değişikliği olmadı, ancak channel_memory 90 günlük dönem doldu ve güncellenmedi. Bu, kanal hafıza bağlamının boşalmasına neden olmuş olabilir.",
  "action_required": True
}
```

### 6.6 Prompt A/B Test

Director bir prompt iyileştirme önerisi ürettiğinde, mevcut ve önerilen promptu karşılaştırabilir:

```
AKIŞ:
1. Director: "S05 prompt'unun şu satırı değiştirilmeli: ..."
2. Kullanıcı Prompt Lab'da onaylar
3. Director AYNI TEST VİDEOSUNU iki kez çalıştırır:
   - Run A: Mevcut prompt
   - Run B: Önerilen prompt
4. Karşılaştırma:
   - Candidate sayısı farkı
   - Pass rate farkı
   - Ortalama puan farkı
   - Reasoning kalitesi (Gemini değerlendirmesi)
   - Token kullanımı farkı (maliyet etkisi)
5. Sonuç raporu: Hangi prompt daha iyi?
6. Kullanıcı kararı: Yeni promptu onayla veya reddet
```

---

## 7. KATMAN 3 — ANALİZ ZİNCİRİ

### 7.1 Adaptif Gemini Çağrı Zinciri

Analiz derinliğine göre 2-4 çağrı yapılır:

```
HIZLI ANALİZ (2 çağrı, Flash):
  Çağrı 1: Sayısal anomali yorumlama
  Çağrı 2: Sentez + puanlama + öneriler

STANDART ANALİZ (3 çağrı, Flash):
  Çağrı 1: Anomali tespiti + tarihsel karşılaştırma
  Çağrı 2: Davranışsal ve yapısal bulgular
  Çağrı 3: Sentez + puanlama + öneriler

DERİN ANALİZ (4 çağrı, Flash + 1 Pro):
  Çağrı 1 (Flash): Anomali tespiti + tarihsel karşılaştırma
  Çağrı 2 (Flash): Davranışsal bulgular
  Çağrı 3 (Pro):   Mimari ve kod analizi (fonksiyon imzaları + dokümantasyon analizi)
  Çağrı 4 (Flash): Sentez + puanlama + öneriler
```

**Tetikleme kuralı:**
- Test sonrası analiz → Derin Analiz
- Günlük scheduled → Standart Analiz
- Eşik aşımı uyarısı → Hızlı Analiz

### 7.2 Çağrı 1 — Anomali Tespiti ve Tarihsel Karşılaştırma

**Girdi** (Python'da hesaplanan ham metrikler):
```json
{
  "period": "son 7 gün",
  "module": "module_1",
  "metrics": {
    "pipeline_success_rate": 0.94,
    "avg_processing_time_ms": 420000,
    "gemini_retry_rate": 0.08,
    "s05_fallback_rate": 0.15,
    "s06_skip_rate": 0.04,
    "pass_rate": 0.38,
    "avg_standalone": 6.9,
    "avg_hook": 6.7,
    "avg_arc": 7.1,
    "r2_upload_fail_rate": 0.01,
    "word_snap_fallback_rate": 0.12
  },
  "similar_past_analyses": [
    {"date": "2025-12-15", "score": 64, "key_finding": "S05 fallback oranı %22'ye çıkmıştı, video upload sorunu vardı"},
    {"date": "2026-01-08", "score": 71, "key_finding": "Gemini retry oranı %15'ti, 429 hataları peak dönemdi"}
  ]
}
```

**Soru:** "Bu metriklerde anormal olan nedir? Geçmiş benzer durumlarla farkı nedir?"

### 7.3 Çağrı 2 — Davranışsal Bulgular

**Girdi:**
- S05 ve S06 thinking_steps örnekleri (son 20 klip)
- Channel DNA özeti
- Kullanıcı onay/red oranları (son 30 gün)
- Çağrı 1'in çıktısı

**Soru:** "Gemini'nin kararları tutarlı ve kaliteli mi? Kullanıcı davranışı sisteme güven mi gösteriyor yoksa şüphe mi? Kanal DNA'sı gerçekten Gemini kararlarına yansıyor mu?"

### 7.4 Çağrı 3 — Mimari Analiz (sadece Derin Analizde, Pro model)

**Girdi:**
- Kritik modül dosyalarının fonksiyon imzaları + docstring'leri + yorum satırları
- Bilinen hata logları
- DIRECTOR_MODULE.md'deki "Potansiyel İyileştirme Alanları"

**Soru:** "Mevcut implementasyonda yapısal sorunlar, eksik entegrasyonlar veya yanlış kurgular var mı? Cesaretli ama gerekli değişiklikler neler olmalı?"

**Önemli:**
Bu çağrıda Gemini tamamen farklı bir bakış açısıyla çalışır: "Sistemin her şeyi değiştirilebilir. S05'in tüm mantığı yanlış olabilir. Mimariyi sil baştan yeniden yazmak gereken bir şey var mı?" gibi cesur sorular sorulur.

### 7.5 Çağrı 4 — Sentez, Puanlama ve Öneriler

**Girdi:** Önceki tüm çağrıların çıktıları + cross-module sinyalleri + mevcut puanın alt skoru.

**Çıktı:**
```json
{
  "score": 73,
  "subscores": {
    "technical_health": 88,
    "ai_decision_quality": 65,
    "output_structural_quality": 71,
    "learning_adaptation": 58,
    "strategic_maturity": 62
  },
  "executive_summary": "Teknik altyapı sağlam. Ana sorun S05'in video yerine transkript fallback'e düşme oranının %15'e çıkması. Bu, büyük video dosyaları için GCS upload'ın optimize edilmesi gerektiğini gösteriyor.",
  "findings": [...],
  "recommendations": [...],
  "bold_calls": [...]  // cesaretli öneri varsa buraya
}
```

### 7.6 İnternet Araştırması (Gemini Grounding)

Director belirli durumlarda web araştırması yapabilir. Bu özellik Gemini'nin Google Search grounding özelliği kullanılarak uygulanır:

```python
# Kullanım durumları:
scenarios = [
    "Diarization doğruluğunu artırmak için güncel alternatifler neler?",
    "Whisper'ın CPU-only deployment'ı Railway için uygun mu oldu?",
    "Yüz tespitinde MediaPipe'e alternatif CPU-only yaklaşımlar neler?",
    "Gemini Pro video analizi için en iyi pratikler neler?",
    "YouTube Shorts için en viral klip süresi son verilere göre nedir?"
]

# Director bir araştırma önerisi ürettiğinde:
# "Bu konuda internet araştırması yap" seçeneği sunar
# Kullanıcı onaylarsa Gemini grounding çağrısı yapılır
# Sonuç öneri context'ine eklenir
```

---

## 8. PUANLAMA SİSTEMİ

### 8.1 Hesaplama Prensibi

Matematiksel hesaplamalar Python'da yapılır (hızlı, güvenilir, maliyet yok). Yorumlama ve puanın anlamlandırılması Gemini'ye bırakılır.

### 8.2 Beş Boyut (Her Modül İçin Ağırlıklar Farklı)

**Modül 1 Boyutları ve Ağırlıkları:**

```
BOYUT 1 — TEKNİK SAĞLIK (20 puan)
───────────────────────────────────
Tüm hesaplama otomatik, Gemini gerekmez.

Pipeline başarı oranı (son 30 gün) → 6 puan
  %100   = 6
  %95    = 5
  %90    = 4
  %80    = 2
  < %80  = 0

Ortalama işlem süresi (p95) → 4 puan
  < 6 dk = 4
  < 8 dk = 3
  < 12 dk = 2
  > 12 dk = 0

Gemini retry oranı → 4 puan
  < %5   = 4
  < %10  = 3
  < %20  = 1
  ≥ %20  = 0

R2 upload hata oranı → 3 puan
  < %1   = 3
  < %5   = 2
  ≥ %5   = 0

S05 fallback oranı (video→audio→transcript) → 3 puan
  < %5   = 3 (video büyük çoğunlukla kullanılıyor)
  < %15  = 2
  < %30  = 1
  ≥ %30  = 0 (video analizi neredeyse hiç çalışmıyor)


BOYUT 2 — AI KARAR KALİTESİ (35 puan)
───────────────────────────────────────
Kısmen otomatik, kısmen Gemini yorumu.

Pass rate (son 30 gün) → 8 puan
  > %50  = 8
  > %35  = 6
  > %20  = 3
  ≤ %20  = 0

Kullanıcı onay/red uyuşumu → 7 puan
  Gemini pass → kullanıcı onay: pozitif sinyal
  Gemini pass → kullanıcı red: ters sinyal (dikkat)
  Ters sinyal oranı:
  < %10  = 7
  < %25  = 4
  ≥ %25  = 1 (kullanıcı Gemini'ye güvenmiyor)

Ortalama standalone skoru → 7 puan
  ≥ 8.0  = 7
  ≥ 7.0  = 5
  ≥ 6.0  = 3
  < 6.0  = 0

Kanal DNA yansıma skoru → 8 puan
  (Gemini çağrısında değerlendirilen: klip kararları DNA ile uyumlu mu?)
  Çok uyumlu    = 8
  Uyumlu        = 5
  Kısmen        = 2
  Uyumsuz       = 0

İçerik çeşitlilik skoru → 5 puan
  5+ farklı content_type kullanılıyor → 5
  3-4 farklı → 3
  1-2 farklı → 1 (sistem tek tip klip seçiyor)


BOYUT 3 — ÇIKTI YAPISAL KALİTESİ (25 puan)
────────────────────────────────────────────
Çoğunlukla otomatik hesaplama.

Süre dağılımı uyumu → 7 puan
  Klipler channel_dna.duration_range içinde mi?
  ≥ %85  = 7
  ≥ %70  = 5
  ≥ %50  = 2
  < %50  = 0

Kelime snap başarı oranı → 5 puan
  S07'de word_timestamps kullanılan clip oranı:
  ≥ %90  = 5
  ≥ %70  = 3
  < %70  = 1 (transcript kalitesi düşük veya diarization hatası)

Hook kalitesi → 7 puan
  Ortalama hook_score:
  ≥ 7.5  = 7
  ≥ 6.5  = 5
  ≥ 5.5  = 2
  < 5.5  = 0

S06 skip oranı (Gemini atlayan adaylar) → 6 puan
  < %5   = 6
  < %10  = 4
  < %20  = 2
  ≥ %20  = 0


BOYUT 4 — ÖĞRENME VE ADAPTASYON (15 puan)
──────────────────────────────────────────
Gemini yorumu ağırlıklı.

3 aylık trend analizi → 6 puan
  AI Karar Kalitesi boyutu geçmişe kıyasla:
  Belirgin iyileşme = 6
  Hafif iyileşme    = 4
  Stabil            = 2
  Gerileme          = 0

Feedback entegrasyonu → 5 puan
  Kullanıcının reddettiği clip tiplerinde azalma var mı?
  Belirgin azalma   = 5
  Hafif azalma      = 3
  Değişim yok       = 1
  Artış var         = 0

Channel DNA güncelliği → 4 puan
  DNA son 90 günde güncellendi mi?
  Güncellendi AND referans clip sayısı ≥ 10 = 4
  Güncellendi ama az referans clip = 2
  90 günden eski = 0


BOYUT 5 — STRATEJİK OLGUNLUK (5 puan)
────────────────────────────────────────
Director'ın önerilerinin uygulanma durumu.

Açık kritik öneri sayısı → 3 puan
  0 kritik öneri = 3
  1-2 kritik öneri = 2
  3+ kritik öneri = 0

Önerilen/uygulanan öneri oranı → 2 puan
  ≥ %60 uygulandı = 2
  ≥ %30 uygulandı = 1
  < %30 uygulandı = 0
```

**Modül 2 Boyutları ve Ağırlıkları (Özet):**

```
Teknik Sağlık (20p): API başarı oranları, Deepgram/Gemini hataları, işlem süreleri
Araç Performansı (40p): Reframe doğruluğu (20p), Caption kalitesi (12p), YouTube metadata benimseme (8p)
Kullanıcı Deneyimi (25p): Session→export oranı, undo sayısı, terk oranı
Öğrenme (10p): Zaman serisi iyileşme
Stratejik Olgunluk (5p): Açık öneriler
```

### 8.3 Puan Eşikleri ve Renk Kodlama

```
0-35  : KRİTİK  (kırmızı)    — Temel işlevler çalışmıyor
36-55 : ZAYIF   (turuncu)    — Çalışıyor ama ciddi eksikler var
56-70 : ORTA    (sarı)       — İşlevsel ama optimize edilmemiş
71-84 : İYİ     (açık yeşil) — İyi durumda, ince ayarlar lazım
85+   : GÜÇLÜ   (yeşil)      — Bu seviyede sürekli kalmak zordur
                              Sistem sürekli yeni gereksinimler ürettiğinden
                              85+ gerçek anlamda başarılı anlamına gelir
```

**Puan düşebilir — bu normaldir.** Yeni özellik eklendiğinde "Stratejik Olgunluk" boyutu yeni gereksinimler üretir ve puan geçici olarak düşer. Bu sistemin durduğunu değil, geliştiğini gösterir.

**Veri eşikleri:**
```
1-4 pipeline:  "Yetersiz veri" uyarısıyla temel metrikler gösterilir
5-9 pipeline:  Puanlama aktif, ama "küçük örneklem" notu var
10+ pipeline:  Tam analiz
20+ pipeline:  Trend analizi aktif
```

---

## 9. ÖNERİ SİSTEMİ

### 9.1 Öneri Anatomisi (6 Bileşen)

```
ÖRNEK ÖNERİ:

başlık: "S05 Prompt'una Kanal Hafızası Bölümü Ekle"
öncelik: 1 (en yüksek)
etki_puanı: +8 (AI Karar Kalitesi boyutunda beklenen artış)
zorluk: 2/5 (kolay)

ne: "unified_discovery.py dosyasında build_channel_context() fonksiyonuna
    son 30 gündeki başarısız içerik türlerini "BAŞARISIZ PATTERN'LAR" başlığı
    altında ekle. Bu bilgi şu an sadece arka planda hesaplanıyor ama
    Gemini'ye iletilmiyor."

neden: "Son 30 günde 'educational_insight' türündeki klipler %12 başarı
        oranıyla en düşük performansı gösteriyor. Bu bilgi Gemini'ye
        iletilmiyor, bu nedenle sistem bu tür klipler seçmeye devam ediyor.
        director_events verisinde son 7 günde 8 adet educational_insight
        seçilip 6'sı kullanıcı tarafından reddedildi."

beklenen_etki: "Gemini'nin son 3 haftada en kötü performans gösteren içerik
                türlerini bilmesi, bu türde aday önerme oranını %40-60
                azaltabilir. Tahmini overall puan artışı: +4-6."

risk: "Prompt uzayacak, token kullanımı yaklaşık %8-12 artabilir.
       Aylık tahmini ek maliyet: $2-4."

alternatif: "Tam liste yerine yalnızca en kötü 2 içerik türünü ekle.
             Token artışı %4-6 ile sınırlı kalır."

veri_ihtiyacı: "Etkiyi ölçmek için değişiklikten sonra minimum 2 hafta
                ve 10+ pipeline çalışması gerekiyor."
```

### 9.2 Öneri Önceliklendirme

Maksimum 7 öneri sunulur. Sıralama:

```python
# Öneri skoru = (etki_puanı × 2) + (5 - zorluk) + güven_katsayısı
# Yüksek etki + düşük zorluk + yüksek güven = öne çıkar

# Örnek:
# Öneri A: etki=8, zorluk=2, güven=0.9 → skor = 16 + 3 + 0.9 = 19.9
# Öneri B: etki=12, zorluk=5, güven=0.7 → skor = 24 + 0 + 0.7 = 24.7
# Öneri B daha yüksek skor ama çok zor. İkisi birden gösterilir, sıralama B önce.
```

### 9.3 Cesaretli Kararlar (Bold Calls)

Sistem iyi çalışıyor görünse bile Director bazı önerileri "cesur ama gerekli" olarak işaretler:

```
BOLD CALL örnekleri:

"S05 için Gemini Pro kullanmak pahalı. Aynı video'yu önce Flash ile analiz et,
 yalnızca Flash'ın belirsiz bulduğu momentler için Pro'ya git. Hibrit yaklaşım
 token maliyetini %40-60 düşürebilir."

"Speaker ID heuristiği (en çok konuşan = misafir) gerçekte %78 doğrulukta.
 Bu çok düşük. PyAnnote Audio'nun daha doğru diarization modeli CPU-only olarak
 çalışabilir, Railway'de test edilmesi gerekiyor."

"Reframe face detection DNN modeli, sahnede iki kişi yoksa orta noktayı tutuyor
 ama bu davranış belirtilmemiş ve test edilmemiş. Yüz yokken davranış explicit
 olarak tanımlanmalı ve test edilmeli."

"Channel DNA'sı onboardingden bu yana güncellenmedi. Son 60 günlük performance
 verisi mevcut ama DNA'ya yansıtılmadı. Bu, sistemin öğrenme mekanizmasının
 çalışmadığı anlamına geliyor."
```

---

## 10. PROMPT LABORATUVARI

### 10.1 Amaç

Director, mevcut S05 ve S06 promptlarını analiz ederek iyileştirme önerileri üretir. Kullanıcı bu önerileri Prompt Lab üzerinde test edip onaylayabilir.

### 10.2 Çalışma Yapısı

```sql
CREATE TABLE director_prompt_lab (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  module_name      TEXT NOT NULL,
  step             TEXT NOT NULL,      -- 's05' | 's06' | 'channel_dna' | ...
  current_prompt_hash TEXT NOT NULL,   -- mevcut promptun hash'i (versiyon takibi)
  proposed_change  TEXT NOT NULL,      -- ne değişmeli (spesifik)
  rationale        TEXT NOT NULL,      -- neden (hangi veriye dayanıyor)
  status           TEXT DEFAULT 'proposed',  -- proposed | testing | approved | rejected
  test_job_a_id    UUID,              -- mevcut prompt ile test job
  test_job_b_id    UUID,              -- önerilen prompt ile test job
  test_comparison  JSONB,             -- A/B test sonuçları
  approved_at      TIMESTAMPTZ,
  created_at       TIMESTAMPTZ DEFAULT now()
);
```

### 10.3 Prompt Analiz Kriterleri

```
Director bir promptu şu sorularla değerlendirir:

1. NETLIK: Talimatlar tek yorumlu mu yoksa muğlak mı?
2. ÇELIŞKI: Farklı talimatlar birbiriyle çelişiyor mu?
3. KANAL DNA ENTEGRASYONU: DNA ne kadar prompt'a yansıtılmış?
   - do_list tam aktarılmış mı?
   - no_go_zones güçlü biçimde vurgulanmış mı?
4. OUTPUT FORMAT: JSON schema net tanımlanmış mı?
5. ÖRNEKLER: Zor durumlar için yönlendirici örnek var mı?
6. UZUNLUK VE TOKEN VERİMLİLİĞİ: Gereksiz tekrar var mı?
7. SKOR KALIBRASYONU: "6 = ortalama" kalibrasyonu net ifade edilmiş mi?
```

---

## 11. KANAL DNA DENETÇİSİ

Channel DNA'sı sistemin bel kemiğidir. Bozuk veya güncel olmayan DNA her şeyi etkiler.

### 11.1 DNA Sağlık Kontrolleri

```
1. GÜNCELLIK
   Son DNA güncellemesi ne zaman? > 90 gün ise uyarı.
   Kaç reference clip var? < 5 ise yetersiz.

2. TUTARLILIK
   do_list ve dont_list çelişiyor mu?
   Örnek: do_list: "teknik deep-dive yap" + dont_list: "teknik konulardan kaçın"
   Bu çelişki Gemini'yi kafa karıştırır.

3. GÜNCEL PERFORMANS YANSIMASI
   Son 30 günde fail olan içerik türleri dont_list'te var mı?
   Son 30 günde başarılı olan türler do_list'te güçlendirilmiş mi?

4. SPESİFİKLIK
   do_list'teki maddeler yeterince spesifik mi?
   "İyi içerik seç" → işe yaramaz.
   "Misafirin 8+ yıl önce yaşadığı başarısızlık anları" → işe yarar.

5. HOOK STILI KALIBRASIYONU
   hook_style mevcut seçilen klipler ile uyumlu mu?
   Kliplerin ilk cümleleri tanımlanan hook stilini yansıtıyor mu?

6. SÜRE UYUMU
   Seçilen klipler duration_range içinde mi?
   Sapma > %20 ise DNA'nın süre parametresi gerçeği yansıtmıyor.
```

### 11.2 DNA Güncelleme Tetikleyicisi

Eğer DNA sağlık skoru düşükse Director şunu önerir:
"Bu kanalın son 60 günlük başarılı kliplerine dayanarak DNA'yı yeniden oluştur. Çalıştır mı?"

---

## 12. DIRECTOR'IN KENDİ KENDİNİ DEĞERLENDİRMESİ

Director her analizde kendini de değerlendirir:

```
Kendi Değerlendirme Metrikleri:

1. ÖNERİ UYGULAMA ORANI
   Verilen önerilerin yüzdesi uygulandı mı?
   < %30: Öneriler çok zor/alakasız olabilir, kalibrasyon gerekiyor

2. ETKİ TAHMİN DOĞRULUĞU
   "Bu öneri +6 puan getirir" dedim → gerçekte kaç puan getirdi?
   Ortalama tahmin hatası
   > ±3 puan hata: Tahmin modeli yanlış kalibre

3. FALSE ALARM ORANI
   "Kritik sorun var" dediğim durumların kaçı gerçekten kritikti?
   > %30 yanlış alarm: Director çok hassas, signal kalitesini artır

4. MISSED SORUNLAR
   Kullanıcının bildirdiği sorunlar Director tarafından önceden tespit edildi mi?
   Tespit edilmediyse: Hangi event bu sorunu yakalardı?

5. GEMİNİ MALİYET VERİMLİLİĞİ
   Analiz başına ortalama token kullanımı
   Bu token'lar kaliteli öneri üretiyor mu?
```

---

## 13. VERİTABANI ŞEMASI ÖZETI

```sql
-- Tüm Director tabloları
director_events              → ham event log
director_analyses            → analiz sonuçları
director_recommendations     → öneriler
director_memory_embeddings   → semantik hafıza
director_cross_module_signals → modüller arası sinyaller
director_prompt_lab          → prompt A/B testleri
director_test_runs           → otomatik test sonuçları

-- Test runs tablosu
CREATE TABLE director_test_runs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  timestamp       TIMESTAMPTZ DEFAULT now(),
  test_type       TEXT NOT NULL,     -- 'e2e' | 'module1' | 'module2' | 'regression' | 'prompt_ab'
  triggered_by    TEXT DEFAULT 'manual',
  test_job_id     UUID,              -- oluşturulan test pipeline job
  status          TEXT DEFAULT 'running',   -- running | completed | failed
  results         JSONB,             -- test çıktıları
  module1_score   INT,
  module2_score   INT,
  delta_from_prev JSONB,            -- önceki test sonuçlarına fark
  completed_at    TIMESTAMPTZ
);
```

---

## 14. FRONTEND DASHBOARD

### 14.1 Modül Sağlık Kartları

```
┌─────────────────────────────────────────┐
│  Modül 1 — Klip Çıkartıcı              │
│                                          │
│  ████████████░░░░░░  73 / 100            │
│                                          │
│  Son analiz: 3 saat önce                 │
│  Değişim: ▲ +4 (geçen haftaya göre)     │
│                                          │
│  Teknik Sağlık     ████████████  88      │
│  AI Karar Kalitesi ████████░░░░  65 ⚠   │
│  Çıktı Kalitesi    █████████░░░  71      │
│  Öğrenme           ████████░░░░  58 ⚠   │
│  Stratejik Olg.    █████████░░░  62      │
│                                          │
│  ⚠ 2 kritik öneri bekliyor              │
│                                          │
│  [Analiz Çalıştır]  [Önerileri Gör]     │
│  [Test Başlat    ]  [Geçmiş Analizler]  │
└─────────────────────────────────────────┘
```

Renk kuralı: 0-35 kırmızı | 36-55 turuncu | 56-70 sarı | 71-84 açık yeşil | 85+ yeşil

### 14.2 Test Ekranı

```
DIRECTOR TEST MERKEZİ
─────────────────────

Test Videosu: benchmark_video.mp4 (8 dk)  [Değiştir]
Kanal: Speedy Cast

[ Full E2E Test    ] ← tüm pipeline + editor (≈15 dk)
[ Modül 1 Testi    ] ← yalnızca pipeline (≈10 dk)
[ Modül 2 Suite    ] ← reframe + captions + youtube (≈5 dk)
[ Regression       ] ← önceki test ile karşılaştır (≈10 dk)
[ Prompt A/B       ] ← öneri varsa aktif olur (≈20 dk)

Son Test: 2026-03-22 14:32 — Skor: 71 (Modül 1), 78 (Modül 2)
```

### 14.3 Analiz Sayfası

- Sol panel: Mevcut puan ve alt skorlar (gauge charts)
- Orta panel: Bulgular listesi (severity: critical/warning/info)
- Sağ panel: Öneriler (öncelik sırası, bir tıkla "uygulandı" işaretle)
- Alt panel: Zaman serisi grafik (son 8 analiz skorları)

### 14.4 Prompt Lab Sayfası

- S05 Prompt'un şu hali (read-only, hash gösterir)
- S06 Prompt'un şu hali
- Director'ın önerilen değişiklikleri
- "A/B Test Başlat" butonu
- Test sonuçları karşılaştırma tablosu

---

## 15. API ENDPOINTS

```
GET  /director/status
     → Tüm modüllerin özet sağlık durumu

GET  /director/module/{module_name}
     → Tek modül tam detayı (skor + alt skorlar + son bulgular + öneriler)

GET  /director/module/{module_name}/history
     → Son 10 analiz sonucu (trend verisi)

POST /director/analyze/{module_name}
     → Manuel analiz tetikle
     body: {depth: "quick" | "standard" | "deep"}

POST /director/test/run
     → Test çalıştır
     body: {test_type, options}

GET  /director/test/{run_id}/status
     → Test ilerleme durumu (WebSocket ile de izlenebilir)

GET  /director/test/{run_id}/report
     → Tamamlanan test raporu

POST /director/recommendation/{rec_id}/mark
     → Öneri durumu değiştir
     body: {status: "applied" | "dismissed", note}

GET  /director/prompt-lab
     → Mevcut prompt önerileri

POST /director/prompt-lab/{lab_id}/test
     → Prompt A/B test başlat

GET  /director/cross-module-signals
     → Modüller arası sinyal özeti

GET  /director/costs
     → Gemini token kullanımı ve maliyet özeti
```

---

## 16. KOD YAPISI

```
backend/app/director/
├── __init__.py
├── integrations/
│   ├── langfuse_client.py         → Langfuse Cloud bağlantısı, score yazma, usage okuma
│   ├── posthog_reader.py          → PostHog Query API, editor event'leri çekme
│   └── sentry_reader.py           → Sentry Issues API, açık hata listesi çekme
├── collector/
│   ├── base_collector.py          → emit() arayüzü, async, hata fırlatmaz
│   ├── module1_collector.py       → Modül 1 event hook'ları
│   └── module2_collector.py       → Modül 2 event hook'ları
├── memory/
│   ├── structural_memory.py       → director_analyses, recommendations CRUD
│   └── semantic_memory.py         → embed, store, search (pgvector)
├── bridge/
│   └── cross_module_signals.py    → sinyal hesaplama ve kaydetme
├── analysis/
│   ├── chain.py                   → adaptif Gemini çağrı zinciri
│   ├── scorer.py                  → puan hesaplama (Gemini gerekmez)
│   ├── recommender.py             → öneri üretimi ve önceliklendirme
│   └── internet_research.py       → Gemini grounding web araştırması
├── test_runner/
│   ├── e2e_runner.py              → Full E2E test
│   ├── module2_suite.py           → Modül 2 test suite
│   ├── regression_runner.py       → Regression test
│   └── prompt_ab_runner.py        → Prompt A/B test
├── analyzers/
│   ├── module1_analyzer.py        → Modül 1 metrik hesaplama
│   ├── module2_analyzer.py        → Modül 2 metrik hesaplama + PostHog verileri
│   ├── reframe_analyzer.py        → Reframe kalite analizi
│   ├── caption_analyzer.py        → Caption drift analizi
│   ├── channel_dna_auditor.py     → DNA sağlık kontrolü
│   └── prompt_lab_analyzer.py     → Prompt kalite analizi
├── cost_tracker.py                → Langfuse'dan token/maliyet verisi çekme
└── api/
    └── director_routes.py         → FastAPI endpoints

frontend/app/dashboard/director/
├── page.tsx                       → Ana Director sayfası (sağlık kartları)
├── test/
│   └── page.tsx                   → Test merkezi
├── analysis/
│   └── [module]/page.tsx          → Modül analiz detayı
└── prompt-lab/
    └── page.tsx                   → Prompt laboratuvarı
```

---

## 17. GEMİNİ MODEL KULLANIMI

```
Tüm Director analizleri → gemini-2.5-flash (varsayılan)
Mimari ve kod analizi (Derin Analiz, Çağrı 3) → gemini-3.1-pro-preview
İnternet araştırması → gemini-2.5-flash (grounding)
Prompt A/B karşılaştırma → gemini-2.5-flash

NOT: Director, S05/S06 Pro modelini değiştirme yetkisine sahip değildir.
Yalnızca kendi analizleri için model seçimi yapar.
```

---

## 18. KISITLAR VE SINIRLAR

### Director ne YAPMAZ

- Clip kesmez, encode etmez
- Promptları otomatik değiştirmez (önerir, insan onaylar)
- Pipeline'ı durdurmaz veya engellemez
- Klibi yayınlamaz
- Kullanıcı adına karar vermez

### Director ne YAPAR (aktif)

- Test pipeline'larını tetikler
- Backend API'leri test modunda çağırır (reframe, captions)
- Editörü bir kliple yönlendirir (URL ile)
- Analizleri Supabase'e kadar kaydeder
- Prompt Lab test çalıştırır (kullanıcı onayıyla)

### Cold Start Davranışı

```
1-4 pipeline çalışması:
  "Yeterli veri biriktirildi mi? [X/10 pipeline]" progress bar'ı göster
  Temel metrikler gösterilir ama puan hesaplanmaz
  Öneri yok

5-9 pipeline:
  Puan hesaplanır (küçük örneklem uyarısıyla)
  Kısmi öneriler (yalnızca sayısal tabanlı)
  Trend analizi yok

10+ pipeline:
  Tam analiz devreye girer
  Gemini çağrıları başlar

20+ pipeline:
  Trend analizi aktif
  Learning & Adaptation boyutu tam puanlanabilir
```

### Döngüsellik Riski

Gemini'yi Gemini'yi değerlendirmek için kullanmak döngüsellik riski taşır.

**Çözüm:**
- Değerlendirici Gemini çağrısı (Director) farklı ve izole bir system prompt kullanır
- Değerlendirici, değerlendirilen Gemini çağrısının thinking_steps'ini görmez (outcome'ı görür)
- Değerlendirici her zaman flash, değerlendirilen bazen pro — farklı kapasite

---

## 19. YENİ MODÜL ENTEGRASYON PROTOKOLÜ

Sisteme yeni bir modül (örn. Content Finder) eklendiğinde Director'a entegrasyon adımları:

```
1. docs/{MODULE_N}.md oluştur (Modül 1 ve 2 formatında)

2. collector/{module_n}_collector.py yaz:
   - Modülün ana işlemlerini event olarak kaydet
   - base_collector.py'den türet

3. analyzers/{module_n}_analyzer.py yaz:
   - Modüle özel puanlama boyutları tanımla
   - Sayısal metrik hesaplamaları ekle

4. scorer.py'a yeni modül için puan ağırlıkları ekle

5. Frontend'de yeni modül için sağlık kartı ekle

6. Test runner'a modül testi ekle

7. director_analyses tablosuna yeni module_name değeri yetkilendir

8. docs/DIRECTOR_MODULE.md'de "Modül N Puanlama Detayları" bölümü ekle
```

---

## 20. DIŞ ENTEGRASYON ARAÇLARI

Director üç dış araçla güçlendirilir. Her biri ayrı bir sorumluluk alanını kapsar ve birbirini tamamlar.

---

### 20.1 Langfuse — LLM Gözlemlenebilirliği

**Neden:** Her Gemini çağrısını izlemek, token maliyetini görmek, Director'ın analizlerinden sonra her trace'e kalite skoru eklemek için.

**Kurulum:** Langfuse Cloud (self-host değil — self-host ClickHouse + Redis + PostgreSQL + S3 gerektirir, Railway'de çok kaynak harcatır)

**Gemini Entegrasyonu:** Vertex AI için native `VertexAIInstrumentor` (OpenTelemetry tabanlı).

```python
# backend/app/services/langfuse_client.py
from langfuse import get_client
from openinference.instrumentation.vertexai import VertexAIInstrumentor

# Uygulama başlangıcında bir kez çağrılır (main.py)
def init_langfuse():
    VertexAIInstrumentor().instrument()
    # Otomatik olarak tüm Vertex AI / Gemini çağrıları izlenir
    # Prompt, response, token sayısı, latency → Langfuse'a gider

langfuse = get_client()
```

**Director'ın Langfuse ile yapacakları:**

```python
# 1. Her Gemini çağrısı otomatik olarak trace'e düşer (VertexAIInstrumentor)

# 2. Director analiz tamamlandığında trace'e kalite skoru ekler
langfuse.create_score(
    trace_id=s05_trace_id,   # S05 çağrısının trace ID'si
    name="clip_pass_rate",
    value=0.42,              # Bu job'da %42 pass rate
    data_type="NUMERIC",
    comment="Director analysis: 2026-03-24"
)

langfuse.create_score(
    trace_id=s06_trace_id,
    name="channel_dna_alignment",
    value=0.78,              # 0.0-1.0 arası
    data_type="NUMERIC"
)

# 3. Prompt Lab A/B testi için iki trace karşılaştırması
# Run A trace_id vs Run B trace_id → token kullanımı ve kalite farkı

# 4. Maliyet takibi için Langfuse API'sinden token toplamı çekilir
metrics = langfuse.get_model_usage(
    from_timestamp="2026-03-01",
    to_timestamp="2026-03-24"
)
# → {total_input_tokens, total_output_tokens, estimated_cost_usd}
```

**Langfuse Dashboard'da görünecekler:**
- Her S05 ve S06 çağrısı için trace (prompt → response → token sayısı → süre)
- Director'ın eklediği kalite skorları (pass_rate, channel_dna_alignment, hook_quality)
- Zaman bazlı token kullanım grafiği
- En pahalı çağrılar
- Retry yapılan çağrılar

**Çevre değişkenleri (Railway):**
```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

---

### 20.2 PostHog — Frontend Davranış Analitiği

**Neden:** Editor'da kullanıcı ne yapıyor? Caption oluşturuluyor mu, reframe çalıştırılıyor mu, export yapılıyor mu? Bu veriler Director'ın Modül 2 analizini besler.

**Kurulum:** PostHog Cloud (1 milyon event/ay ücretsiz)

**Next.js Entegrasyonu:**

```typescript
// opencut/apps/web/src/lib/posthog.ts
import posthog from 'posthog-js'

export function initPostHog() {
  posthog.init(process.env.NEXT_PUBLIC_POSTHOG_KEY!, {
    api_host: 'https://app.posthog.com',
    capture_pageview: false,  // Manuel kontrol
    persistence: 'localStorage'
  })
}

// Kullanım:
posthog.capture('reframe_triggered', {
  session_id: sessionId,
  has_diarization: Boolean(clipJobId),
  clip_duration_s: duration
})

posthog.capture('captions_generated', {
  session_id: sessionId,
  word_count: words.length,
  language: detectedLanguage
})

posthog.capture('editor_export_completed', {
  session_id: sessionId,
  had_reframe: reframeActive,
  had_captions: captionsActive,
  time_from_open_ms: Date.now() - sessionStartTime
})

posthog.capture('youtube_metadata_accepted', {
  title_changed: titleWasEdited,
  description_changed: descWasEdited
})
```

**Director PostHog API'sinden veri çeker:**

```python
# backend/app/director/analyzers/posthog_reader.py
import httpx

async def get_editor_metrics(days: int = 30) -> dict:
    """PostHog Query API üzerinden event verisi çeker"""
    response = await httpx.post(
        "https://app.posthog.com/api/projects/{project_id}/query/",
        headers={"Authorization": f"Bearer {POSTHOG_API_KEY}"},
        json={
            "query": {
                "kind": "EventsQuery",
                "event": "editor_export_completed",
                "properties": [],
                "dateRange": {"date_from": f"-{days}d"}
            }
        }
    )
    return response.json()
```

**Çevre değişkenleri (Vercel):**
```
NEXT_PUBLIC_POSTHOG_KEY=phc_...
NEXT_PUBLIC_POSTHOG_HOST=https://app.posthog.com
```

**PostHog Railway backend'e de eklenir:**
```python
# Önemli backend olayları için
from posthog import Posthog
posthog = Posthog(POSTHOG_API_KEY, host='https://app.posthog.com')

posthog.capture('anonymous', 'pipeline_completed', {
    'channel_id': channel_id,
    'pass_count': pass_count,
    'duration_ms': duration_ms
})
```

---

### 20.3 Sentry — Hata Takibi

**Neden:** Railway backend ve Vercel frontend'deki her hata otomatik yakalanır, stack trace ile. Director "bilinen hata kategorileri" bölümünü Sentry'den besler.

**Kurulum:** Sentry Cloud (5.000 hata/ay + 5M span ücretsiz — tek kullanıcı için fazlasıyla yeterli)

**Railway Backend Entegrasyonu:**

```python
# backend/app/main.py — en üste ekle
import sentry_sdk

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    traces_sample_rate=1.0,      # %100 transaction takibi
    profiles_sample_rate=0.2,    # %20 profiling (performans)
    environment=settings.ENVIRONMENT,
    release="prognot@1.0.0"
)
```

**Vercel Frontend Entegrasyonu:**

```typescript
// opencut/apps/web/src/lib/sentry.ts
import * as Sentry from "@sentry/nextjs"

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  tracesSampleRate: 0.5,
  environment: process.env.NODE_ENV
})
```

**Director'ın Sentry ile entegrasyonu:**

```python
# Director analiz sırasında Sentry Issues API'den son hataları çeker
async def get_recent_errors(days: int = 7) -> list:
    response = await httpx.get(
        f"https://sentry.io/api/0/projects/{ORG}/{PROJECT}/issues/",
        headers={"Authorization": f"Bearer {SENTRY_AUTH_TOKEN}"},
        params={"query": "is:unresolved", "statsPeriod": f"{days}d"}
    )
    issues = response.json()
    # Director'a dönen: [{title, count, firstSeen, lastSeen, culprit}]
    return issues
```

Director analizinde "Teknik Sağlık" boyutu Sentry'deki açık hata sayısından etkilenir.

**Çevre değişkenleri:**
```
# Railway
SENTRY_DSN=https://xxx@o123.ingest.sentry.io/456
SENTRY_AUTH_TOKEN=sntrys_...   # Director API erişimi için

# Vercel
NEXT_PUBLIC_SENTRY_DSN=https://xxx@o123.ingest.sentry.io/456
```

---

### 20.4 Araçlar Arasındaki İş Bölümü

```
Olay                          Langfuse   PostHog    Sentry     Supabase
─────────────────────────────────────────────────────────────────────────
Gemini API çağrısı               ✓          -          -          -
Gemini token kullanımı           ✓          -          -          -
Director kalite skoru            ✓          -          -          ✓
Backend exception                -          -          ✓          -
Pipeline adım süresi             -          -          -          ✓
Reframe tetiklendi               -          ✓          -          ✓
Caption oluşturuldu              -          ✓          -          ✓
Editor export                    -          ✓          -          ✓
Frontend exception               -          -          ✓          -
Kullanıcı klip onayı             -          -          -          ✓
Kanal DNA güncellemesi           -          -          -          ✓
```

---

## 21. YAYINLAMA PLANI VE ÖNCELİK SIRASI

### Faz 1 — Temel Altyapı + Dış Araçlar
1. **Sentry** kurulumu (Railway backend + Vercel frontend) — 30 dakika
2. **Langfuse Cloud** hesabı + VertexAIInstrumentor entegrasyonu — 1 saat
3. **PostHog Cloud** hesabı + Next.js snippet — 30 dakika
4. `director_events` tablosu ve base_collector.py
5. Modül 1 event hook'ları (S05 ve S06 en kritik)
6. Sayısal metrik hesaplayıcı (scorer.py — Gemini yok)
7. Basit dashboard: ham metrikler tablosu

### Faz 2 — Analiz Zinciri
8. Gemini analiz zinciri (2 çağrı ile başla, Flash)
9. `director_analyses` ve `director_recommendations` tabloları
10. Director → Langfuse score yazma entegrasyonu
11. Director → Sentry Issues okuma entegrasyonu
12. Dashboard'a puan kartları ve öneri listesi

### Faz 3 — Test Sistemi
13. Modül 1 E2E test runner
14. Modül 2 test suite (reframe + captions)
15. PostHog event verisi → Director modül 2 analizi
16. Test dashboard sayfası

### Faz 4 — İleri Özellikler
17. Semantik hafıza (pgvector embedding)
18. Cross-module köprüsü
19. Prompt Lab
20. İnternet araştırması (Gemini grounding)
21. Director kendi kendini değerlendirme
22. Langfuse Prompt Management entegrasyonu (prompt versiyonlama)

---

*Bu döküman Director modülünün geliştirme planıdır. Faz 1 tamamlandığında bu döküman geliştirme notu olarak güncellenir. Her yeni modül eklendiğinde Bölüm 19'daki protokol izlenir.*
