# Clip Pipeline

YouTube → Viral Klipler otomasyon sistemi.

---

## Kurulum (İlk Kez)

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
```

`.env` dosyasını aç, API key'lerini yaz:
```
GEMINI_API_KEY=buraya_gemini_key_yaz
OPENAI_API_KEY=buraya_openai_key_yaz
```

### 2. Frontend

```bash
cd frontend
npm install
```

---

## Çalıştırma (Her Seferinde)

**Terminal 1 — Backend:**
```bash
cd backend
uvicorn main:app --reload --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

Tarayıcıda aç: **http://localhost:3000**

---

## Nasıl Kullanılır

1. YouTube URL yapıştır
2. Kaç klip istediğini seç (1-5)
3. "Klipleri Oluştur" butonuna bas
4. Bekle (video uzunluğuna göre 3-10 dakika)
5. Klipleri önizle, MP4 ve SRT olarak indir
6. metadata.txt'i aç — başlıklar ve açıklamalar hazır

---

## Çıktı Yapısı

```
backend/output/
└── {job_id}/
    ├── source.mp4       ← orijinal video
    ├── audio.mp3        ← ses dosyası
    ├── clip_01.mp4      ← kesilmiş klip
    ├── clip_01.srt      ← altyazı
    ├── clip_02.mp4
    ├── clip_02.srt
    └── metadata.txt     ← başlık + açıklama + hashtag
```
