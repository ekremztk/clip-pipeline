# SİSTEM CORE — Altyapı, Servisler ve Veri Katmanı
> Son güncelleme: 2026-03-24

Bu döküman, tüm modüllerin üzerine inşa edildiği temel sistem bileşenlerini kapsar: veritabanı şeması, API katmanı, servisler, deployment, kanal yönetimi ve feedback döngüsü.

---

## 1. DEPLOYMENT MİMARİSİ

```
┌─────────────────────────────────────────────────────────────────┐
│  Kullanıcı                                                       │
│    ↕ HTTPS                                                       │
│  Vercel (Frontend — Next.js)                                     │
│    ↕ NEXT_PUBLIC_API_URL (proxy via next.config.js)              │
│  Railway (Backend — FastAPI + Docker)                           │
│    ↕ Port 6543                                                   │
│  Supabase (PostgreSQL + pgvector)                               │
│    ↕ boto3                                                       │
│  Cloudflare R2 (Video depolama)                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Railway (Backend)
- Docker container (CPU-only, 8GB RAM)
- Python FastAPI + Uvicorn
- FFmpeg kurulu (Dockerfile'da)
- Procfile: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Deployment: `git push origin main` → otomatik deploy

### Vercel (Frontend)
- Next.js App Router
- `next.config.js` proxy → Railway URL'ye yönlendirir (**değiştirme**)
- Deployment: `git push origin main` → otomatik deploy

### Supabase
- PostgreSQL + pgvector eklentisi
- **Port: 6543** (Connection Pooler) — 5432 Railway'den erişilemez
- RLS (Row Level Security) tablolarda aktif
- Migrations Supabase dashboard üzerinden uygulanır

### Cloudflare R2
- S3-uyumlu nesne depolama
- Bucket: `{R2_BUCKET_NAME}`
- Public URL: `https://pub-xxxxx.r2.dev`
- Endpoint: `https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com`

---

## 2. VERİTABANI ŞEMASI

### 2.1 `jobs` Tablosu

```sql
CREATE TABLE jobs (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  channel_id        TEXT NOT NULL,
  video_title       TEXT,
  guest_name        TEXT,
  status            TEXT DEFAULT 'queued',
    -- 'queued' | 'processing' | 'awaiting_speaker_confirm' | 'completed' | 'failed' | 'partial'
  current_step      TEXT,
    -- 's01_audio_extract' | 's02_transcribe' | ... | 's08_export'
  current_step_number INT,
  progress_pct      INT DEFAULT 0,
  clip_count        INT DEFAULT 0,
  error_message     TEXT,
  video_path        TEXT,           -- Railway'deki geçici dosya yolu
  trim_start_seconds FLOAT DEFAULT 0,
  trim_end_seconds  FLOAT,
  started_at        TIMESTAMPTZ DEFAULT now(),
  completed_at      TIMESTAMPTZ
);
```

**Status değerleri ve anlamları**:
- `queued`: Sıraya eklendi, başlamadı
- `processing`: Aktif olarak çalışıyor (S01-S08)
- `awaiting_speaker_confirm`: S03 sonrası, kullanıcı onayı bekleniyor
- `completed`: Tüm adımlar başarıyla tamamlandı
- `failed`: Bir adımda hata oluştu, durup hata mesajı bıraktı
- `partial`: Bazı klipler başarılı ama tümü değil

### 2.2 `transcripts` Tablosu

```sql
CREATE TABLE transcripts (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id           UUID REFERENCES jobs(id) ON DELETE CASCADE,
  raw_response     JSONB,           -- Deepgram'ın tam yanıtı
  labeled_transcript TEXT,          -- S04 çıktısı (insan okunabilir)
  word_timestamps  JSONB,           -- [{word, start, end, speaker, confidence}, ...]
  speaker_map      JSONB,           -- {"SPEAKER_0": {"role": "guest", "name": "Elon"}}
  speaker_confirmed BOOLEAN DEFAULT false,
  created_at       TIMESTAMPTZ DEFAULT now()
);
```

**word_timestamps formatı**:
```json
[
  {
    "word": "hello",
    "punctuated_word": "Hello,",
    "start": 1.23,
    "end": 1.56,
    "speaker": 0,
    "confidence": 0.97
  }
]
```

### 2.3 `clips` Tablosu

```sql
CREATE TABLE clips (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id                UUID REFERENCES jobs(id) ON DELETE CASCADE,
  channel_id            TEXT,
  clip_index            INT,             -- sıra numarası (0'dan)
  start_time            FLOAT,           -- saniye cinsinden
  end_time              FLOAT,
  duration_s            FLOAT,
  hook_text             TEXT,            -- ilk cümle
  content_type          TEXT,            -- revelation | debate | humor | ...
  confidence            FLOAT,           -- overall_confidence (0.0-1.0)

  -- Puanlar (1-10)
  standalone_score      INT,
  hook_score            INT,
  arc_score             INT,
  channel_fit_score     INT,
  overall_confidence    FLOAT,

  -- Gemini düşünce adımları
  thinking_steps        JSONB,

  -- Kalite değerlendirmesi
  quality_verdict       TEXT,            -- pass | fixable | fail
  reject_reason         TEXT,

  -- Strateji
  clip_strategy_role    TEXT,            -- launch | viral | engagement | fan_service
  posting_order         INT,             -- pass: 1,2,3 | fail: 999

  -- YouTube
  suggested_title       TEXT,
  suggested_description TEXT,

  -- Dosya
  file_url              TEXT,            -- R2 public URL
  video_landscape_path  TEXT,            -- opsiyonel lokal yedek
  is_successful         BOOLEAN DEFAULT true,
  why_failed            TEXT,

  -- Kullanıcı aksiyonu
  user_approved         BOOLEAN,
  user_notes            TEXT,
  is_published          BOOLEAN DEFAULT false,

  -- YouTube yayın
  youtube_video_id      TEXT,
  published_at          TIMESTAMPTZ,

  -- Performans
  feedback_status       TEXT,
  views_48h             INT,
  views_7d              INT,
  avd_pct               FLOAT,           -- Average View Duration %

  -- RAG
  clip_summary          TEXT,            -- Gemini'nin özeti
  clip_summary_embedding vector(768),    -- pgvector embed

  created_at            TIMESTAMPTZ DEFAULT now()
);
```

**Kritik kural**: `clip_summary_embedding` vektör boyutu **768**'dir. Değiştirilmez.

### 2.4 `channels` Tablosu

```sql
CREATE TABLE channels (
  id                  TEXT PRIMARY KEY,       -- kullanıcı belirlediği slug
  display_name        TEXT NOT NULL,
  niche               TEXT,                   -- "tech", "fitness", "finance"
  content_format      TEXT,                   -- "podcast", "interview"
  clip_duration_min   INT DEFAULT 15,
  clip_duration_max   INT DEFAULT 60,
  channel_vision      TEXT,                   -- kanal hakkında kısa açıklama
  channel_dna         JSONB,                  -- tam DNA yapısı
  youtube_channel_id  TEXT,
  youtube_access_token TEXT,
  youtube_refresh_token TEXT,
  onboarding_status   TEXT DEFAULT 'pending', -- pending | in_progress | ready
  created_at          TIMESTAMPTZ DEFAULT now()
);
```

### 2.5 `guest_profiles` Tablosu

```sql
CREATE TABLE guest_profiles (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  normalized_name  TEXT UNIQUE NOT NULL,  -- küçük harfle ("elon musk")
  original_name    TEXT NOT NULL,
  profile_data     JSONB NOT NULL,
    -- {profile_summary, recent_topics, viral_moments, controversies,
    --  expertise_areas, clip_potential_note}
  expires_at       TIMESTAMPTZ NOT NULL, -- 7 gün sonra
  updated_at       TIMESTAMPTZ DEFAULT now()
);
```

### 2.6 `reference_clips` Tablosu

```sql
CREATE TABLE reference_clips (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  channel_id               TEXT REFERENCES channels(id),
  source                   TEXT,           -- "youtube_shorts"
  source_url               TEXT,
  transcript               TEXT,
  clip_summary             TEXT,
  clip_summary_embedding   vector(768),
  views                    INT,
  performance_data         JSONB,
  analyzed_at              TIMESTAMPTZ DEFAULT now()
);
```

Kanal onboarding sırasında kanalın en iyi YouTube short'larından oluşturulur. Channel DNA'sının referans materyalidir.

### 2.7 `pipeline_audit_log` Tablosu

```sql
CREATE TABLE pipeline_audit_log (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id         UUID,
  step_number    INT,
  step_name      TEXT,
  status         TEXT,         -- started | completed | failed | skipped
  input_summary  JSONB,        -- adım başında ne biliyorduk
  output_summary JSONB,        -- adım ne üretti
  duration_ms    INT,
  token_usage    JSONB,        -- Gemini token kullanımı (varsa)
  error_message  TEXT,
  error_stack    TEXT,
  created_at     TIMESTAMPTZ DEFAULT now()
);
```

**Director için kritik**: Her pipeline adımının ne kadar sürdüğü, kaç token harcandığı ve hangi adımlarda hata oluştuğu bu tablodan okunabilir.

---

## 3. API KATMANI

**Dosya**: `backend/app/main.py`

### Endpoint Grupları

```
/jobs          → jobs.py     (iş oluşturma, durum)
/clips         → clips.py    (klip yönetimi)
/speakers      → speakers.py (konuşmacı onayı)
/channels      → channels.py (kanal yönetimi)
/reframe       → reframe.py  (video reframe)
/captions      → captions.py (altyazı üretimi)
/youtube-metadata → youtube_metadata.py
/feedback      → feedback.py (performans takibi)
/downloads     → downloads.py (dosya indirme)
/proxy         → proxy.py    (URL proxy)
/ws            → progress.py (WebSocket)
/output        → StaticFiles (/output dizini)
/health        → health check
```

### CORS Konfigürasyonu

```python
CORSMiddleware(
  allow_origins=["*"],      # tüm origins
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"]
)
```

### Clips Endpoint'leri (clips.py)

```
GET  /clips                     → job_id veya channel_id ile liste
GET  /clips/{clip_id}           → tek klip detayı
PATCH /clips/{clip_id}/approve  → user_approved=True
PATCH /clips/{clip_id}/reject   → user_approved=False
PATCH /clips/{clip_id}/publish  → is_published=True + youtube_video_id
DELETE /clips/{clip_id}         → klibi sil
```

### Channels Endpoint'leri (channels.py)

```
POST  /channels                           → kanal oluştur
GET   /channels                           → tüm kanallar
GET   /channels/{channel_id}              → tek kanal
PATCH /channels/{channel_id}              → güncelle (dna dahil)
POST  /channels/{channel_id}/onboard/existing → YouTube onboarding başlat
```

### Feedback Endpoint'leri (feedback.py)

```
POST /feedback/clips/{clip_id}/publish    → yayın tarihi + video ID kaydet
POST /feedback/clips/{clip_id}/performance → views_48h, views_7d, avd_pct güncelle
GET  /feedback/clips/{channel_id}         → kanal performans özeti
```

---

## 4. SERVİS KATMANI

### 4.1 Gemini Client (`services/gemini_client.py`)

```python
Singleton pattern

İki client türü:
  1. VertexAI client (primary): GCP credentials
  2. Developer client (fallback): API key ile

Metotlar:
  generate(prompt, system, model) → str
    → Model default: GEMINI_MODEL_FLASH
    → 3 deneme, 30s → 60s bekleme

  generate_json(prompt, system, model) → dict
    → ```json``` wrapper'ları sil
    → Control char'ları temizle (re.sub(r'[\x00-\x1f]', '', raw))
    → json.loads()

  analyze_video(video_path, prompt, model) → str
    → <20MB: inline bytes
    → ≥20MB: GCS'e yükle, gs:// URI ile analiz, sonra sil
    → Fallback: audio analizi → transcript analizi

  analyze_audio(audio_path, prompt, model) → str
    → analyze_video ile benzer mantık

  embed_content(text) → list[float]
    → Model: text-embedding-004
    → 768 boyutlu vektör
    → clips.clip_summary_embedding için
```

### 4.2 Deepgram Client (`services/deepgram_client.py`)

```python
transcribe(audio_path) → dict

POST https://api.deepgram.com/v1/listen
Headers:
  Authorization: Token {DEEPGRAM_API_KEY}
  Content-Type: audio/mp4

Parameters:
  model=nova-2
  diarize=true
  sentiment=true
  punctuate=true
  utterances=true
  words=true
  language=en

Timeout: 300 saniye
```

### 4.3 Supabase Client (`services/supabase_client.py`)

```python
Singleton:
_supabase_client = None

def get_client() -> Client:
    global _supabase_client
    if not _supabase_client:
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _supabase_client

# ZORUNLU: SUPABASE_URL içinde port 6543 olmalı
# Doğru:    https://xxx.supabase.co:6543/...
# Yanlış:   https://xxx.supabase.co:5432/...
```

### 4.4 R2 Client (`services/r2_client.py`)

```python
upload_clip(job_id, filename, file_path) → str

boto3.client(
    's3',
    endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
    aws_access_key_id=R2_ACCESS_KEY_ID,
    aws_secret_access_key=R2_SECRET_ACCESS_KEY
)

bucket_key = f"{job_id}/{filename}"
public_url = f"{R2_PUBLIC_URL}/{bucket_key}"
```

---

## 5. KANAL SİSTEMİ (`channels/`)

**CLAUDE.md**: Bu yapı değiştirilmez.

### Kanal İzolasyonu

Her kanal kendi konfigürasyonu ve veri silosunda çalışır:

```
backend/channels/
├── channel_registry.py         → dinamik kanal yükleme
└── speedy_cast/
    └── config.py               → varsayılan kanal konfigürasyonu
```

### channel_registry.py

```python
# Kanalları dinamik olarak yükler
# Yeni kanal eklenmek istenirse channels/ altına dizin oluşturulur
# config.py içinde kanal parametreleri tanımlanır
```

### speedy_cast/config.py

Varsayılan kanal konfigürasyonu. Yeni kanallar bu yapıdan türetilir.

---

## 6. BELLEK/GERİBESLİM SİSTEMİ (`app/memory/`)

**CLAUDE.md**: Bu sistem şu an askıya alınmış. Değiştirilmez.

Feedback döngüsü şu an `clips` tablosunun `views_48h`, `views_7d`, `avd_pct` alanları ve `feedback.py` route'u üzerinden manuel olarak yönetilmektedir.

Asıl memory sistemi ileride aktive edilecektir.

---

## 7. KANAL ONBOARDING AKIŞI

### Onboarding Nedir?

Yeni kanal eklendiğinde kanalın çalışma şeklini öğrenmek için yapılan tek seferlik analiz.

### Akış

```
1. Kullanıcı /channels/{id}/onboard/existing çağırır
2. YouTube API'den kanalın son short'ları çekilir (20 adet)
3. Her short için transkript çıkarılır (Deepgram)
4. Başarılı short'lar (görüntülenme eşiği üstü) seçilir
5. reference_clips tablosuna kaydedilir
6. reference_analyzer.py çalışır:
   a. Klip özetleri oluşturulur (gemini-2.5-flash)
   b. Embed'ler üretilir (text-embedding-004, 768 dim)
   c. channel_dna oluşturulur (gemini-2.5-flash)
7. channels.channel_dna güncellenir
8. channels.onboarding_status → 'ready'
```

### Channel DNA Oluşturma Promptu

```
Gemini'ye gönderilen:
- 20 başarılı klip özeti + performans verileri
- "Bu kliplerin ortak özelliklerine bakarak kanal DNA'sı oluştur"

Dönen:
- audience_identity, tone, do_list, dont_list, no_go_zones,
  best_content_types, humor_profile, duration_range,
  speaker_preference, hook_style, sacred_topics,
  title_style, description_template
```

---

## 8. KONFIGÜRASYON (`app/config.py`)

```python
class Settings(BaseSettings):
    # AI Modeller
    GEMINI_MODEL_PRO = "gemini-3.1-pro-preview"   # S05/S06
    GEMINI_MODEL_FLASH = "gemini-2.5-flash"         # Diğerleri

    # API Anahtarları
    GEMINI_API_KEY: str
    DEEPGRAM_API_KEY: str

    # Supabase
    SUPABASE_URL: str      # port 6543 içermeli
    SUPABASE_SERVICE_KEY: str

    # R2
    R2_ACCOUNT_ID: str     # hex ID sadece, URL değil
    R2_ACCESS_KEY_ID: str
    R2_SECRET_ACCESS_KEY: str
    R2_BUCKET_NAME: str
    R2_PUBLIC_URL: str     # https://pub-xxx.r2.dev

    # Dizinler
    OUTPUT_DIR: Path = Path("output")
    UPLOAD_DIR: Path = Path("uploads")

    # Genel
    ENVIRONMENT: str = "production"
    FRONTEND_URL: str
```

---

## 9. HATA YÖNETİMİ STANDARDI

Her fonksiyon:

```python
try:
    result = operation()
except Exception as e:
    print(f"[ModülAdı] Error in fonksiyon_adı: {e}")
    result = fallback_value  # ya da raise
finally:
    # Dosya temizliği her durumda
    for path in [temp_path_1, temp_path_2]:
        if path and os.path.exists(path):
            os.remove(path)
```

### Kritik Kural

Gemini prompt'larında **asla `.format()` kullanılmaz**:

```python
# YANLIŞ — JSON içindeki {} format() ile çakışır
prompt = "Return: {{'key': 'value'}}".format(x=y)

# DOĞRU
prompt = "Return: {'key': 'value'}"
prompt = prompt.replace("GUEST_NAME", guest_name)
```

---

## 10. ORTAM DEĞİŞKENLERİ

### Railway
```
GEMINI_API_KEY=
DEEPGRAM_API_KEY=
SUPABASE_URL=          # port 6543 içermeli
SUPABASE_SERVICE_KEY=
DATABASE_URL=          # port 6543 ZORUNLU
FRONTEND_URL=
```

### Vercel
```
NEXT_PUBLIC_API_URL=   # Railway backend URL
```

### Cloudflare R2
```
R2_ACCOUNT_ID=         # hex ID sadece (URL değil)
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=
R2_PUBLIC_URL=         # https://pub-xxxxx.r2.dev
```

---

## 11. DOCKER YAPISI

### Dockerfile İlkesi

```dockerfile
# ÖNCE requirements.txt, SONRA kod — Docker layer cache için kritik
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
```

### FFmpeg

```dockerfile
# Base image'da FFmpeg ve ffprobe kurulu olmalı
RUN apt-get install -y ffmpeg
```

---

## 12. DIRECTOR İÇİN SİSTEM GENELİ METRİKLER

### Sistem Sağlığı Göstergeleri

| Metrik | Kaynak | Hedef |
|--------|--------|-------|
| Toplam pipeline başarı oranı | jobs tablosu: completed/total | > %90 |
| Ortalama pipeline süresi | pipeline_audit_log: duration_ms toplamı | < 8 dakika |
| S05 token kullanımı | audit_log.token_usage | İzle, artış var mı? |
| S06 token kullanımı | audit_log.token_usage | İzle |
| R2 upload hata oranı | clips.file_url'de lokal path oranı | < %2 |
| DB bağlantı hataları | error_message LIKE '%6543%' olmayan | 0 |
| Gemini rate limit sayısı | audit_log.error_message LIKE '%429%' | < günde 5 |
| Deepgram timeout | audit_log.error_message LIKE '%timeout%' | < günde 2 |

### Tablolarda Takip Edilebilir Performans

```sql
-- Kanal başarı oranı
SELECT channel_id,
       COUNT(*) as total,
       SUM(CASE WHEN quality_verdict='pass' THEN 1 ELSE 0 END) as passed,
       AVG(overall_confidence) as avg_confidence
FROM clips
GROUP BY channel_id;

-- İçerik türü başarısı
SELECT content_type,
       AVG(standalone_score) as avg_standalone,
       AVG(hook_score) as avg_hook,
       AVG(views_7d) as avg_views
FROM clips
WHERE quality_verdict = 'pass'
GROUP BY content_type
ORDER BY avg_views DESC;

-- Pipeline adım süreleri
SELECT step_name, AVG(duration_ms) as avg_ms, MAX(duration_ms) as max_ms
FROM pipeline_audit_log
WHERE status = 'completed'
GROUP BY step_name
ORDER BY avg_ms DESC;

-- Son 7 günde hata dağılımı
SELECT step_name, COUNT(*) as error_count
FROM pipeline_audit_log
WHERE status = 'failed'
  AND created_at > now() - interval '7 days'
GROUP BY step_name
ORDER BY error_count DESC;
```

---

*Bu döküman sistem altyapısında yapılan her değişiklikte güncellenmelidir.*
