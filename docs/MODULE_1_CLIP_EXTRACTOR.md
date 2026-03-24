# MODÜL 1 — KLİP ÇIKARICI (Clip Extractor)
> Son güncelleme: 2026-03-24 | Pipeline V4 (8 Adım)

Bu döküman, Modül 1'in tüm çalışma mantığını, her aşamasını, kullandığı araçları, AI modellerini, promptları, veri akışlarını ve karar mekanizmalarını eksiksiz açıklar. Director modülünün bu sistemi anlayarak analiz edebilmesi için yazılmıştır.

---

## 1. MODÜLÜN AMACI

Modül 1, uzun formatlı video içeriklerinden (podcast, röportaj) viral potansiyeli yüksek kısa klipler çıkarmak için tasarlanmış tam otomatik bir AI pipeline'ıdır.

**Giriş**: Ham video dosyası (MP4, MOV, etc.)
**Çıkış**: Puanlanmış, kesilmiş, encode edilmiş, Cloudflare R2'ye yüklenmiş ve Supabase'e kaydedilmiş klipler

**Beklenen Sonuç**:
- Her video için 2-8 arasında "pass" kalitesinde klip
- Her klip; hook kalitesi, bağımsızlık skoru, arc bütünlüğü ve kanal uyumu açısından puanlanmış
- YouTube başlığı ve açıklaması hazırlanmış
- Kanal DNA'sına göre sıralanmış ve strateji rolü atanmış

---

## 2. PIPELINE GENEL YAPISI (V4)

```
S01 → S02 → S03 → [PAUSE: kullanıcı onayı] → S04 → S05 → S06 → S07 → S08
 5%    15%   22%        awaiting                30%   65%   85%   92%  100%
```

| Adım | İsim | Model/Araç | Amaç |
|------|------|-----------|------|
| S01 | Audio Extract | FFmpeg | Video'dan ses çıkarımı |
| S02 | Transcribe | Deepgram nova-2 | Kelime bazlı transkript + diarizasyon |
| S03 | Speaker ID | Heuristik algoritma | Host/Guest tespiti |
| S04 | Labeled Transcript | Python string işleme | İnsan okunabilir transkript |
| S05 | Unified Discovery | Gemini Pro (video+text) | Klip adayları keşfi |
| S06 | Batch Evaluation | Gemini Pro (text only) | Adayları puanlama + quality gate |
| S07 | Precision Cut | FFmpeg + kelime timestamps | Kelime sınırına hizalama |
| S08 | Export | FFmpeg + boto3 + Supabase | Encode → R2 → DB |

---

## 3. JOB OLUŞTURMA VE BAŞLATMA

**Dosya**: `backend/app/api/routes/jobs.py`

### 3.1 Upload Preview (`POST /jobs/upload-preview`)

Kullanıcı video seçtiği anda çağrılır. Pipeline başlamaz, sadece video validate edilir ve süre bilgisi döner.

```
Giriş: video dosyası (multipart/form-data)
İşlem:
  1. Dosyayı UPLOAD_DIR'e kaydet
  2. ffprobe ile süreyi oku
  3. upload_id (UUID) ata

Çıkış: {upload_id, duration_seconds, file_path, filename}
```

**Amacı**: Kullanıcı job oluşturmadan önce video süresini görür. Trim aralığı girebilir.

### 3.2 Job Oluşturma (`POST /jobs`)

```
Giriş:
  - upload_id (önceden yüklendiyse) VEYA video dosyası (direkt yüklenebilir)
  - title: video başlığı
  - guest_name: misafir adı (opsiyonel, S05'te kullanılır)
  - channel_id: hangi kanal için klip çıkarılacak
  - trim_start_seconds: (opsiyonel)
  - trim_end_seconds: (opsiyonel)

İşlem:
  1. Video dosyasını doğrula (boyut, format)
  2. Trim belirtildiyse FFmpeg ile lossless copy (-c copy) yap
  3. Supabase jobs tablosuna kaydet (status: QUEUED)
  4. run_pipeline() fonksiyonunu arka planda başlat (FastAPI BackgroundTasks)

Çıkış: {job_id, status: "queued"}
```

**Neden trim önce yapılıyor?** Eğer kullanıcı "sadece 10-45. dakika arası" diyorsa, pipeline'ın geri kalanı gereksiz verilerle uğraşmasın diye trim işlemi en başta uygulanır. Bu işlem lossless'tır (yeniden encode yok).

---

## 4. S01 — SES ÇIKARIMI (Audio Extract)

**Dosya**: `backend/app/pipeline/steps/s01_audio_extract.py`

### Amaç
Video dosyasından ses parçasını ayrıştırmak. Deepgram yalnızca ses dosyasına ihtiyaç duyar; tüm videoyu göndermek gereksiz bant genişliği harcar.

### FFmpeg Komutu
```bash
ffmpeg -y -i {video_path} -vn -c:a aac -b:a 128k -movflags +faststart {output.m4a}
```

- `-vn`: video stream'i kaldır
- `-c:a aac`: AAC codec (Deepgram uyumlu)
- `-b:a 128k`: 128kbps (transkripsiyon için yeterli kalite)
- `-movflags +faststart`: dosya başından okunabilir (streaming-friendly)

### Çıktı
- `temp_{job_id}.m4a` dosyası
- Dosya varlığı doğrulanır, exit code kontrol edilir
- Hata olursa: exception fırlatılır, orchestrator FAILED yapar

### Sonraki Adıma Ne Geçiyor?
`audio_path` string'i → S02'ye gönderilir

---

## 5. S02 — TRANSKRİPSYON (Transcribe)

**Dosya**: `backend/app/pipeline/steps/s02_transcribe.py`

### Amaç
Ses dosyasını metne çevirmek. Yalnızca metin değil; kelime bazlı timestamp'ler, konuşmacı ayrıştırması (diarization) ve duygu analizi (sentiment) de çıkarılır.

### Deepgram API Parametreleri
```
Model: nova-2
diarize: true          → SPEAKER_0, SPEAKER_1, ... etiketleri
sentiment: true        → Her utterance için duygu skoru (-1.0 ile +1.0)
punctuate: true        → Noktalama işaretleri eklenir
utterances: true       → Konuşma birimleri (cümle benzeri)
words: true            → Kelime bazlı timestamps
language: en
```

### Neden nova-2?
Deepgram'ın en doğru modeli. Diarization + sentiment + word timestamps hepsini tek API çağrısında verir. Whisper gibi local model çalıştırılmaz çünkü Railway'de GPU yok.

### Çıktı Yapısı
```json
{
  "transcript": "full text string",
  "words": [
    {
      "word": "hello",
      "punctuated_word": "Hello,",
      "start": 1.23,
      "end": 1.56,
      "speaker": 0,
      "confidence": 0.97
    }
  ],
  "utterances": [
    {
      "transcript": "Hello, how are you?",
      "start": 1.23,
      "end": 3.45,
      "speaker": 0,
      "sentiment": 0.72
    }
  ],
  "duration": 3601.5,
  "raw_response": { ...tam Deepgram yanıtı... }
}
```

### S07 İçin Kritik Önem
`words` dizisi, S07 Precision Cut adımında **kelime sınırına snap** yapmak için kullanılır. Bu sayede klip ortasında bir kelime kesilmez.

---

## 6. S03 — SPEAKER ID (Konuşmacı Tespiti)

**Dosya**: `backend/app/pipeline/steps/s03_speaker_id.py`

### Amaç
Deepgram'ın tanımladığı SPEAKER_0, SPEAKER_1 gibi kimliksiz konuşmacıları HOST ve GUEST olarak eşleştirmek.

### Algoritma (Heuristik)

```
1. Her konuşmacının toplam konuşma süresini utterances'tan hesapla
2. En uzun konuşan → GUEST (misafir podcast'te daha çok konuşur)
3. İkinci uzun konuşan → HOST
4. Diğerleri → UNKNOWN
5. Eğer sadece 1 konuşmacı varsa → GUEST, onay gerekmez
```

**Neden heuristik?** Podcast/röportaj formatında misafir çoğunlukla host'tan çok konuşur. Alternatif: ses tonu analizi, ama GPU gerektirdiğinden tercih edilmez.

### Pipeline Duraklatması
S03 tamamlandığında job status → `AWAITING_SPEAKER_CONFIRM` olur.

Pipeline burada **kasıtlı olarak durur**. Kullanıcıya gösterilir:
- Her konuşmacının adı ve rolü (tahmin)
- Onay veya düzeltme yapabilir

**Neden kullanıcı onayı gerekli?**
Diarization hatalı olabilir. Yanlış bir speaker map'i ile devam edilirse transkript yanlış etiketlenir, Gemini yanlış kişiyi "misafir" zanneder ve alakasız momentleri seçer.

### Çıktı
```python
{
  "speaker_stats": {
    "SPEAKER_0": {"duration": 1200.5, "utterance_count": 45},
    "SPEAKER_1": {"duration": 800.2, "utterance_count": 30}
  },
  "predicted_map": {
    "SPEAKER_0": {"role": "guest", "name": None},
    "SPEAKER_1": {"role": "host", "name": None}
  },
  "needs_confirmation": True
}
```

### Kullanıcı Onayı Endpoint'i
`POST /jobs/{job_id}/confirm-speakers`

```json
{
  "speaker_map": {
    "SPEAKER_0": {"role": "guest", "name": "Elon Musk"},
    "SPEAKER_1": {"role": "host", "name": "Lex Fridman"}
  }
}
```

Bu endpoint çağrıldığında `resume_pipeline_from_s04()` arka planda başlar.

---

## 7. S04 — ETİKETLİ TRANSKRİPT (Labeled Transcript)

**Dosya**: `backend/app/pipeline/steps/s04_labeled_transcript.py`

### Amaç
Deepgram'ın ham JSON verisini, Gemini'nin anlayabileceği ve okuyabileceği insan-dostu metin formatına dönüştürmek.

### Çıktı Formatı
```
[00:12.3] GUEST (Elon Musk):[sentiment:-0.45] "Rockets are hard. The thing people don't realize..."
[00:28.7] HOST (Lex Fridman): "What was the hardest moment?"
[00:32.1] GUEST (Elon Musk):[sentiment:0.82] "When we almost ran out of money in 2008..."
```

### Format Detayları
- `[MM:SS.s]`: Dakika:Saniye formatında timestamp
- `GUEST (İsim)` veya `HOST (İsim)`: Rol + isim (isim biliniyorsa)
- `[sentiment:X]`: Yalnızca ±0.3 üstü duygusal yoğunlukta gösterilir (spam olmasın)
- Boş utterances filtrelenir

### S05 İçin Neden Kritik?
Gemini bu formatlı metni okur. Host/Guest ayrımı, konuşmacı ismi ve duygusal tonlama bilgisiyle clip seçimi çok daha isabetli olur.

---

## 8. S05 — UNİFİED DİSCOVERY (Klip Keşfi)

**Dosya**: `backend/app/pipeline/steps/s05_unified_discovery.py`
**Prompt dosyası**: `backend/app/pipeline/prompts/unified_discovery.py`

### Amaç
Videonun tamamını izleyerek (ve transkripti okuyarak), kanal DNA'sına ve misafir profiline uygun viral klip adaylarını keşfetmek.

**Model**: `gemini-3.1-pro-preview` — video + text input

### Neden Video + Text Birlikte?
Transkript metin olarak yeterli gibi görünse de gerçekte değil:
- Ses tonu, vurgu, duygusal yoğunluk metinde kaybolur
- Yüz ifadeleri, jest, mimik → yalnızca video'da
- Gülme, ağlama, ses kısıklığı → transkriptte görünmez
- Ani sessizlik, ritim değişikliği → yalnızca video/audio'da

Bu nedenle S05 video'yu kesinlikle gönderir.

### S05 Pipeline Aşamaları

#### 8.1 Kanal Bağlamı Oluşturma (`build_channel_context()`)

Channel DNA JSON'u okunur ve natural language'a dönüştürülür:

```
YOU ARE EDITING FOR: [audience_identity]
TONE: [tone]

PRIORITIZE THESE MOMENTS:
1. [do_list[0]]
2. [do_list[1]]
...

NEVER SELECT:
- [dont_list[0]]
- [dont_list[1]]
...

FORBIDDEN TOPICS: [no_go_zones]

HUMOR STYLE: [style]. Frequency: [frequency]. Triggers: [triggers]

DURATION PREFERENCE: Average successful clip is [avg]s. Sweet spot: [min]-[max]s.

HOOK STYLE: [hook_style]
```

Bu metin Gemini'ye "kanal kimdir, ne ister, ne istemez" bilgisini verir.

#### 8.2 Misafir Profili (`_get_guest_profile()`)

`guest_name` varsa çağrılır. Önce önbellekte aranır (7 günlük cache):

```python
# Supabase guest_profiles tablosundan kontrol
SELECT * FROM guest_profiles WHERE normalized_name = '{lower_case_name}' AND expires_at > now()
```

Önbellekte yoksa Gemini Flash ile araştırılır:

**Prompt** (guest_research.py):
```
Research {guest_name}. Return JSON:
{
  "profile_summary": "One sentence bio",
  "recent_topics": ["topic1", "topic2"],
  "viral_moments": ["Known viral moment 1"],
  "controversies": ["Controversial statement they made"],
  "expertise_areas": ["Primary expertise"],
  "clip_potential_note": "What type of moment goes viral with this guest"
}
```

Bu profil Gemini'ye "bu kişi kim, ne zaman patlar" bağlamı sağlar.

#### 8.3 Kanal Hafızası (`_get_channel_memory()`)

Son 90 günün klip verilerinden başarı oranı hesaplanır:

```sql
SELECT content_type, quality_verdict, views_7d, overall_confidence
FROM clips
WHERE channel_id = '{channel_id}'
  AND created_at > now() - interval '90 days'
```

Gemini'ye şu bilgi eklenir:
```
CHANNEL PERFORMANCE MEMORY (last 90 days):
Success rate: 67%
Best performing content_types: ["revelation", "debate"]
Avoid: ["educational_insight"] (only 12% success rate)
```

#### 8.4 Max Aday Sayısı

Video süresine göre:
```
< 15 dakika  → 15 aday
< 30 dakika  → 25 aday
< 60 dakika  → 35 aday
≥ 60 dakika  → 45 aday
```

S06'da bunlar quality gate'e tabi tutulur. Gerçek "pass" sayısı genelde 2-8 arası çıkar.

#### 8.5 Gemini'ye Video Gönderme

```
Video boyutu < 20MB → dosya bytes olarak inline gönderilir
Video boyutu ≥ 20MB → Google Cloud Storage'a yüklenir, gs:// URI gönderilir
                    → GCS dosyası finally bloğunda silinir

Fallback zinciri:
  1. Video + transkript gönder
  2. Başarısızsa: sadece ses + transkript gönder
  3. Başarısızsa: sadece transkript gönder (yalnızca metin analizi)
```

### S05 Gemini Çıktı Yapısı

```json
[
  {
    "candidate_id": 1,
    "timestamp": "12:34",
    "recommended_start": 754.2,
    "recommended_end": 812.8,
    "estimated_duration": 58.6,
    "hook_text": "The exact first sentence the viewer will hear",
    "reason": "Why this moment has viral potential for this channel's audience",
    "primary_signal": "multi",
    "strength": 9,
    "content_type": "revelation",
    "needs_context": false
  }
]
```

**primary_signal** değerleri:
- `transcript`: Yalnızca söylenenler güçlü
- `visual`: Yüz ifadesi, jest kritik
- `audio_energy`: Ses tonu, heyecan seviyesi
- `humor`: Komedi, ironi
- `multi`: Birden fazla sinyal birleşimi

---

## 9. S06 — BATCH EVALUATION (Toplu Değerlendirme)

**Dosya**: `backend/app/pipeline/steps/s06_batch_evaluation.py`
**Prompt dosyası**: `backend/app/pipeline/prompts/batch_evaluation.py`

### Amaç
S05'ten gelen ham adayları, YouTube Shorts izleyicisi gözüyle değerlendirmek. Kalite kapısından geçenleri sıralamak ve YouTube metadata'sı üretmek.

**Model**: `gemini-3.1-pro-preview` — yalnızca text

### Neden S05'ten Ayrı Bir Adım?

S05 "keşif" adımıdır — geniş bir ağ atar, potansiyelli momentleri işaretler.
S06 "değerlendirme" adımıdır — daha katı kriterlere göre eleme yapar, bağımsız biçimde puanlar.

İki ayrı adım olmasının nedeni:
- S05 videoya bakarak "bu önemli görünüyor" der
- S06 transkript parçasına bakarak "sıfır bağlamla izlenebilir mi?" diye sorar
- Farklı bakış açısı → daha güvenilir sonuç

### 9.1 Transkript Segmenti Çıkarımı

Her aday için S06'ya gönderilmeden önce:

```python
# Adayın başlangıç/bitiş zamanının ±2 dakikası alınır
window_start = candidate_start - 120
window_end = candidate_end + 120

# word_timestamps kullanılarak o penceredeki kelimeler seçilir
# Eğer word_timestamps yoksa: labeled_transcript'ten satır bazlı çıkarım yapılır
```

Bu sayede Gemini "bu klibin bağlamı ne?" sorusunu yanıtlayabilir.

### 9.2 Batch İşleme (6'lık Gruplar)

Adaylar 6'lık gruplar halinde Gemini'ye gönderilir:

```
Neden 6?
- Çok fazla aday tek seferde gönderilirse Gemini bazılarını atlayabilir
- 6, güvenilir yanıt garantisi için optimize edilmiş sayı
```

Gemini'nin atladığı adaylar tespit edilir (candidate_id karşılaştırması) ve tekrar bireysel olarak gönderilir.

### 9.3 Kalite Kapısı Kuralları

```
PASS (geçti):
  standalone_score >= 7 (bağımsız anlaşılabilir)
  hook_score >= 6       (ilk 3 saniyede dikkat çekiyor)
  arc_score >= 6        (başlangıç-gerilim-sonuç var)

FIXABLE (düzeltilebilir):
  Sınırlar 2-3 saniye kaydırılırsa geçebilir
  Genellikle hook biraz erken veya geç başlıyor

FAIL (reddedildi):
  standalone_score < 5: "Bu kişi kim?" olmadan anlaşılmıyor
  VEYA dışsal bağlam gerekiyor
  VEYA arc tamamlanmamış
```

**Reddedilen klipler silinmez.** `posting_order = 999` atanır ve DB'ye "fail" olarak kaydedilir. Kullanıcı manuel review yapabilir.

### 9.4 Puanlama Boyutları (1-10 Skala, 6 = Ortalama)

| Boyut | Soru | Eşik |
|-------|------|------|
| `standalone_score` | Bu klibi hiç bağlam olmadan izleyen anlıyor mu? | ≥ 7 |
| `hook_score` | İlk 3 saniyede scroll durur mu? | ≥ 6 |
| `arc_score` | Başlangıç → gerilim → sonuç tam mı? | ≥ 6 |
| `channel_fit_score` | Kanal kitlesi için doğru içerik mi? | (bilgi amaçlı) |
| `overall_confidence` | Genel viral potansiyel (0.0-1.0) | (sıralama için) |

### 9.5 Strateji Rolleri

Geçen kliplere otomatik rol atanır:

| Rol | Anlam | Ne Zaman Atanır |
|-----|-------|-----------------|
| `launch` | Serinin en iyi klibi, ilk paylaşılacak | Batch'in en yüksek overall_confidence'ı |
| `viral` | Yüksek viral potansiyel | Hook + standalone güçlü |
| `engagement` | Yorum ve tartışma yaratır | Controversial, debate türleri |
| `fan_service` | Mevcut izleyicilere hitap eder | Channel-specific sacred topics |

### 9.6 YouTube Metadata Üretimi

S06 Gemini prompt'unda:

```
TITLE INSTRUCTIONS:
- If channel_dna.title_style exists: "{Follow this style}"
- Else: Max 60 chars, bold claim or guest name, no emojis

DESCRIPTION INSTRUCTIONS:
- If channel_dna.description_template exists: Fill in [GUEST], [TOPIC] placeholders
- Else: 2-3 sentences summarizing the clip + 3-5 relevant hashtags
```

---

## 10. S07 — PRECİSİON CUT (Hassas Kesim)

**Dosya**: `backend/app/pipeline/steps/s07_precision_cut.py`

### Amaç
S06'dan gelen float timestamp'leri, Deepgram kelime timestamp'lerine hizalamak. Bu adım FFmpeg çalıştırmaz — **yalnızca hesaplama** yapar.

### Neden Kelime Sınırına Snap Gerekli?

Gemini "53.7 saniyeden başla" der. Ama 53.7 saniyede bir kelimenin ortası olabilir. Klip o noktadan başlarsa izleyici yarım kelime duyar. Bu amateur görünür.

### Snap Algoritması

```
Her aday için:
  1. recommended_start için:
     - 3 saniyelik pencerede (start-3 to start+3) kelimeleri ara
     - Hedefin öncesindeki en yakın kelime_start'ı bul
     - Skor: mesafe azaldıkça artar, hedefi geçmek cezalandırılır

  2. recommended_end için:
     - 3 saniyelik pencerede kelime_end'leri ara
     - Hedefin sonrasındaki en yakın kelime_end'i bul

  3. Nefes bufferları uygula:
     - Start: -0.3 saniye (konuşmadan önce doğal duraklama)
     - End: +0.5 saniye (konuşmacının tepkisini yakala)

  4. Süre limitleri uygula:
     - Min: 12 saniye
     - Max: 60 saniye
     - Aşılırsa: end sıkıştır

  5. Video süresine kısıtla (ffprobe ile alınır)
```

### Çıktı

```python
{
  "final_start": 53.4,      # kelime sınırına hizalanmış
  "final_end": 89.1,        # kelime sınırına hizalanmış
  "final_duration_s": 35.7
}
```

---

## 11. S08 — EXPORT (Dışa Aktarım)

**Dosya**: `backend/app/pipeline/steps/s08_export.py`

### Amaç
Her klip için: frame-accurate kesim + yüksek kalite encode + Cloudflare R2'ye yükleme + Supabase'e kaydetme.

### FFmpeg Komutu (Klip Başına 1 Kez)

```bash
ffmpeg -y \
  -ss {final_start} \
  -i {video_path} \
  -t {final_duration} \
  -c:v libx264 -preset slow -crf 18 \
  -c:a aac -b:a 320k \
  -movflags +faststart \
  -pix_fmt yuv420p \
  -avoid_negative_ts make_zero \
  -map 0:v:0 -map 0:a:0 \
  output/clip_{index}_{content_type}.mp4
```

**Neden bu parametreler?**
- `-ss` önce `-i`'den: Input seeking (hızlı, frame-accurate)
- `-c:v libx264 -preset slow -crf 18`: Görsel kayıpsız H.264 (CRF 18 = çok yüksek kalite)
- `-c:a aac -b:a 320k`: 320kbps AAC ses (en yüksek pratik kalite)
- `-movflags +faststart`: Web'de streaming için optimize
- `-pix_fmt yuv420p`: Tüm player'larla uyumluluk
- `-avoid_negative_ts make_zero`: Negatif timestamp hatasını önler
- `-t {duration}` (end değil): `-t` duration kullanmak daha güvenilir

**Neden sadece S08'de encode?**
S07 lossless copy kullanır (hızlı, kalitesiz değil). Tek encode prensibi: her encode kalite kaybı demektir. Encode sadece son adımda yapılır.

### R2 Yükleme

```python
boto3 client:
  endpoint_url: https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com
  bucket key: {job_id}/{filename}

Sonuç URL: {R2_PUBLIC_URL}/{job_id}/{filename}
# Örnek: https://pub-abc.r2.dev/job_123/clip_01_revelation.mp4
```

### Supabase'e Kayıt

Her klip için `clips` tablosuna INSERT:

```python
{
  "job_id": uuid,
  "channel_id": str,
  "clip_index": int,          # sıra numarası (0'dan başlar)
  "start_time": float,
  "end_time": float,
  "duration_s": float,
  "hook_text": str,           # ilk cümle
  "content_type": str,        # revelation, debate, humor, ...
  "confidence": float,        # overall_confidence
  "standalone_score": int,
  "hook_score": int,
  "arc_score": int,
  "channel_fit_score": int,
  "overall_confidence": float,
  "thinking_steps": list,     # Gemini'nin düşünce adımları
  "quality_verdict": str,     # pass / fixable / fail
  "clip_strategy_role": str,  # launch / viral / engagement / fan_service
  "posting_order": int,       # pass = 1,2,3... | fail = 999
  "suggested_title": str,
  "suggested_description": str,
  "file_url": str,            # R2 public URL
  "is_successful": bool,
  "why_failed": str | None
}
```

### Hata Yönetimi S08'de

```python
try:
    ffmpeg_result = subprocess.run(...)
    upload_url = r2_client.upload(...)
    supabase.insert(clip_data)
except Exception as e:
    print(f"[S08] Clip {i} failed: {e}")
    # DEVAM ET — bir klipin başarısız olması diğerlerini durdurmaz
finally:
    if os.path.exists(local_clip_path):
        os.remove(local_clip_path)  # her durumda temizle
```

---

## 12. ORCHESTRATOR (Pipeline Yöneticisi)

**Dosya**: `backend/app/pipeline/orchestrator.py`

### İki Entry Point

#### `run_pipeline(job_id, video_path, video_title, guest_name, channel_id)`
S01'den S03'e kadar çalışır, S03 sonunda durur.

#### `resume_pipeline_from_s04(job_id, confirmed_speaker_map)`
S04'ten S08'e kadar devam eder.

### Job Status Geçişleri

```
QUEUED
  ↓ run_pipeline() başlar
PROCESSING (S01-S03 çalışıyor)
  ↓ S03 tamamlandı
AWAITING_SPEAKER_CONFIRM
  ↓ kullanıcı /confirm-speakers çağırdı
PROCESSING (S04-S08 çalışıyor)
  ↓ S08 tamamlandı
COMPLETED
```

Herhangi bir adımda hata → `FAILED` + `error_message`

### Audit Logging

Her adım için `pipeline_audit_log` tablosuna kayıt:

```python
{
  "job_id": str,
  "step_number": int,
  "step_name": str,
  "status": "started" | "completed" | "failed",
  "duration_ms": int,
  "input_summary": {}, # hangi verilerle başladı
  "output_summary": {}, # ne üretti
  "error_message": str | None,
  "error_stack": str | None
}
```

---

## 13. KANAL DNA (Channel DNA) SİSTEMİ

**Tablo**: `channels.channel_dna` (JSONB)

### Yapısı

```json
{
  "audience_identity": "Girişimci ve startup kurucuları, 25-40 yaş",
  "tone": "educational, slightly irreverent",
  "do_list": [
    "Underdog stories — sıfırdan zirveye",
    "Gelir/monetizasyon detayları",
    "Misafirin karşıt görüşleri",
    "Başarısızlık ve şüphe anları"
  ],
  "dont_list": [
    "İş ile ilgisiz ünlü dedikodular",
    "Sonuçsuz felsefi tartışmalar",
    "Derin teknik anlatımlar (izleyici teknik değil)"
  ],
  "no_go_zones": ["siyaset", "sağlık iddiaları", "finansal tavsiye"],
  "best_content_types": ["revelation", "debate", "emotional", "storytelling"],
  "humor_profile": {
    "style": "general",
    "frequency": "occasional",
    "triggers": ["ironic statements", "unexpected punchlines"]
  },
  "duration_range": {"min": 45, "max": 120},
  "avg_successful_duration": 75,
  "speaker_preference": "guest_dominant",
  "hook_style": "bold_claim_or_curiosity_gap",
  "sacred_topics": ["mental health", "relationships", "burnout"],
  "title_style": "{İsim}: {Cesur İddia} (max 60 karakter, emoji yok)",
  "description_template": "{Guest} {topic} hakkında konuşuyor. [2-3 cümle]. #podcast #{tag}"
}
```

### Nasıl Oluşturuluyor?

Kanal onboarding sırasında `reference_analyzer.py` çalışır:
1. Kanalın YouTube'daki başarılı short'larından (en fazla 20 adet) transkript çıkarılır
2. Transkriptler + performans verileri Gemini Flash'a gönderilir
3. Gemini kanal DNA JSON'unu oluşturur

### S05 ve S06'da Kullanımı

- S05: `build_channel_context()` ile natural language'a dönüştürülür ve Gemini'nin system context'ine eklenir
- S06: Batch evaluation prompt'una dahil edilir (title_style ve description_template)
- Her ikisi de: "CHANNEL CONTEXT IS LAW" prensibiyle çalışır

---

## 14. MİSAFİR PROFİLİ (Guest Profile)

**Tablo**: `guest_profiles`

### Alanlar
```
normalized_name  → küçük harfle lookup için ("elon musk")
original_name    → görünen isim ("Elon Musk")
profile_data     → JSON:
  profile_summary     → tek cümle bio
  recent_topics       → son güncel konular
  viral_moments       → bilinen viral anları
  controversies       → tartışmalı konuları
  expertise_areas     → uzmanlık alanları
  clip_potential_note → bu kişi ne zaman viral olur
expires_at       → 7 gün sonra yenilenir
```

### Amacı

S05'te Gemini'ye "bu misafir kim, ne zaman patlar" bağlamı sağlar. Gemini bu sayede:
- Misafirin güçlü olduğu konularda klip önerir
- Misafirin önceki viral anlarına benzer yapıları arar
- Tartışmalı konuları fark eder

---

## 15. PUANLAMA VE SIRALAMA SİSTEMİ

### Klip Puanları (1-10)

| Puan | Anlam |
|------|-------|
| 9-10 | Exceptional |
| 7-8 | Strong |
| 5-6 | Average |
| 3-4 | Weak |
| 1-2 | Very poor |

**6 = Ortalama** (YouTube'daki tipik klip)

### posting_order Atama Mantığı

```python
pass_clips = sorted(by overall_confidence DESC)
for i, clip in enumerate(pass_clips):
    clip.posting_order = i + 1  # 1, 2, 3...

for clip in fail_clips:
    clip.posting_order = 999
```

### clip_strategy_role Atama

```python
if clip == max(all_clips, key=overall_confidence):
    role = "launch"     # İlk paylaşılacak
elif clip.hook_score >= 8 and clip.standalone_score >= 8:
    role = "viral"      # En yüksek viral potansiyel
elif clip.content_type in ["debate", "controversial"]:
    role = "engagement" # Yorum ve tartışma
else:
    role = "fan_service" # Mevcut izleyiciye
```

---

## 16. DOSYA DEPOLAMA SİSTEMİ

### Geçici Dosyalar (Pipeline Süresi)
```
uploads/{job_id}/          → Yüklenen orijinal video (pipeline bitince silinir)
temp_{job_id}.m4a          → S01 audio (S02 sonrası silinir)
output/{job_id}/clip_X.mp4 → S08 encode (R2'ye yüklendikten sonra silinir)
```

### Kalıcı Depolama (Cloudflare R2)
```
Bucket key: {job_id}/{filename}
Public URL: https://pub-xxx.r2.dev/{job_id}/clip_01_revelation.mp4
```

R2 dosyaları silinmez (kullanıcı klibi her zaman playback edebilmeli).

### Supabase
Tüm metadata kalıcıdır. Video binary'si asla Supabase'e kaydedilmez.

---

## 17. MODEL KULLANIMI VE GEMİNİ RATE LIMITING

### Model Seçimi

| Adım | Model | Neden |
|------|-------|-------|
| S05 Discovery | `gemini-3.1-pro-preview` | Video anlama kritik |
| S06 Evaluation | `gemini-3.1-pro-preview` | Text reasoning kritik |
| Guest Research | `gemini-2.5-flash` | Basit araştırma |
| Channel DNA | `gemini-2.5-flash` | Analiz ama video yok |
| YouTube Metadata | `gemini-2.5-flash` | Kısa metin görevi |

### Rate Limit Yönetimi

```python
for attempt in range(3):
    try:
        response = gemini.generate(...)
        break
    except RateLimitError:
        if attempt == 0: sleep(30)
        elif attempt == 1: sleep(60)
        else: raise RuntimeError("Gemini rate limit exceeded")
```

---

## 18. CONTENT TYPE KATALOĞU

Gemini'nin kullanabileceği içerik türleri:

| Type | Açıklama |
|------|---------|
| `revelation` | Şok edici gerçek, beklenmedik bilgi |
| `debate` | Karşıt görüşler, tartışma |
| `humor` | Komedi, ironi, beklenmedik çıkış |
| `insight` | Derin düşünce, perspektif değişimi |
| `emotional` | Duygusal yoğunluk, güçlü an |
| `controversial` | Tartışmalı iddia |
| `storytelling` | Anlatı, hikaye |
| `celebrity_conflict` | Ünlü çatışması |
| `hot_take` | Cesur görüş |
| `funny_reaction` | Komik tepki |
| `unexpected_answer` | Beklenmedik yanıt |
| `relatable_moment` | Herkesin tanıdığı an |
| `educational_insight` | Öğretici bilgi |

---

## 19. PERFORMANS VERİLERİ VE GERİ BESLİM

### Clips Tablosundaki Performance Alanları

```sql
views_48h    INT     -- Yayınlandıktan 48 saat sonra görüntülenme
views_7d     INT     -- 7 gün sonra görüntülenme
avd_pct      FLOAT   -- Average View Duration yüzdesi
```

### Feedback Döngüsü

`feedback.py` route'u:
1. Kullanıcı klibi yayınladığında `published_at`, `youtube_video_id` kaydeder
2. Performans verileri manuel veya API ile girilebilir
3. S05'te `_get_channel_memory()` bu verileri okur
4. Başarısız content_type'lar bir sonraki pipeline'da daha az tercih edilir

---

## 20. DIRECTOR İÇİN ANALİZ NOKTALARI

Modül 1'in verimliliği şu metriklerle ölçülebilir:

| Metrik | Nasıl Hesaplanır | Hedef |
|--------|-----------------|-------|
| Pass Rate | pass_clips / total_candidates | > %40 |
| Avg standalone_score | mean(standalone_scores) | > 7.5 |
| Avg hook_score | mean(hook_scores) | > 7.0 |
| S05 Candidate Accuracy | pass_count / candidate_count | > %30 |
| S06 Skip Rate | skipped_candidates / batch_size | < %10 |
| Export Success Rate | exported_clips / pass_clips | > %95 |
| R2 Upload Fail Rate | failed_uploads / exports | < %2 |
| Avg Processing Time | S01→S08 toplam süre | < 8 dakika |

### Potansiyel İyileştirme Alanları

1. **S05 Video Fallback Oranı**: Video yerine transkript kullanılıyorsa kalite düşer
2. **S06 Batch Skip Oranı**: Gemini'nin atladığı adaylar sapma yaratır
3. **Channel DNA Güncelliği**: DNA eski referanslarla oluşturulduysa bozulur
4. **Guest Cache Hit Rate**: Yeniden araştırma gereksiz API harcatır
5. **Word Snap Başarısızlıkları**: Kelime timestamp'i yoksa snap yapılamaz

---

*Bu döküman her Modül 1 güncellemesinde ilgili bölümler değiştirilerek güncel tutulmalıdır.*
