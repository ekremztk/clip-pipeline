# PROGNOT CLIP PIPELINE — AI ANAYASASI
> **Bu dosyayı her yeni AI konuşmasının başında `@CLAUDE.md` ile sisteme ekle.**
> Son güncelleme: Mart 2026 | Versiyon: 3.1 (Intelligence Engine Geçişi)

---
## 0. AKTİF MCP ARAÇLARI
- GitHub MCP: Repo işlemleri için kullan
- Supabase MCP: DB sorguları için kullan  
- Context7: Kütüphane dokümantasyonu için "use context7" yaz
- Sequential Thinking: Büyük mimari kararlar için kullan "Bu mimari kararı sequential thinking ile analiz et" komutu çalıştır"

---

## 1. PROJENİN KİMLİĞİ

**Prognot Clip Pipeline**, uzun formatlı yatay videoları (podcast, talk-show, röportaj)
5 katmanlı Channel Intelligence Engine ile analiz edip, viral potansiyeli en
yüksek kesitleri kalite kaybı olmadan (lossless) kesen **tam otomatik, tek kullanıcılı**
kişisel bir endüstriyel sistemdir.

| Alan | Değer |
|------|-------|
| **Sahibi** | Ekrem (tek kullanıcı, kişisel sistem) |
| **Hedef** | Kendi YouTube kanalları için viral klip üretimi |
| **Deployment** | Railway (backend) + Vercel (frontend) + Supabase (DB) |
| **Geliştirme ortamı** | Antigravity IDE + GitHub (main branch) |
| **CI/CD** | `git push` → Railway ve Vercel otomatik deploy alır |
| **Mimari Versiyon** | V3.1 — Channel Intelligence Engine (RAG → 5 Katman geçişi) |

---

## 2. AKTİF MODÜLLER

| Modül | Durum | Açıklama |
|-------|-------|----------|
| **Modül 1 — Klip Çıkartıcı** | ✅ AKTİF | Tek odak. Video analizi + hassas kesim |
| **V3.1 Intelligence Engine** | 🔄 GELİŞTİRİLİYOR | 5 katmanlı kapalı döngü sistemi |
| **Modül 2 — Dikey Format** | ⏸️ SÜRESİZ ASKIDA | 9:16 reframe + altyazı — dokunma |
| **Modül 3+** | 🔮 TANIMLANMADI | Gelecekte bağımsız modül olarak eklenecek |

> ⛔ `reframer.py` ve `subtitler.py` dosyalarına **hiçbir koşulda dokunma.**
> Modül 2 ile ilgili hiçbir geliştirme önerme, yapma veya test etme.

---

## 3. MODÜL 1 — PIPELINE AKIŞI

### Mevcut Çalışan Akış (V3.0)

```
[Frontend — Next.js / Vercel]
    │  MP4 upload + video_title + description + channel_id
    ▼
[Backend — FastAPI / Railway — CPU Only, 8GB RAM]
    │
    ├─ Adım 1: Audio Extract      FFmpeg subprocess   (MP4 → M4A)
    ├─ Adım 2: Transcribe         Groq Whisper        (word-level timestamps)
    ├─ Adım 3: Energy Analysis    Librosa             (desibel/enerji haritası)
    ├─ Adım 4: RAG Query          Supabase pgvector   (channel_id filtreli)
    ├─ Adım 5: AI Analysis        Gemini 2.5 Flash    (ses + transkript + enerji + RAG → JSON)
    ├─ Adım 6: Schema Validation  Regex + Python      (JSON temizle, skor filtresi)
    ├─ Adım 7: Precision Cut      PySceneDetect+FFmpeg (sahne snap + lossless cut)
    └─ Adım 8: Cleanup            os.remove()         (geçici MP4, M4A — zorunlu)
    │
    ▼
[Supabase]
    ├─ jobs tablosu    → iş durumu
    ├─ clips tablosu   → klip metadata
    └─ viral_library   → RAG hafızası
```

### V3.1 Hedef Akış (Geliştirme sürecinde aşamalı geçiş)

```
[Frontend — Next.js / Vercel]
    │  MP4 upload + video_title + description + channel_id
    ▼
[Backend — FastAPI / Railway — CPU Only, 8GB RAM]
    │
    ├─ Adım 1:   Audio Extract      FFmpeg subprocess       (MP4 → M4A)
    ├─ Adım 2:   Transcribe         Groq Whisper            (word-level timestamps)
    │             └─ Kalite Kontrol  segment/word oranı      (E5)
    ├─ Adım 3:   Energy Analysis    Librosa                 (enerji haritası + pencere bazlı)
    │             └─ Chunked         5dk bloklar + gc.collect (E23)
    ├─ Adım 3.5: Genome Load        genome.py               (K0 — kanal DNA'sı)
    ├─ Adım 3.6: Correlation Load   correlation.py          (K1 — kalibre ağırlıklar)
    ├─ Adım 3.7: Segment Scoring    scorer.py               (K2 — matematiksel ön eleme)
    │             ├─ Coarse Scan     30s pencereler → dinamik cutoff
    │             └─ Fine Scan       5s pencereler → puanlama
    │                 ├─ < 60 puan   → ELENİR (Gemini görmez)
    │                 └─ ≥ 60 puan   → Gemini'ye gönderilir
    ├─ Adım 4:   AI Analysis        Gemini 2.5 Flash        (K3 — hakem rolünde)
    │             ├─ Hook anatomy    JSON yapısal ayrıştırma
    │             ├─ Enum kontrol    content_type + pattern_id
    │             ├─ Anti-Fatigue    son 10 klip çeşitlilik kontrolü
    │             └─ Decision log    karar denetim izi
    ├─ Adım 5:   Schema Validation  Regex + Python + overlap check
    ├─ Adım 6:   Precision Cut      PySceneDetect + FFmpeg  (sahne snap + lossless)
    ├─ Adım 7:   Cleanup            os.remove()             (geçici dosyalar — zorunlu)
    │
    └─ Post-Pipeline:
        ├─ 48h → Ön sinyal          feedback.py             (K4 — spike mı?)
        ├─ 7d  → Kesin etiket       feedback.py             (K4 — tier belirleme)
        ├─ Korelasyon güncelleme     correlation.py          (K1 güncelle)
        ├─ Genome güncelleme         genome.py               (K0 güncelle, versiyonlu)
        └─ Sağlık kontrolü           health.py               (K5 — haftalık rapor)
    │
    ▼
[Supabase — 7 Tablo]
    ├─ jobs tablosu           → iş durumu
    ├─ clips tablosu          → klip metadata + decision_log + feedback_status
    ├─ viral_library          → genişletilmiş RAG hafızası (22+ alan)
    ├─ channel_genome         → kanal DNA'sı (versiyonlu)      (YENİ)
    ├─ correlation_rules      → sinyal ağırlıkları + drift      (YENİ)
    ├─ celebrity_registry     → ünlü tanıma + multiplier        (YENİ)
    └─ channels               → kanal izolasyonu
```

### Fallback Zinciri

| Adım | Hata Durumu | Fallback |
|------|-------------|----------|
| Transcribe (Groq) | API hatası / timeout | `transcript_text = ""` — Gemini ses analizi yeterli |
| Energy Analysis | Import / dosya hatası | `energy_summary = ""` ile devam |
| Genome Load | DB hatası / genome yok | `genome_data = {}` — varsayılan parametreler |
| Correlation Load | DB hatası / kural yok | `DEFAULT_SIGNAL_WEIGHTS` kullan (hardcoded fallback) |
| Segment Scoring | Scorer hatası | `scored_segments = None` — Gemini tam analiz yapar |
| RAG Query | DB bağlantı hatası | `"Referans bulunamadı, genel viral kurallarını uygula."` |
| Gemini Analiz | Timeout / 429 | 3 deneme, 30s bekleme; tümü başarısız → `RuntimeError` |
| JSON Parse | Bozuk JSON | `re.sub` ile temizle, tekrar parse; başarısız → `[]` |
| Hook Anatomy | Gemini döndürmedi | Default değerlerle doldur (validate_clips) |
| Precision Cut | PySceneDetect hatası | Snap olmadan doğrudan FFmpeg ile kes |
| Cleanup | Dosya zaten silinmiş | `if os.path.exists()` kontrolü — hata fırlatma |

---

## 4. V3.1 INTELLIGENCE ENGINE — 5 KATMAN

### Katman Özeti

| Katman | Dosya | Görev | Durum |
|--------|-------|-------|-------|
| **K0 — Kanal Genomu** | `genome.py` | Kanalın DNA'sını çıkar: tier eşikleri, golden_duration, içerik ağırlıkları | 🔄 Geliştiriliyor |
| **K1 — Korelasyon Matrisi** | `correlation.py` | Hangi hook tipi, fiil yapısı, içerik paterni çalışıyor? | 🔄 Geliştiriliyor |
| **K2 — Segment Skorlama** | `scorer.py` | Gemini'den ÖNCE matematiksel ön eleme (coarse + fine scan) | 🔄 Geliştiriliyor |
| **K3 — Gemini Karar Motoru** | `analyzer.py` | Gemini artık editör değil, hakem. K0-K2 verileriyle zenginleştirilmiş prompt | 🔄 Revize edilecek |
| **K4 — Bileşik Öğrenme** | `feedback.py` | 48h/7d feedback toplama, sinyal doğruluk analizi, genome güncelleme | 🔄 Geliştiriliyor |
| **K5 — Genome Sağlığı** | `health.py` | Sistemi izleyen sistem. Override oranı, drift, sinyal doğruluk raporu | 🔄 Geliştiriliyor |

### Enum Listeleri (Tüm Sistemde Sabit — correlation.py'da Tanımlı)

```python
CONTENT_TYPES = [
    "celebrity_conflict", "hot_take", "funny_reaction",
    "emotional_reveal", "unexpected_answer", "relatable_moment",
    "controversial_opinion", "storytelling", "educational_insight"
]

PATTERN_IDS = [
    "celebrity_conflict_reveal", "question_hook",
    "physical_action_hook", "number_stat_hook",
    "emotional_reveal_hook", "controversy_hook"
]

DEFAULT_SIGNAL_WEIGHTS = {
    "wpm": 0.10, "has_question": 0.15, "has_exclamation": 0.10,
    "speaker_change": 0.10, "celebrity_name": 0.20,
    "rms_level": 0.05, "rms_spike": 0.10, "silence_before": 0.05,
    "duration_in_golden_zone": 0.10, "content_type_weight": 0.05
}
```

> ⚠️ Bu listeler correlation.py'da TANIMLANIR. Başka dosyalarda kullanırken `from correlation import CONTENT_TYPES` ile import et. HARDCODE ETME.

### V3.1 API Endpoint'leri (Yeni — /v2/ prefix)

| Endpoint | Method | Açıklama |
|----------|--------|----------|
| `/v2/genome/{channel_id}` | GET | Genome verisi (versiyonlu) |
| `/v2/genome/{channel_id}/recalculate` | POST | Genome yeniden hesapla |
| `/v2/genome/{channel_id}/rollback/{version_id}` | POST | Genome rollback |
| `/v2/feedback/{clip_id}` | POST | Klip performans verisi (validated) |
| `/v2/feedback/bulk-import` | POST | Toplu CSV/JSON feedback import |
| `/v2/correlation/{channel_id}` | GET | Korelasyon matrisi + kalibre ağırlıklar |
| `/v2/health/{channel_id}` | GET | Genome sağlık raporu |
| `/v2/celebrity-registry` | GET/POST | Celebrity listesi yönetimi |

> ⚠️ Yeni endpoint'ler `/v2/` prefix'i kullanır. Mevcut endpoint'ler (`/upload`, `/status`, `/feedback`, `/jobs`) DEĞİŞMEZ.
> Frontend proxy: `next.config.js` → `/api/backend/:path*` üzerinden Railway'e yönlendiriliyor. Yeni endpoint'ler frontend'den `/api/backend/v2/genome/...` olarak çağrılır.

---

## 5. KANAL SİSTEMİ

Her YouTube kanalı için **tam izolasyon**: ayrı RAG verisi, ayrı Gemini prompt'u, ayrı Genome, ayrı korelasyon kuralları.
Kanallar birbirinin verisini hiçbir zaman görmez.

### Mevcut Kanallar

| channel_id | Kanal Adı | Config Dosyası | Durum |
|------------|-----------|----------------|-------|
| `speedy_cast` | Speedy Cast Clip | `backend/channels/speedy_cast/config.py` | ✅ Aktif |

### İzolasyon Prensibi

```
Speedy Cast                    Kadın Podcast (örnek)
─────────────────              ──────────────────────
channel_genome                 channel_genome
WHERE channel_id               WHERE channel_id
= 'speedy_cast'                = 'women_podcast'
       ↓                              ↓
correlation_rules              correlation_rules
WHERE channel_id               WHERE channel_id
= 'speedy_cast'                = 'women_podcast'
       ↓                              ↓
viral_library                  viral_library
WHERE channel_id               WHERE channel_id
= 'speedy_cast'                = 'women_podcast'
       ↓                              ↓
speedy_cast/config.py          women_podcast/config.py
       ↓                              ↓
   Klipler A                      Klipler B
```

### Yeni Kanal Eklerken Kontrol Listesi

- [ ] `backend/channels/{kanal_id}/config.py` oluştur
- [ ] Supabase `channels` tablosuna kayıt ekle
- [ ] `viral_library`'e `channel_id` doldurulmuş referans verileri ekle
- [ ] `channel_genome`'a ilk bootstrap genome kaydı ekle
- [ ] Frontend `CHANNELS` listesine ekle (`page.tsx`)
- [ ] `docs/CHANNELS.md` dokümantasyonunu güncelle

---

## 6. TECH STACK

### Backend (Railway — CPU ONLY)

```
Python 3.11
FastAPI + Uvicorn
FFmpeg (subprocess)       → Audio extraction, video cutting
Librosa                   → Ses enerji analizi (CPU, sr=16000)
PySceneDetect (OpenCV)    → Sahne geçişi tespiti (CPU)
psycopg2-binary           → PostgreSQL bağlantısı
Groq API                  → Whisper large-v3 (word-level timestamps)
Google Genai SDK          → Gemini 2.5 Flash (JSON mode)
reportlab                 → PDF rapor üretimi
```

### Frontend & Altyapı

```
Next.js 16.1.6 / TypeScript / Tailwind CSS 3.4   → Vercel
  ⚠️ Node.js >= 20.9.0 ZORUNLU (Next.js 16 gereksinimi)
Supabase (PostgreSQL + pgvector)                  → RAG veritabanı + Intelligence Engine
gemini-embedding-001                              → 3072 boyutlu vektör (!)
```

---

## 7. KRİTİK DOSYA HARİTASI

```
clip-pipeline/
├── CLAUDE.md
├── README.md
├── Dockerfile                       (COPY backend/ .)
├── railway.json
├── docs/
│   └── CHANNELS.md
│
├── backend/
│   ├── main.py                      FastAPI endpoints + StaticFiles + V2 endpoints
│   ├── pipeline.py                  Ana iş akışı (K0-K2 adımları ekleniyor)
│   ├── analyzer.py                  Gemini K3 hakem (prompt revize edilecek)
│   ├── cutter.py                    PySceneDetect + FFmpeg
│   ├── transcriber.py               Groq Whisper
│   ├── audio_analyzer.py            Librosa enerji analizi (pencere bazlı çıktı)
│   ├── database.py                  Supabase CRUD (7 tablo)
│   ├── state.py                     In-memory job tracking (DB fallback)
│   ├── report_builder.py
│   ├── metadata.py
│   ├── pdf_reporter.py
│   ├── requirements.txt
│   ├── .env                         (git'e gitmiyor)
│   │
│   ├── genome.py                    K0 Kanal Genomu (YENİ — V3.1)
│   ├── correlation.py               K1 Korelasyon Matrisi + Enum listeleri (YENİ — V3.1)
│   ├── scorer.py                    K2 Segment Skorlama (YENİ — V3.1)
│   ├── feedback.py                  K4 Bileşik Öğrenme (YENİ — V3.1)
│   ├── health.py                    K5 Genome Sağlığı (YENİ — V3.1)
│   │
│   ├── channels/
│   │   ├── channel_registry.py
│   │   ├── speedy_cast/
│   │   │   └── config.py
│   │   └── {yeni_kanal}/
│   │       └── config.py
│   │
│   ├── tools/
│   │   └── channel_hunter.py        Viral DNA toplama (manuel script)
│   │
│   └── output/                      (git'e gitmiyor)
│       └── {job_id}/
│           ├── clip_01.mp4
│           ├── clip_02.mp4
│           ├── clip_03.mp4
│           ├── metadata.txt
│           └── report.pdf
│
└── frontend/
    ├── app/page.tsx                  UI + Feedback + Genome Dashboard + Health Monitor
    ├── next.config.js                /api/backend/* → Railway proxy
    └── tailwind.config.js
```

---

## 8. ORTAM DEĞİŞKENLERİ

### Railway (Backend)

```env
GEMINI_API_KEY=
GROQ_API_KEY=
SUPABASE_URL=            # https://xxx.supabase.co
SUPABASE_SERVICE_KEY=    # service_role key (RLS bypass)
DATABASE_URL=            # postgresql://...@xxx.supabase.co:6543/postgres
                         # ⚠️ PORT MUTLAKA 6543 OLMALI (Supabase Connection Pooler)
                         # 5432 Railway/Docker içinden erişilemez — Network unreachable hatası
FRONTEND_URL=            # https://xxx.vercel.app

# V3.1 — Opsiyonel
DISCORD_WEBHOOK_URL=     # K5 sağlık raporları için (opsiyonel)
GENOME_RECALC_INTERVAL=50  # Kaç feedback'te bir genome yeniden hesaplansın
FEEDBACK_AUTO_MODE=manual  # manual | csv | api
```

### Vercel (Frontend)

```env
NEXT_PUBLIC_API_URL=     # https://xxx.railway.app
```

---

## 9. VERİTABANI ŞEMASI

> ⚠️ **`embedding vector(3072)`** — gemini-embedding-001'in gerçek çıktı boyutu.
> 768 veya başka değer kullanırsan boyut uyuşmazlığı hatası alırsın.

### Mevcut Tablolar (V3.0)

```sql
CREATE TABLE channels (
  id                  TEXT PRIMARY KEY,
  display_name        TEXT,
  description         TEXT,
  min_virality_score  INT DEFAULT 80,
  max_clip_duration   INT DEFAULT 35,
  created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE jobs (
  id            TEXT PRIMARY KEY,
  status        TEXT,           -- 'running' | 'done' | 'error'
  step          TEXT,
  progress      INT,
  video_title   TEXT,
  channel_id    TEXT REFERENCES channels(id),
  error_message TEXT,
  metadata_path TEXT,
  pdf_path      TEXT,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE clips (
  id                    SERIAL PRIMARY KEY,
  job_id                TEXT REFERENCES jobs(id),
  channel_id            TEXT,
  hook                  TEXT,
  score                 INT,
  path                  TEXT,
  psychological_trigger TEXT,
  rag_reference_used    TEXT,
  suggested_title       TEXT,
  suggested_description TEXT,
  suggested_hashtags    TEXT,
  why_selected          TEXT,
  views                 INT,
  retention             FLOAT,
  swipe_rate            FLOAT,
  feedback_score        FLOAT,
  -- V3.1 Yeni Kolonlar:
  views_48h             INT,
  views_7d              INT,
  growth_type           TEXT,
  feedback_status       TEXT DEFAULT 'pending',
  decision_log          JSONB,
  created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE viral_library (
  id                SERIAL PRIMARY KEY,
  channel_id        TEXT NOT NULL,
  title             TEXT,
  hook_text         TEXT,
  why_it_went_viral TEXT,
  content_pattern   TEXT,
  viral_score       INT,
  embedding         vector(3072),
  -- V3.1 Yeni Kolonlar:
  hook_anatomy            JSONB,
  content_type            TEXT,
  segment_scores          JSONB,
  genome_tier_predicted   INT,
  genome_tier_actual      INT,
  views_48h               INT,
  views_7d                INT,
  growth_type             TEXT,
  avg_watch_pct           FLOAT,
  first_3s_retention      FLOAT,
  swipe_away_rate         FLOAT,
  is_successful           BOOLEAN,
  is_proxy                BOOLEAN DEFAULT false,
  signal_accuracy         JSONB,
  override_flag           BOOLEAN DEFAULT false,
  why_failed              TEXT,
  feedback_status         TEXT DEFAULT 'pending',
  embedding_model         TEXT DEFAULT 'gemini-embedding-001',
  created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON viral_library
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

### V3.1 Yeni Tablolar

```sql
CREATE TABLE channel_genome (
  id                      SERIAL PRIMARY KEY,
  channel_id              TEXT NOT NULL REFERENCES channels(id),
  version_id              INT NOT NULL DEFAULT 1,
  is_active               BOOLEAN DEFAULT true,
  mode                    TEXT DEFAULT 'bootstrap',  -- bootstrap | real | proxy
  tier_thresholds         JSONB,
  golden_duration         JSONB,
  golden_duration_by_type JSONB DEFAULT '{}',
  content_type_weights    JSONB DEFAULT '{}',
  growth_type_distribution JSONB DEFAULT '{}',
  growth_type_thresholds  JSONB,
  proxy_config            JSONB,
  total_clips_analyzed    INT DEFAULT 0,
  avg_views               INT DEFAULT 0,
  calculated_at           TIMESTAMPTZ DEFAULT NOW(),
  created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_genome_active ON channel_genome(channel_id, is_active)
WHERE is_active = true;

CREATE TABLE correlation_rules (
  id               SERIAL PRIMARY KEY,
  channel_id       TEXT NOT NULL REFERENCES channels(id),
  rule_type        TEXT NOT NULL,     -- hook_pattern | content_type | signal_weight
  rule_key         TEXT NOT NULL,     -- celebrity_conflict_reveal | celebrity_name vb.
  tier4_plus_rate  FLOAT DEFAULT 0,
  average_rate     FLOAT DEFAULT 0,
  sample_count     INT DEFAULT 0,
  weight           FLOAT DEFAULT 1.0,
  is_active        BOOLEAN DEFAULT true,
  drift_confidence FLOAT DEFAULT 0,
  last_30d_rate    FLOAT,
  last_90d_rate    FLOAT,
  updated_at       TIMESTAMPTZ DEFAULT NOW(),
  created_at       TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(channel_id, rule_type, rule_key)
);

CREATE TABLE celebrity_registry (
  id          SERIAL PRIMARY KEY,
  name        TEXT UNIQUE NOT NULL,
  tier        TEXT DEFAULT 'unknown',    -- A, B, C, niche, unknown
  multiplier  FLOAT DEFAULT 1.0,
  aliases     TEXT[],
  channel_id  TEXT,                      -- NULL = global, set = kanala özel
  created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 10. DEMİR KURALLAR

### GPU Yasağı — Mutlak

```
❌ PyTorch, TensorFlow, transformers
❌ WhisperX (lokal) — CPU'da Mac'i yakıyor, Railway'de çalışmıyor
❌ Herhangi bir lokal AI modeli
✅ FFmpeg subprocess, OpenCV, PySceneDetect, Librosa (hepsi CPU)
✅ API tabanlı her şey (Groq, Gemini)
```

### Hata Toleransı — Her Fonksiyonda Zorunlu

```python
# ✅ DOĞRU
try:
    result = risky_operation()
except Exception as e:
    print(f"[ModulAdi] ⚠️ Hata: {e}")
    result = fallback_value

# ❌ YANLIŞ — pipeline çöker
result = risky_operation()
```

### Geçici Dosya Temizliği — `finally` Zorunlu

```python
finally:
    for path in [audio_path, local_mp4_path]:
        if os.path.exists(path):
            os.remove(path)
```

### Gemini Prompt'larında `.format()` Yasak

```python
# ❌ YANLIŞ — JSON süslü parantezleriyle çakışır
prompt = "Return: {{'key': 'value'}}".format(title=x)

# ✅ DOĞRU
prompt = "Return: {'key': 'value'}"
prompt = prompt.replace("TITLE_PLACEHOLDER", x)
```

### Klip Süresi — İki Katmanlı Koruma

```python
# analyzer.py — prompt + kod seviyesi
MAX_CLIP_DURATION = 35   # saniye
MIN_CLIP_DURATION = 15

# cutter.py — son güvenlik ağı
MAX_TOTAL = 39           # 35s + 2s padding + tolerans
```

### V3.1 Kuralları

```
⚠️ sr=16000 DEĞİŞTİRME (audio_analyzer.py)
   → Peak zamanlamaları bozulur, mevcut pipeline kırılır

⚠️ Yeni endpoint'ler /v2/ prefix'i ile
   → Mevcut endpoint'lerle (/upload, /feedback, /status) çakışma YASAK

⚠️ CONTENT_TYPES ve PATTERN_IDS — correlation.py'da tanımlı
   → Başka dosyalarda import et, HARDCODE ETME

⚠️ Genome versiyonlama — save öncesi eski versiyon is_active: false
   → Versiyonsuz güncelleme YASAK (rollback imkanı kalkar)

⚠️ Sıfıra bölme koruması — views_7d == 0 kontrolü
   → growth_type hesabında ZeroDivisionError riski

⚠️ Webhook için urllib.request kullan
   → requests kütüphanesi requirements.txt'te YOK
```

### Scope Disiplini

Yeni özellik veya büyük mantık değişikliği öncesinde mimari plan sun, onay al.
İstenmeyen şey ekleme. Tek PR = tek konu.

---

## 11. KLİP PARAMETRELERİ

```python
MAX_CLIP_DURATION   = 35   # saniye
MIN_CLIP_DURATION   = 15
MIN_VIRALITY_SCORE  = 80   # altındakiler reddedilir
CLIPS_PER_VIDEO     = 3
CRF_QUALITY         = 18   # FFmpeg (18 = görsel kayıpsız)
FFMPEG_THREADS      = 0    # 0 = tüm CPU çekirdekleri
MIN_VIDEO_DURATION  = 60   # V3.1: 60s altı videolar reddedilir
```

---

## 12. BİLİNEN SORUNLAR & ÇÖZÜMLER

| # | Sorun | Kök Neden | Çözüm |
|---|-------|-----------|-------|
| 1 | `Network is unreachable` (Supabase) | Railway/Docker port 5432'ye çıkamıyor | `DATABASE_URL` portunu **6543** yap (Connection Pooler) |
| 2 | `/output/clip_01.mp4` → 404 | `main.py`'da `StaticFiles` mount eksik | `app.mount("/output", StaticFiles(directory="output"), name="output")` ekle |
| 3 | Gemini JSON parse hatası | Cevap kontrol karakteri içeriyor | `re.sub(r'[\x00-\x1f]', '', raw)` ile temizle |
| 4 | Gemini rate limit (429) | Kota aşımı | 3 deneme: 1-2. denemede 30s, 3.'de 60s bekle |
| 5 | Gemini Files API ACTIVE bekleme | Büyük dosya henüz işlenmedi | <20MB → inline bytes; >20MB → Files API + `time.sleep(8)` |
| 6 | Docker rebuild 20 dk | Requirements her build'de yeniden kuruluyor | `requirements.txt` COPY'sini kod COPY'sinden önce yap |
| 7 | yt-dlp format error Railway | Docker'daki yt-dlp versiyonu eski | `Dockerfile`'a `RUN pip install -U yt-dlp` ekle |
| 8 | Embedding boyut uyuşmazlığı | Tablo `vector(768)`, model `3072` üretiyor | Tabloyu `vector(3072)` ile yeniden oluştur |
| 9 | WhisperX CPU çökmesi | Lokal model GPU olmadan çalışamaz | Groq API kullan, lokal model yasak |
| 10 | ZeroDivisionError (V3.1) | `views_7d = 0` iken growth_type hesabı | `if views_7d == 0: growth_type = 'unknown'` |
| 11 | KeyError: 'hook_anatomy' (V3.1) | Gemini bu alanı döndürmedi | `validate_clips`'te default değer kontrolü |
| 12 | Endpoint çakışma (V3.1) | Eski `/feedback` ile yeni `/v2/feedback` | Yeni endpoint'ler `/v2/` prefix'i kullanır |
| 13 | Node.js versiyon hatası | Next.js 16.1.6 → Node >= 20.9.0 gerekli | `node --version` kontrol, güncelle |
| 14 | ModuleNotFoundError: 'requests' | requirements.txt'te yok | `urllib.request` kullan (built-in) |

---

## 13. MİMARİ KARAR GEÇMİŞİ

| Karar | Alternatif | Neden Seçilmedi |
|-------|------------|-----------------|
| Groq Whisper API | WhisperX lokal | GPU gerektirir, CPU'da çalışmıyor |
| Gemini 2.5 Flash | GPT-4, Claude API | Google AI Studio ücretsiz tier yeterli |
| PySceneDetect | ML tabanlı sahne tespiti | GPU gerektirir |
| FFmpeg subprocess | Python FFmpeg kütüphanesi | Subprocess daha fazla flag esnekliği |
| Supabase pgvector | Pinecone, Weaviate | Zaten Supabase kullanıyoruz, ekstra servis gereksiz |
| Port 6543 (Pooler) | Port 5432 (Direct) | 5432 Railway/Docker içinden erişilemiyor |
| Gemini NER (V3.1) | spaCy | spaCy ~500MB RAM, Railway'de ağır. Gemini zaten transkripti görüyor |
| /v2/ prefix (V3.1) | Mevcut endpoint'leri değiştir | Geriye uyumluluk — mevcut frontend bozulmaz |
| sr=16000 koru (V3.1) | sr=22050'ye geç | Peak zamanlamaları kayar, mevcut pipeline kırılır |
| urllib.request (V3.1) | requests kütüphanesi | requirements.txt'e ek paket eklemek yasak |

---

## 14. ANTİ-PATTERN'LER (Tekrar Önerme)

| Anti-Pattern | Ne Oldu | Doğrusu |
|-------------|---------|---------|
| `subtitler.py` rewrite önerisi | Kapsam dışı başlatıldı, yarıda durduruldu | Modül 2 askıda — dokunma |
| `0` Gemini'ye literal geçmek | "auto" mod yerine sıfır aldı, hata | `None` veya `"auto"` geç |
| channel_id'siz `viral_library` | Tüm kanal verileri karıştı | Her sorgu `WHERE channel_id = ?` zorunlu |
| `vector(768)` | gemini-embedding-001 gerçekte 3072 üretiyor | `vector(3072)` kullan |
| Browser extension VPN | Sadece tarayıcıyı yönlendiriyor | Sistem genelinde VPN gerekli (subprocess dahil) |
| sr=22050 önerisi (V3.1) | Peak zamanlamaları kayar | sr=16000 KORU, değiştirme |
| /api/feedback yeni endpoint (V3.1) | Mevcut /feedback ile çakışır | /v2/ prefix kullan |
| CONTENT_TYPES hardcode (V3.1) | Her dosyada farklı liste oluşur | correlation.py'dan import et |

---

## 15. GELİŞTİRME ÖNCELİKLERİ (Güncel Backlog — V3.1)

```
1. ✅ viral_library channel_id kolonu (YAPILDI)
2. ✅ channels/ yapısı kuruldu (YAPILDI)
3. ✅ analyzer.py channel_id parametresi (YAPILDI)
4. ✅ Frontend kanal seçim dropdown (YAPILDI)
5. ✅ DATABASE_URL port 6543 (YAPILDI)
6. ✅ StaticFiles mount (YAPILDI)
7. ✅ Dockerfile layer caching (YAPILDI)
8. ✅ Librosa entegrasyonu (YAPILDI)

── V3.1 Intelligence Engine Geçişi ──────────────────
9.  🔄 B1: Supabase migrasyonları (3 yeni tablo + ALTER TABLE)
10. 🔄 B2: Backend iskeletleri (genome, correlation, scorer, feedback, health)
11. 🔄 B3: Mevcut dosya güncellemeleri (pipeline, analyzer, audio_analyzer, main, database)
12. 🔄 B4: Frontend (Feedback UI, Genome Dashboard, Health Monitor)
13. 🔄 B5: Test, Deploy, CLAUDE.md V4.0 Final
```

---

## 16. YASAK KONULAR

```
⛔ Modül 2 geliştirmesi (dikey format, reframe, altyazı)
⛔ reframer.py veya subtitler.py'ye dokunmak
⛔ GPU kütüphanesi önermek veya eklemek
⛔ vector(768) boyutu önermek
⛔ Pipeline akışını onay almadan değiştirmek
⛔ Kapsam dışı özellik eklemek
⛔ sr=16000 değiştirmek (audio_analyzer.py)
⛔ Mevcut endpoint'leri (/upload, /feedback, /status) değiştirmek
⛔ requirements.txt'e yeni paket eklemek
⛔ CONTENT_TYPES veya PATTERN_IDS listelerini hardcode etmek
```