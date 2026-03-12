# PROGNOT CLIP PIPELINE — AI ANAYASASI
> **Bu dosyayı her yeni AI konuşmasının başında `@CLAUDE.md` ile sisteme ekle.**
> Son güncelleme: Mart 2026 | Versiyon: 3.0 (Master)

---

## 1. PROJENİN KİMLİĞİ

**Prognot Clip Pipeline**, uzun formatlı yatay videoları (podcast, talk-show, röportaj)
yapay zeka ve RAG (Vektörel Hafıza) teknolojisiyle analiz edip, viral potansiyeli en
yüksek kesitleri kalite kaybı olmadan (lossless) kesen **tam otomatik, tek kullanıcılı**
kişisel bir endüstriyel sistemdir.

| Alan | Değer |
|------|-------|
| **Sahibi** | Ekrem (tek kullanıcı, kişisel sistem) |
| **Hedef** | Kendi YouTube kanalları için viral klip üretimi |
| **Deployment** | Railway (backend) + Vercel (frontend) + Supabase (DB) |
| **Geliştirme ortamı** | Cursor / Antigravity IDE + GitHub (main branch) |
| **CI/CD** | `git push` → Railway ve Vercel otomatik deploy alır |

---

## 2. AKTİF MODÜLLER

| Modül | Durum | Açıklama |
|-------|-------|----------|
| **Modül 1 — Klip Çıkartıcı** | ✅ AKTİF | Tek odak. Video analizi + hassas kesim |
| **Modül 2 — Dikey Format** | ⏸️ SÜRESİZ ASKIDA | 9:16 reframe + altyazı — dokunma |
| **Modül 3+** | 🔮 TANIMLANMADI | Gelecekte bağımsız modül olarak eklenecek |

> ⛔ `reframer.py` ve `subtitler.py` dosyalarına **hiçbir koşulda dokunma.**
> Modül 2 ile ilgili hiçbir geliştirme önerme, yapma veya test etme.

---

## 3. MODÜL 1 — PIPELINE AKIŞI

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

### Fallback Zinciri

| Adım | Hata Durumu | Fallback |
|------|-------------|----------|
| Transcribe (Groq) | API hatası / timeout | `transcript_text = ""` — Gemini ses analizi yeterli |
| Energy Analysis | Import / dosya hatası | `energy_summary = ""` ile devam |
| RAG Query | DB bağlantı hatası | `"Referans bulunamadı, genel viral kurallarını uygula."` |
| Gemini Analiz | Timeout / 429 | 3 deneme, 30s bekleme; tümü başarısız → `RuntimeError` |
| JSON Parse | Bozuk JSON | `re.sub` ile temizle, tekrar parse; başarısız → `[]` |
| Precision Cut | PySceneDetect hatası | Snap olmadan doğrudan FFmpeg ile kes |
| Cleanup | Dosya zaten silinmiş | `if os.path.exists()` kontrolü — hata fırlatma |

---

## 4. KANAL SİSTEMİ

Her YouTube kanalı için **tam izolasyon**: ayrı RAG verisi, ayrı Gemini prompt'u.
Kanallar birbirinin verisini hiçbir zaman görmez.

### Mevcut Kanallar

| channel_id | Kanal Adı | Config Dosyası | Durum |
|------------|-----------|----------------|-------|
| `speedy_cast` | Speedy Cast Clip | `backend/channels/speedy_cast/config.py` | ✅ Aktif |

### İzolasyon Prensibi

```
Speedy Cast                    Kadın Podcast (örnek)
─────────────────              ──────────────────────
viral_library                  viral_library
WHERE channel_id               WHERE channel_id
= 'speedy_cast'                = 'women_podcast'
       ↓                              ↓
speedy_cast/config.py          women_podcast/config.py
(özel prompt)                  (özel prompt)
       ↓                              ↓
   Klipler A                      Klipler B
```

### Yeni Kanal Eklerken Kontrol Listesi

- [ ] `backend/channels/{kanal_id}/config.py` oluştur
- [ ] Supabase `channels` tablosuna kayıt ekle
- [ ] `viral_library`'e `channel_id` doldurulmuş referans verileri ekle
- [ ] Frontend `CHANNELS` listesine ekle (`page.tsx`)
- [ ] `docs/CHANNELS.md` dokümantasyonunu güncelle

---

## 5. TECH STACK

### Backend (Railway — CPU ONLY)

```
Python 3.11
FastAPI + Uvicorn
FFmpeg (subprocess)       → Audio extraction, video cutting
Librosa                   → Ses enerji analizi (CPU)
PySceneDetect (OpenCV)    → Sahne geçişi tespiti (CPU)
psycopg2-binary           → PostgreSQL bağlantısı
Groq API                  → Whisper large-3 (word-level timestamps)
Google Genai SDK          → Gemini 2.5 Flash (JSON mode)
reportlab                 → PDF rapor üretimi
```

### Frontend & Altyapı

```
Next.js 15+ / TypeScript / Tailwind CSS   → Vercel
Supabase (PostgreSQL + pgvector)           → RAG veritabanı
gemini-embedding-001                       → 3072 boyutlu vektör (!)
```

---

## 6. KRİTİK DOSYA HARİTASI

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
│   ├── main.py                      FastAPI endpoints + StaticFiles mount
│   ├── pipeline.py                  Ana iş akışı yöneticisi
│   ├── analyzer.py                  RAG + Gemini (channel_id parametresi alır)
│   ├── cutter.py                    PySceneDetect + FFmpeg
│   ├── transcriber.py               Groq Whisper
│   ├── audio_analyzer.py            Librosa enerji analizi
│   ├── database.py                  Supabase CRUD
│   ├── state.py                     In-memory job tracking (DB fallback)
│   ├── report_builder.py
│   ├── metadata.py
│   ├── pdf_reporter.py
│   ├── channel_hunter.py            Viral DNA toplama (manuel script)
│   ├── requirements.txt
│   ├── .env                         (git'e gitmiyor)
│   │
│   ├── channels/
│   │   ├── channel_registry.py
│   │   ├── speedy_cast/
│   │   │   └── config.py
│   │   └── {yeni_kanal}/
│   │       └── config.py
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
    ├── app/page.tsx
    ├── next.config.js               /api/backend/* → Railway proxy
    └── tailwind.config.js
```

---

## 7. ORTAM DEĞİŞKENLERİ

### Railway (Backend)

```env
GEMINI_API_KEY=
GROQ_API_KEY=
SUPABASE_URL=            # https://xxx.supabase.co
SUPABASE_ANON_KEY=
DATABASE_URL=            # postgresql://...@xxx.supabase.co:6543/postgres
                         # ⚠️ PORT MUTLAKA 6543 OLMALI (Supabase Connection Pooler)
                         # 5432 Railway/Docker içinden erişilemez — Network unreachable hatası
FRONTEND_URL=            # https://xxx.vercel.app
```

### Vercel (Frontend)

```env
NEXT_PUBLIC_API_URL=     # https://xxx.railway.app
```

---

## 8. VERİTABANI ŞEMASI

> ⚠️ **`embedding vector(3072)`** — gemini-embedding-001'in gerçek çıktı boyutu.
> 768 veya başka değer kullanırsan boyut uyuşmazlığı hatası alırsın.

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
  created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE viral_library (
  id                SERIAL PRIMARY KEY,
  channel_id        TEXT NOT NULL,    -- KRİTİK: izolasyon buradan sağlanır
  title             TEXT,
  hook_text         TEXT,
  why_it_went_viral TEXT,
  content_pattern   TEXT,
  viral_score       INT,
  embedding         vector(3072),     -- ⚠️ gemini-embedding-001 = 3072 boyut
  created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- RAG performansı için index
CREATE INDEX ON viral_library
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

---

## 9. DEMİR KURALLAR

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

### Scope Disiplini

Yeni özellik veya büyük mantık değişikliği öncesinde mimari plan sun, onay al.
İstenmeyen şey ekleme. Tek PR = tek konu.

---

## 10. KLİP PARAMETRELERİ

```python
MAX_CLIP_DURATION   = 35   # saniye
MIN_CLIP_DURATION   = 15
MIN_VIRALITY_SCORE  = 80   # altındakiler reddedilir
CLIPS_PER_VIDEO     = 3
CRF_QUALITY         = 18   # FFmpeg (18 = görsel kayıpsız)
FFMPEG_THREADS      = 0    # 0 = tüm CPU çekirdekleri
```

---

## 11. BİLİNEN SORUNLAR & ÇÖZÜMLER

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

---

## 12. MİMARİ KARAR GEÇMİŞİ

| Karar | Alternatif | Neden Seçilmedi |
|-------|------------|-----------------|
| Groq Whisper API | WhisperX lokal | GPU gerektirir, CPU'da çalışmıyor |
| Gemini 2.5 Flash | GPT-4, Claude API | Google AI Studio ücretsiz tier yeterli |
| PySceneDetect | ML tabanlı sahne tespiti | GPU gerektirir |
| FFmpeg subprocess | Python FFmpeg kütüphanesi | Subprocess daha fazla flag esnekliği |
| Supabase pgvector | Pinecone, Weaviate | Zaten Supabase kullanıyoruz, ekstra servis gereksiz |
| Monorepo | Ayrı Modül 2 backend | Tek kişilik proje; diskler aynı — avantajlı |
| Railway Hobby Plan | Ücretsiz tier | Ücretsiz tier disk limiti doldu |
| `height<=1080` format | format_id-based yt-dlp | format_id Railway'de tutarsız |
| Port 6543 (Pooler) | Port 5432 (Direct) | 5432 Railway/Docker içinden erişilemiyor |

---

## 13. ANTİ-PATTERN'LER (Tekrar Önerme)

| Anti-Pattern | Ne Oldu | Doğrusu |
|-------------|---------|---------|
| `subtitler.py` rewrite önerisi | Kapsam dışı başlatıldı, yarıda durduruldu | Modül 2 askıda — dokunma |
| `0` Gemini'ye literal geçmek | "auto" mod yerine sıfır aldı, hata | `None` veya `"auto"` geç |
| channel_id'siz `viral_library` | Tüm kanal verileri karıştı | Her sorgu `WHERE channel_id = ?` zorunlu |
| `vector(768)` | gemini-embedding-001 gerçekte 3072 üretiyor | `vector(3072)` kullan |
| Browser extension VPN | Sadece tarayıcıyı yönlendiriyor | Sistem genelinde VPN gerekli (subprocess dahil) |

---

## 14. GELİŞTİRME ÖNCELİKLERİ (Güncel Backlog)

1. `viral_library` tablosuna `channel_id` kolonu ekle (Supabase migration)
2. `backend/channels/` yapısını kur — `speedy_cast/config.py` oluştur
3. `analyzer.py`'ı `channel_id` parametresi alacak şekilde güncelle
4. Frontend'e kanal seçim dropdown'ı ekle
5. `DATABASE_URL` portunu Railway env'de 6543'e güncelle
6. `main.py`'da `StaticFiles` mount kontrolü yap
7. Dockerfile layer caching optimizasyonu
8. Librosa entegrasyonunu pipeline ile doğrula

---

## 15. YASAK KONULAR

```
⛔ Modül 2 geliştirmesi (dikey format, reframe, altyazı)
⛔ reframer.py veya subtitler.py'ye dokunmak
⛔ GPU kütüphanesi önermek veya eklemek
⛔ vector(768) boyutu önermek
⛔ Pipeline akışını onay almadan değiştirmek
⛔ Kapsam dışı özellik eklemek
```