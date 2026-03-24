# MODÜL 2 — EDİTÖR (Editor)
> Son güncelleme: 2026-03-24 | OpenCut tabanlı editor entegrasyonu

Bu döküman, Modül 2 (Editor) sisteminin tüm bileşenlerini, çalışma mantığını, araçlarını ve veri akışlarını eksiksiz açıklar. Reframe, Auto Captions, YouTube metadata generatörü, preview sistemi, timeline yapısı ve depolama dahil tüm alt sistemler burada açıklanmıştır.

---

## 1. MODÜLÜN AMACI

Modül 2, Modül 1'in çıktısı olan klipler üzerinde son dokunuşları yapabilmek için tasarlanmış bir video editörüdür.

**Giriş**: Modül 1'den gelen klip (R2 URL) veya bağımsız video yüklemesi
**Çıkış**: Son formata getirilmiş klip — reframe edilmiş, altyazılı, YouTube metadata'sı eklenmiş

**Editörün Temel Özellikleri**:
- 16:9 → 9:16 reframe (yapay zeka yüz takibi + konuşmacı diarizasyonu)
- Otomatik altyazı üretimi (Deepgram word-level timestamps)
- YouTube başlık + açıklama oluşturma (Gemini Flash)
- Canvas tabanlı preview
- Timeline düzenleme
- Clip export (render)

---

## 2. EDİTÖR MİMARİSİ

### Kullanılan Teknoloji

| Katman | Teknoloji |
|--------|-----------|
| UI Framework | Next.js (OpenCut tabanlı) |
| State Management | Zustand stores |
| Timeline/Canvas | Özel renderer (MediaBunny tabanlı) |
| Video İşleme | FFmpeg (backend), Canvas API (frontend preview) |
| AI: Reframe | OpenCV DNN (backend Python) |
| AI: Captions | Deepgram nova-2 (backend API) |
| AI: YouTube | Gemini 2.5-flash (backend API) |

### Editör Dizin Yapısı

```
opencut/apps/web/src/
├── app/
│   ├── page.tsx                    → Ana sayfa (proje listesi)
│   └── projects/[id]/page.tsx      → Editör açılış sayfası
├── components/
│   └── editor/
│       ├── panels/
│       │   ├── assets/
│       │   │   └── views/
│       │   │       ├── reframe.tsx     → 9:16 Reframe paneli
│       │   │       └── captions.tsx    → Altyazı paneli
│       │   ├── properties/             → Seçili öğe özellikleri
│       │   └── preview/                → Canvas preview
│       └── timeline/                   → Timeline bileşenleri
├── stores/
│   ├── editor-store.ts             → Genel editör state
│   ├── timeline-store.ts           → Timeline state (snap, ripple, clipboard)
│   ├── preview-store.ts            → Preview oynatma state
│   ├── properties-store.ts         → Seçili öğe properties
│   ├── youtube-store.ts            → YouTube metadata state
│   └── reframe-metadata-store.ts   → Reframe için jobId state
├── core/
│   └── managers/
│       ├── timeline-manager.ts     → Timeline iş mantığı
│       ├── playback-manager.ts     → Oynatma kontrolü
│       ├── project-manager.ts      → Proje kaydet/yükle
│       ├── renderer-manager.ts     → Canvas render
│       ├── media-manager.ts        → Medya varlıkları
│       └── selection-manager.ts    → Öğe seçimi
└── types/
    ├── project.ts                  → Proje veri yapısı
    ├── timeline.ts                 → Timeline tip tanımları
    └── transcription.ts            → Altyazı tipleri
```

---

## 3. EDITÖRE GİRİŞ

### 3.1 Modül 1'den Editöre Geçiş

Modül 1 tamamlandığında klipler Clip Library'de görünür. Her klip kartında "Edit" butonu bulunur.

Tıklandığında:
```
1. Klip ID ve file_url editöre parametre olarak geçilir
2. Editor URL: /editor?clipJobId={job_id}&clipId={clip_id}
3. clipJobId → reframe-metadata-store'a yazılır (diarization için)
4. Klip video URL → timeline'a ilk medya öğesi olarak eklenir
```

**Neden clipJobId editöre geçiyor?**
Reframe işlemi sırasında konuşmacı segmentlerine ihtiyaç duyulur. Bu segmentler Supabase'de `transcripts` tablosunda `job_id` ile eşleştirilmiş halde durur. clipJobId olmadan reframe yalnızca yüz tespitine dayanmak zorunda kalır.

### 3.2 Bağımsız Video Yükleme

`frontend/app/editor/upload/page.tsx` üzerinden:
```
1. Kullanıcı video seçer
2. Dosya doğrudan editöre yüklenir (Modül 1 pipeline'ı çalışmaz)
3. Timeline'a boş canvas olarak açılır
4. Reframe çalışır ama diarization olmaz (speaker olmadığından yalnızca yüz tespiti)
```

---

## 4. TIMELINE SİSTEMİ

**Store**: `stores/timeline-store.ts`
**Manager**: `core/managers/timeline-manager.ts`

### Timeline Yapısı

```typescript
Timeline {
  tracks: Track[]
  duration: number       // toplam süre (saniye)
  currentTime: number    // oynatma başlığı
  fps: number            // frame rate
}

Track {
  id: string
  type: "video" | "audio" | "caption" | "effect"
  clips: TimelineClip[]
}

TimelineClip {
  id: string
  mediaId: string        // assets'teki medya referansı
  startTime: number      // track'teki pozisyon
  duration: number
  trimStart: number      // medya içi trim başlangıç
  trimEnd: number        // medya içi trim bitiş
  effects: Effect[]      // uygulanan efektler
  keyframes: Keyframe[]  // animasyon keyframe'leri (reframe için kullanılır)
}
```

### Timeline Özellikleri

| Özellik | Durum | Açıklama |
|---------|-------|---------|
| Snap | Aktif | Clip sınırları ve zaman işaretlerine yapışma |
| Ripple Editing | Aktif | Bir clip küçültülünce sonrakiler sola kayar |
| Clipboard | Aktif | Ctrl+C/V ile clip kopyalama |
| Multi-track | Aktif | Video + Audio + Caption + Effect track'leri |
| Keyframe Editor | Aktif | Reframe keyframe'lerini manuel düzenleme |

---

## 5. PREVIEW SİSTEMİ

**Store**: `stores/preview-store.ts`
**Manager**: `core/managers/renderer-manager.ts`

### Nasıl Çalışır?

Preview tamamen **canvas tabanlı**'dır. Tarayıcı video elementi doğrudan kullanılmaz:

```
1. Renderer-manager her frame'de canvas'a çizer
2. Video track'i → video elementi'nden frame çekilir, canvas'a çizilir
3. Caption track'i → canvas üzerine text overlay çizilir
4. Effect track'i → canvas transform'ları uygulanır
5. requestAnimationFrame döngüsü ile 30/60 fps oynatma
```

### Canvas Boyutları

Editörde iki mod:
- **Landscape** (16:9): 1920×1080 canvas
- **Portrait** (9:16): 1080×1920 canvas

Reframe aktif olduğunda canvas portrait moda geçer.

### Clip Preview Akışı

```
1. Kullanıcı playback başlatır
2. playback-manager → currentTime günceller (animationFrame)
3. renderer-manager her track'teki aktif clip'leri bulur
4. Video clip'i: video elementi.currentTime ayarlanır, canvas'a drawImage()
5. Caption clip'i: canvas fillText() + background rect
6. Reframe aktifse: her frame'de keyframe'den crop_x hesaplanır,
   canvas'ta clipping region uygulanır
```

---

## 6. REFRAME SİSTEMİ (9:16 Dönüştürme)

### 6.1 Genel Bakış

Reframe sistemi 16:9 landscape videoyu 9:16 portrait formata çevirir. Bunu yaparken:
- Sahnelerdeki konuşmacıların yüzlerini takip eder
- Konuşmacı değişimlerini diarization verisinden anlar
- Sahne kesimlerini tespit eder, kesim noktalarında anında geçiş yapar
- Aynı sahnede/konuşmacıda yumuşak (EMA) geçiş kullanır

### 6.2 Backend Pipeline

**Ana dosya**: `backend/app/reframe/processor.py`

```
REFRAME PIPELINE:
─────────────────────────────────────────────────────────
1. VİDEO YÜKLEMESİ
   clip_url (HTTP) → wget ile lokal'e indir
   clip_local_path → doğruca kullan
   → input_path (doğrulanmış)

2. SAHNE TESPİTİ (scene_detector.py)
   PySceneDetect kullanır
   Her sahne kesimi kaydedilir: [scene_cut_time, ...]
   Amaç: Pan'ın sahne kesimi üzerinde devam etmesini önle

3. YÜZ TESPİTİ (face_detector.py)
   Her 0.5 saniyede bir frame örneklenir (her frame değil, hız için)
   OpenCV DNN ile ResNet-10 SSD modeli kullanılır
   ↳ İlk çalışmada model otomatik indirilir (~10MB)
   ↳ Model başarısızsa Haar Cascade'e fallback yapılır

   Her frame için:
     Solda (cx ≤ 0.5) yüz = sol_yüz
     Sağda (cx > 0.5) yüz = sağ_yüz

   Outlier kaldırma:
     Komşu frame'lerden >0.25 sapan tespitler atılır

   Boşluk doldurma (within-scene):
     Tespit olmayan frame'lerde: son bilinen pozisyon tutulur (hold)
     Sahneler arası: SIFIRLANIR (bir sahnenin sağ yüzü öteki sahneye taşımaz)

4. DİARİZASYON VERİSİ (diarization.py)
   Supabase'den:
     SELECT word_timestamps FROM transcripts WHERE job_id = {job_id}
   Konuşmacı segmentleri çıkarılır:
     [{speaker: 0, start: 0.0, end: 12.5}, {speaker: 1, start: 12.5, end: 45.3}, ...]
   clip_start/clip_end'e kırpılır

5. CROP POZISYONU HESAPLAMA (crop_calculator.py)
   Kaynak: 1920×1080 (16:9)
   Hedef crop genişliği: 1080 × (9/16) ≈ 607px
   crop_x aralığı: 0 ile 1920-607 = 1313

   Her frame için:
     Aktif konuşmacıyı bul (diarization'dan)
     Konuşmacı 0 (HOST) → SOL yüzü takip et, yoksa sağı
     Konuşmacı 1 (GUEST) → SAĞ yüzü takip et, yoksa solu

     Konuşmacı değişimi veya sahne kesimi → ANİNDEN atla
     Aynı konuşmacı + aynı sahne → EMA smoothing (α = 0.15)
       ema_x = α × hedef_x + (1 - α) × önceki_ema_x

   Sonuç: her frame için crop_x (int32 array)

6. KEYFRAME ÜRETIMI (crop_calculator.py)
   Canvas pixel ofsetlerine dönüştürülür
   Değişim > 25px olan noktalarda keyframe eklenir
   Sahne kesimlerinde: HOLD keyframe (önce) + LINEAR keyframe (sonra)
   Min keyframe aralığı: 0.5 saniye
   Interpolation tipleri: "linear" | "hold"

7. SONUÇ
   Encode YOK. Upload YOK.
   Sadece keyframe listesi döner:
   {
     keyframes: [{time_s: 0.0, offset_x: 412, interpolation: "linear"}, ...],
     src_w: 1920, src_h: 1080, fps: 30.0, duration_s: 45.3
   }
```

### 6.3 Yüz Tespiti Detayları

**Dosya**: `backend/app/reframe/face_detector.py`

```python
Birincil model: OpenCV DNN ResNet-10 SSD
  Confidence threshold: 0.5
  İlk çalışmada model dosyası indirilir:
    deploy.prototxt    → model mimarisi
    res10_300x300_ssd_iter_140000.caffemodel → ağırlıklar

Fallback model: Haar Cascade (haarcascade_frontalface_default.xml)
  OpenCV'ye dahil, kurulum gerekmez
  Daha hızlı ama daha az doğru
  Profil yüzleri tespit edemez

Çıktı per-frame:
  [{"cx_norm": 0.3, "cy_norm": 0.4, "confidence": 0.87}, ...]
  cx_norm/cy_norm: 0.0-1.0 normalize koordinatlar
```

### 6.4 Sahne Tespiti Detayları

**Dosya**: `backend/app/reframe/scene_detector.py`

```python
Kütüphane: PySceneDetect
Eşik: ContentDetector (varsayılan eşik)
Sonuç: sahne başlangıç zamanları listesi (saniye cinsinden)
Amaç: Pan'ın sahne sınırını geçmesini önle
```

### 6.5 API Endpoints

**Dosya**: `backend/app/api/routes/reframe.py`

```
POST /reframe/upload
  Input: video dosyası (multipart/form-data)
  Process: UPLOAD_DIR'e kaydeder
  Output: {local_path, filename}

POST /reframe/process
  Input: {
    clip_url: str (HTTP URL) veya clip_local_path: str,
    job_id: str (opsiyonel, diarization için),
    clip_start: float (opsiyonel),
    clip_end: float (opsiyonel)
  }
  Process: asyncio task olarak processor.process_reframe() başlatır
  Output: {reframe_job_id}

GET /reframe/status/{reframe_job_id}
  Output: {
    status: "processing" | "completed" | "failed",
    progress: 0-100,
    result: {keyframes, src_w, src_h, fps, duration_s}  ← tamamlandıysa
  }
```

### 6.6 Frontend Entegrasyonu

**Dosya**: `opencut/apps/web/src/components/editor/panels/assets/views/reframe.tsx`

```typescript
Kullanıcı "Run Reframe" butonuna bastığında:

1. reframe-metadata-store'dan clipJobId al
2. Editördeki aktif video klibini bul (timeline'dan)
3. POST /reframe/upload → video dosyasını yükle → local_path al
4. POST /reframe/process {
     clip_local_path: local_path,
     job_id: clipJobId,
     clip_start: clip.trimStart,
     clip_end: clip.trimEnd
   }
5. Poll GET /reframe/status/{id} (her 1 saniyede)
6. Tamamlandığında:
   a. Canvas boyutunu 1080×1920 yap (portrait mod)
   b. Tüm timeline klipleri üzerindeki keyframe'leri güncelle
   c. Her keyframe: {time_s, offset_x} → timeline keyframe objesine çevir
   d. interpolation: "linear" → smooth, "hold" → sabit tut
7. Preview'da anlık güncellenir (canvas rerender)
```

**reframe-metadata-store.ts**:
```typescript
// Editör açılışında clipJobId burada saklanır
const useReframeMetadataStore = create<{
  clipJobId: string | null;
  setClipJobId: (id: string) => void;
}>()
```

---

## 7. OTOMATİK ALTYAZI (Auto Captions)

### 7.1 Genel Bakış

Otomatik altyazı sistemi, klibin sesini Deepgram'a göndererek kelime bazlı timestamp'ler alır ve bunları caption segmentlerine gruplar.

### 7.2 Backend API

**Dosya**: `backend/app/api/routes/captions.py`

```
POST /captions/generate
  Input: ses dosyası (WAV veya WebM, multipart/form-data)

  İşlem:
    1. Gelen dosyayı 16kHz mono WAV'a dönüştür (FFmpeg):
         ffmpeg -i input -ar 16000 -ac 1 output.wav
    2. Deepgram nova-2'ye gönder:
         model=nova-2
         punctuate=true
         words=true
         smart_format=true
    3. Kelime gruplarına ayır:
         - Noktalama işareti geldiğinde veya
         - 10 kelimeye ulaşıldığında
         yeni segment başlatılır
    4. Her segment: {text, start, end}

  Çıktı:
    {
      segments: [{text, start, end}, ...],
      words: [{word, punctuated_word, start, end, confidence}, ...],
      text: "full transcript",
      language: "en"
    }
```

### 7.3 Frontend Entegrasyonu

**Dosya**: `opencut/apps/web/src/components/editor/panels/assets/views/captions.tsx`

```typescript
Kullanıcı "Generate Captions" butonuna bastığında:

1. Timeline'daki video klibinin sesini çıkar (MediaBunny API)
2. POST /captions/generate → segmentler + kelimeler alınır
3. Segmentleri caption chunk'larına böl:
     maxChars (20 | 32 | 42 karakter seçeneği)
     maxLines (1 veya 2 satır)
4. Her chunk → Caption objesine dönüştür:
     {
       text: str,
       startTime: float,
       endTime: float,
       words: [{word, start, end}]  ← kelime bazlı highlight için
     }
5. Caption track'e ekle (timeline'a yeni track açılır)
6. Preview'da görünür

İndirme:
  - SRT formatında indirilebilir
  - Timeline'a uygulanabilir (caption track olarak)
```

### 7.4 Caption Görsel Seçenekleri

Kullanıcı caption stilini ayarlayabilir:
- Font boyutu
- Font rengi
- Background (renkli/şeffaf/kapalı)
- Pozisyon (üst/orta/alt)
- Kelime bazlı highlight (aktif kelime farklı renk)

---

## 8. YOUTUBE METADATA OLUŞTURMA

### 8.1 Genel Bakış

Editörde "YouTube" panelinde, yapay zeka ile YouTube başlığı ve açıklaması otomatik olarak oluşturulabilir.

### 8.2 Backend API

**Dosya**: `backend/app/api/routes/youtube_metadata.py`

```
POST /youtube-metadata/generate
  Input:
    {
      title: str,         ← mevcut başlık (varsa)
      description: str,   ← mevcut açıklama (varsa)
      guest_name: str     ← misafir adı (opsiyonel)
    }

  Model: gemini-2.5-flash (S05/S06 değil, flash yeterli)

  Prompt talimatları:
    Title:
      - Max 100 karakter
      - Merak uyandırıcı, dikkat çekici
      - guest_name varsa dahil et
    Description:
      - 2-4 paragraf
      - Misafirden bahset
      - 5-8 hashtag ekle

  Çıktı:
    {
      title: "Generated YouTube title",
      description: "Generated YouTube description\n\n#tag1 #tag2..."
    }
```

### 8.3 Frontend State

**Dosya**: `opencut/apps/web/src/stores/youtube-store.ts`

```typescript
Zustand store — localStorage'a persist edilir (proje başına)

{
  title: string,
  description: string,
  guestName: string,

  setTitle: (t: string) => void,
  setDescription: (d: string) => void,
  setGuestName: (n: string) => void,
  generate: () => Promise<void>  // API çağrısı yapar
}
```

**Neden localStorage?**
Kullanıcı sekmeyi kapasa bile metadata kaybolmasın. Her proje ID'sine göre ayrı kayıt.

---

## 9. EXPORT (Render)

### 9.1 Nasıl Çalışıyor?

Editor export işlemi tamamen **istemci tarafında** gerçekleşir (server-side render yok):

```
1. Kullanıcı "Export" butonuna basar
2. Timeline'daki tüm clip'ler, efektler, caption'lar taranır
3. Her frame canvas üzerine render edilir (requestAnimationFrame)
4. MediaRecorder API ile canvas stream'i yakalanır
5. MP4 veya WebM olarak indirilir
```

### 9.2 Reframe Dahil Export

Eğer reframe aktifse:
- Her frame'de crop_x keyframe değeri hesaplanır
- Canvas transform uygulanarak sadece o bölge çizilir
- Canvas boyutu 1080×1920 olduğundan output 9:16 olur

### 9.3 Caption Dahil Export

Caption track'i aktifse:
- Her frame'de o anki aktif caption bulunur
- Canvas'a text overlay olarak çizilir
- Export'a dahil olur

---

## 10. PROJE YÖNETİMİ

**Manager**: `core/managers/project-manager.ts`

### Proje Yapısı

```typescript
Project {
  id: string
  name: string
  createdAt: string
  updatedAt: string

  timeline: Timeline       // track + clip yapısı
  assets: MediaAsset[]     // timeline'daki medya varlıkları
  captions: Caption[]      // oluşturulan captions
  reframeKeyframes: Keyframe[]  // reframe keyframe'leri

  // YouTube metadata (youtube-store'dan)
  youtubeTitle: string
  youtubeDescription: string
}
```

### Kaydetme/Yükleme

Projeler **localStorage**'a kaydedilir (JSON serialize):
- Browser kapanınca silinmez
- Birden fazla proje aynı anda tutulabilir
- Supabase'e project kaydı yapılmaz (tamamen istemci tarafı)

---

## 11. DOSYA DEPOLAMA (Editör Bağlamında)

### Modül 1'den Gelen Dosyalar

```
R2 Bucket: {job_id}/{clip_filename}.mp4
Public URL: https://pub-xxx.r2.dev/{job_id}/{filename}
```

Editör bu URL'yi direkt stream eder. Kopyalamaz, yeniden upload etmez.

### Reframe İşleminde Geçici Dosyalar

```
UPLOAD_DIR/{uuid}.mp4     → POST /reframe/upload ile kaydedilen dosya
  ↓ processor.py çalışır
  ↓ Sonuç döner (sadece keyframes)
  ↓ finally: dosya silinir
```

Reframe kesinlikle encode yapmaz. Çıktı sadece matematiksel keyframe verisidir.

### Caption Geçici Dosyaları

```
temp_{uuid}.wav           → FFmpeg audio extraction (16kHz mono)
  ↓ Deepgram'a gönderilir
  ↓ finally: silinir
```

---

## 12. KANAL DNA İLE EDİTÖR ENTEGRASYONu

Editör, kanal DNA'sını YouTube metadata üretiminde kullanır:

Eğer Modül 1'den klip açılıyorsa:
```
1. clip.channel_id mevcut
2. YouTube metadata üretilirken channel_dna.title_style okunur
3. Gemini prompt'una dahil edilir: "Şu stili kullan: {title_style}"
4. clip.suggested_title ve clip.suggested_description ön doldurma olarak yüklenir
5. Kullanıcı isteğe göre değiştirebilir veya yeniden ürettirebilir
```

---

## 13. WEBSOCKET PROGRESS (Gerçek Zamanlı İlerleme)

**Dosya**: `backend/app/api/websocket/progress.py`

Reframe ve diğer uzun işlemler için:

```
WS bağlantısı: ws://backend/ws/progress/{job_id}

Mesaj tipi: "reframe_progress"
  {type: "reframe_progress", job_id: str, progress: 0-100, message: str}

Mesaj tipi: "completed"
  {type: "completed", job_id: str, result: {...}}

Mesaj tipi: "error"
  {type: "error", job_id: str, message: str}
```

Frontend bu mesajları dinler ve progress bar'ı günceller.

---

## 14. HATA YÖNETİMİ

### Backend Hataları

**Reframe**:
```python
try:
    result = processor.process_reframe(...)
except Exception as e:
    print(f"[Reframe] Error: {e}")
    return {"status": "failed", "error": str(e)}
finally:
    if os.path.exists(input_path):
        os.remove(input_path)
```

**Captions**:
```python
try:
    response = deepgram.transcribe(audio_path)
    segments = group_words(response.words)
except Exception as e:
    print(f"[Captions] Error: {e}")
    raise HTTPException(500, detail=str(e))
finally:
    if os.path.exists(temp_wav):
        os.remove(temp_wav)
```

**YouTube Metadata**:
```python
try:
    result = gemini.generate_json(prompt)
except Exception as e:
    # Fallback: mevcut başlık/açıklamayı döndür
    return {"title": title, "description": description}
```

### Frontend Hataları

- Reframe başarısız → toast hata mesajı, keyframe uygulanmaz
- Captions başarısız → toast hata mesajı, boş caption track
- YouTube metadata başarısız → mevcut değerler korunur

---

## 15. GÜNCELLEME GEÇMİŞİ

| Tarih | Değişiklik |
|-------|-----------|
| 2026-03-XX | Reframe sistemi overhaul: interpolation → hold-fill, scene boundary'de cut |
| 2026-03-XX | clipJobId editor URL'ine parametre olarak eklendi |
| 2026-03-XX | Reframe yüz takibi düzeltmesi: 3 root cause fix |
| 2026-03-XX | Local file upload desteği (blob: URL hatası düzeltildi) |

---

## 16. DIRECTOR İÇİN ANALİZ NOKTALARI

| Metrik | Nasıl Ölçülür | Hedef |
|--------|--------------|-------|
| Reframe Kalitesi | Kullanıcı manuelde kaç keyframe düzeltiyor? | < %20 düzeltme |
| Caption WER | Kelime hata oranı (Deepgram accuracy) | < %5 |
| Yüz Tespiti Başarı Oranı | Frame başarı / toplam frame | > %85 |
| Sahne Tespiti Hassasiyeti | Yanlış pozitif sahne kesimi | < %10 |
| YouTube Başlık Benimseme | Üretilen başlıkların kaçı değiştirilmeden kullanılıyor? | > %60 |
| Reframe İşlem Süresi | Saniye başına işlem | < 0.5s/saniye video |

### Potansiyel İyileştirme Alanları

1. **Yüz Tespiti**: DNN profil yüzleri görmekte zorlanır. Daha gelişmiş model (RetinaFace) ileride kullanılabilir ama GPU gerektirdiğinden şu an ertelendi.
2. **Reframe EMA Hızı**: α=0.15 bazı hızlı sahnelerde geç kalıyor. Dinamik alpha (hareket hızına göre) iyileştirme yapabilir.
3. **Caption Gruplandırma**: Şu an kelime sayısı ve noktalama ile gruplanıyor. Anlamsal gruplandırma (cümle bazlı) daha iyi sonuç verebilir.
4. **YouTube Metadata**: Flash model kullanılıyor, Pro ile daha kaliteli başlıklar üretilebilir ama maliyet artar.
5. **Client-side Export**: Tarayıcı tabanlı render yavaş. Server-side FFmpeg render entegrasyonu yapılabilir.

---

*Bu döküman her Modül 2 güncellemesinde ilgili bölümler değiştirilerek güncel tutulmalıdır.*
