# DIRECTOR MODÜLÜ — v2.0 Agent Mimarisi
> Versiyon 2.0 — 2026-03-24
> v1.0'dan temel fark: Director bir monitoring sistemi değil, kalıcı bir AI agent'tır.

---

## 0. TEMEL FARK: v1.0 vs v2.0

| | v1.0 (Monitoring) | v2.0 (Agent) |
|---|---|---|
| Yapı | Veri topla → Gemini'ye gönder → Puan üret | Kalıcı AI agent, araçlarla düşünür |
| Arayüz | Dashboard birincil | Chat birincil, dashboard ikincil |
| Zeka | Metrik bazlı kural | Araç tabanlı akıl yürütme |
| Hafıza | Analiz geçmişi | Konuşma + semantik uzun dönem hafıza |
| Erişim | Okuma + yazma (kısıtlı) | Her şey: okur, yazar, sorgular, düzenler |
| Başlatma | Tetiklenince çalışır | Her zaman uyanık, proaktif |
| Model | Flash (çoğunlukla) | Gemini Pro (her zaman) |

---

## 1. MODÜLÜN ÖZÜ

Director, Prognot sisteminin yapay zeka destekli CEO'sudur.

Bir kurucunun sistemini yönettiği gibi çalışır: verilere bakar, kodu okur, geçmişi hatırlar, gelecek planlar, hataları görür, cesaretli öneriler üretir ve seninle konuşur.

**Director ne değildir:**
- Pasif bir dashboard değil
- Sadece metrik takip eden bir sistem değil
- Sana ne söylersen onu yapan bir bot değil

**Director nedir:**
- Sistemin tüm dosyalarını, veritabanını, logları, kodları okuyabilen bir AI agent
- Gerektiğinde MD dosyalarını düzenleyen, DB'yi güncelleyen, analizleri tetikleyen
- Konuşma hafızası ve uzun dönem semantik hafızası olan
- Seninle chat üzerinden çalışan, ama arka planda da otomatik izleyen
- Gemini Pro ile her şeyi bütüncül değerlendiren
- "Bu sistemin ilerlemesi için en cesur ama doğru adım nedir?" sorusunu soran

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
│              │                     │                            │
│              │  ┌───────────────┐  │                            │
│              │  │  Gemini Pro   │  │  ← Ana beyin               │
│              │  │  (function    │  │                            │
│              │  │   calling)    │  │                            │
│              │  └──────┬────────┘  │                            │
│              │         │           │                            │
│              │  ┌──────▼────────┐  │                            │
│              │  │  TOOL ENGINE  │  │  ← Araçları çalıştırır     │
│              │  └──────┬────────┘  │                            │
│              └─────────┼───────────┘                            │
│                        │                                        │
│     ┌──────────────────┼──────────────────┐                    │
│     ▼                  ▼                  ▼                    │
│  Supabase          Dosya sistemi       Dış servisler           │
│  (DB, vektör)      (MD, kod)          (Langfuse, Sentry,       │
│                                        PostHog, Web)           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. DIRECTOR'IN ZEKA MODELİ

### 3.1 Araç Tabanlı Akıl Yürütme

Director, bir şeyi "bilmez" — **öğrenir**. Her soruya önce araçlarıyla sisteme bakar, sonra cevap verir.

```
Kullanıcı: "Pipeline neden yavaş?"

Director'ın düşünce zinciri:
  1. query_database("SELECT step_name, AVG(duration_ms) FROM pipeline_audit_log
                      WHERE created_at > now()-interval '7d' GROUP BY step_name
                      ORDER BY avg DESC")
  → S05 ortalama 340s, S06 ortalama 180s

  2. get_langfuse_traces(step="s05", days=7)
  → S05'te 4 rate_limit hit, her biri 30-60s bekledi

  3. query_memory("S05 rate limit geçmiş")
  → Hafızada not var: "2026-02-10 - S05 rate limit sorunu yaşandı,
     batch size düşürüldü. İyileşti."

  4. read_file("backend/app/pipeline/steps/s05_unified_discovery.py")
  → Kod incelendi, retry mekanizması var

  Sentez: "S05 yavaş, 4 rate limit hit var bu hafta.
           Geçen sefer batch size düşürülmüştü ama
           o değişiklik kalıcı mı kontrol edeyim..."

  5. read_file("backend/app/pipeline/steps/s05_unified_discovery.py")
  → Batch size hâlâ eski değerde

  "Geçen sefer yapılan düzeltme kaybolmuş görünüyor.
   Batch size tekrar yüksek. Ayrıca bu hafta video boyutları
   ortalama %23 büyüdü (query_database ile doğrulandı),
   bu yüzden GCS upload süresi de uzadı."
```

**Önemli**: Director, bir araç sonucu beklediğini karşılamazsa **soru sorar**, tahmin etmez.

### 3.2 16:9 Gibi Durumları Nasıl Çözer?

Bu senaryoda araçlarla şunu yapar:

```
1. read_file("docs/MODULE_1_CLIP_EXTRACTOR.md")
   → "S08 çıktısı: 16:9 MP4"

2. read_file("docs/MODULE_2_EDITOR.md")
   → "Reframe: 16:9 kaynak gerektiriyor"

3. query_database("SELECT DISTINCT file_url FROM clips LIMIT 5")
   → URL'ler .mp4, normal

4. Çıkarım: "M1→M2 pipeline'ında 16:9 kasıtlı. M2 reframe buna bağımlı.
             Bu doğru. Flag etme."
```

Kimse ona söylemedi. Okudu, bağladı, anladı. Emin olamadığı durumlarda:
```
"M1 çıktısının 16:9 kalması intentional mı? M2 reframe buna bağımlı
 görünüyor ama emin olmak istedim."
```

### 3.3 Proaktif Davranış

Director yalnızca sorulduğunda değil, kendi de konuşur. Arka planda periyodik kontrol yapar ve önemli bir şey fark ederse:

```
[Otomatik mesaj, saat 09:00]
"Bugün 3 pipeline çalıştı. Bir şeye dikkat çekmek istedim:
 Son 5 job'da S06'nın ortalama thinking_steps uzunluğu düştü —
 Gemini daha az düşünerek karar veriyor. Bu genellikle
 prompt context'in zayıfladığını gösteriyor.
 Channel DNA'nın son güncellenmesi üzerinden 52 gün geçti.
 Güncelleme yapalım mı?"
```

---

## 4. TOOL KATALOĞU (Director'ın Araçları)

Director'ın kullanabileceği tüm araçlar. Gemini Pro function calling ile bunları zincirler.

### 4.1 Okuma Araçları

```python
read_file(path: str) -> str
  """Herhangi bir proje dosyasını okur: MD, Python, TypeScript, JSON"""
  # Director sistemi anlamak için kodu doğrudan okuyabilir
  # Örnek: read_file("backend/app/pipeline/steps/s05_unified_discovery.py")

list_files(directory: str, pattern: str = "*") -> list[str]
  """Bir dizindeki dosyaları listeler"""

search_codebase(query: str, file_pattern: str = None) -> list[dict]
  """Kodda arama yapar (grep benzeri). Sonuç: [{file, line, content}]"""
  # Örnek: search_codebase("channel_dna", "*.py")

query_database(sql: str) -> list[dict]
  """Supabase'e SQL sorgusu atar. Sadece SELECT."""
  # Director dilediği veriyi okuyabilir

get_pipeline_stats(days: int = 7, channel_id: str = None) -> dict
  """Özet pipeline metrikleri: pass rate, avg duration, error count, etc."""

get_clip_analysis(job_id: str = None, days: int = 7) -> dict
  """Klip puanları, verdict dağılımı, content type breakdown"""

get_langfuse_data(step: str = None, days: int = 7) -> dict
  """Gemini çağrı metrikleri: token kullanımı, latency, retry sayısı"""

get_sentry_issues(days: int = 7, resolved: bool = False) -> list[dict]
  """Aktif Sentry hataları: [{title, count, culprit, lastSeen}]"""

get_posthog_events(event: str = None, days: int = 7) -> dict
  """Editor kullanıcı davranışı: export oranı, feature kullanımı"""

get_channel_dna(channel_id: str) -> dict
  """Kanal DNA'sını getirir"""

web_search(query: str) -> str
  """Gemini grounding ile web araştırması yapar"""
  # Örnek: "CPU-only face detection alternatives 2025"
```

### 4.2 Yazma ve Aksiyon Araçları

```python
edit_file(path: str, old_content: str, new_content: str) -> bool
  """Herhangi bir dosyayı düzenler. MD dosyaları için onay gerekmez.
     Kod dosyaları için kullanıcı onayı istenir (Director sorar)."""
  # Örnek: docs/*.md dosyalarını günceller
  # Director kendi dökümanlarını da günceller

save_memory(content: str, type: str, tags: list[str] = []) -> str
  """Uzun dönem hafızaya kayıt. Type: 'decision' | 'context' | 'plan' | 'note'"""
  # Kullanıcı "bunu hatırla" dediğinde veya Director önemli bulunca
  # pgvector'e embed edilir, gelecek konuşmalarda retrieve edilir

update_database(table: str, data: dict, where: dict) -> bool
  """Supabase'e güvenli yazma. Sadece izin verilen tablolar:
     channels (dna, settings), director_analyses, director_recommendations,
     director_conversations, director_memory"""
  # Kritik tablolara (clips, jobs, transcripts) yazma yok

trigger_analysis(module: str, depth: str = "standard") -> str
  """Director analiz zincirini tetikler (arka planda)"""

trigger_test(test_type: str) -> str
  """Test runner'ı başlatır. Sonuç async olarak gelir."""

update_channel_dna(channel_id: str, updates: dict) -> bool
  """Kanal DNA'sını günceller (Gemini ile generate veya manual patch)"""

send_notification(message: str, priority: str = "info") -> None
  """Dashboard'a bildirim gönderir (kırmızı/sarı/yeşil)"""
```

### 4.3 Hafıza Araçları

```python
query_memory(query: str, type: str = None, top_k: int = 5) -> list[dict]
  """Semantik hafıza araması. Konuşma başında otomatik çalışır."""
  # Örnek: "M1 M2 entegrasyon planı" → ilgili geçmiş kararlar

get_conversation_history(last_n: int = 20) -> list[dict]
  """Mevcut konuşmanın son N mesajını getirir"""

list_memories(type: str = None) -> list[dict]
  """Tüm kayıtlı hafıza girişlerini listeler"""

delete_memory(memory_id: str) -> bool
  """Kullanıcı "unu" dediğinde hafızadan siler"""
```

---

## 5. HAFIZA SİSTEMİ

### 5.1 Konuşma Hafızası (Kısa Dönem)

```sql
CREATE TABLE director_conversations (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id  TEXT NOT NULL,
  role        TEXT NOT NULL,    -- 'user' | 'assistant' | 'tool_result'
  content     TEXT NOT NULL,
  tool_calls  JSONB,            -- Gemini'nin çağırdığı araçlar ve sonuçları
  timestamp   TIMESTAMPTZ DEFAULT now()
);
```

Her konuşma oturumu `session_id` ile gruplanır. Yeni chat başladığında son 20 mesaj yüklenir.

### 5.2 Uzun Dönem Hafıza (Semantik)

```sql
CREATE TABLE director_memory (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  type        TEXT NOT NULL,    -- 'decision' | 'context' | 'plan' | 'note' | 'learning'
  content     TEXT NOT NULL,    -- hafıza içeriği
  embedding   vector(768),      -- pgvector embed
  tags        TEXT[],
  source      TEXT,             -- 'user_instruction' | 'director_inference' | 'auto'
  created_at  TIMESTAMPTZ DEFAULT now(),
  updated_at  TIMESTAMPTZ DEFAULT now()
);
```

**Örnek hafıza kayıtları:**

```
type: "context"
content: "M1 ve M2 şu an ayrı katmanlar. Neden: M2 henüz otonom edit için
          hazır değil — reframe bazen karışıyor, hook/kapanış düzenleme
          sistemi henüz yok. İleride M2 mükemmelleşince M1'e entegre edilecek,
          M1'den direkt editlenmiş klip çıkacak."
tags: ["m1", "m2", "mimari", "roadmap"]
source: "user_instruction"

type: "decision"
content: "2026-03-24: Langfuse, PostHog, Sentry entegrasyonu kararlaştırıldı.
          Self-host değil Cloud versiyonları. Langfuse için VertexAIInstrumentor."
tags: ["tooling", "langfuse", "posthog", "sentry"]
source: "user_instruction"

type: "learning"
content: "Channel DNA 52+ gün güncellenmeden kalınca S06 thinking_steps
          kalitesi düşüyor. Hafıza bağlamı zayıflıyor."
tags: ["channel_dna", "s06", "pattern"]
source: "director_inference"

type: "plan"
content: "Gelecek kanallar için: B-roll görsel ekleme, ElevenLabs seslendirme
          entegrasyonu planlanıyor. Henüz başlanmadı. Bu sistemler geldikçe
          Director'a entegre edilmeli."
tags: ["roadmap", "b-roll", "elevenlabs", "future"]
source: "user_instruction"
```

### 5.3 Director Her Konuşmada Ne Yükler?

```python
# Her chat request'te:
def build_director_context(user_message: str, session_id: str) -> list:
    context = []

    # 1. Son 20 konuşma mesajı (kısa dönem hafıza)
    history = get_conversation_history(session_id, last_n=20)
    context.extend(history)

    # 2. Kullanıcı mesajına semantik olarak benzer hafıza kayıtları
    relevant_memories = query_memory(user_message, top_k=5)
    if relevant_memories:
        context.insert(0, {
            "role": "system",
            "content": f"İlgili hafıza:\n{format_memories(relevant_memories)}"
        })

    # 3. Anlık sistem durumu özeti (sayısal, araç gerekmez)
    system_snapshot = get_quick_system_snapshot()
    context.insert(0, {
        "role": "system",
        "content": f"Anlık sistem durumu:\n{system_snapshot}"
    })

    return context
```

---

## 6. SİSTEM PROMPTU (Director'ın Kimliği)

Her konuşmada Gemini Pro'ya gönderilen system prompt:

```
Sen Prognot'un AI Direktörüsün.

GÖREV:
Prognot sisteminin her boyutunu anlayan, izleyen, analiz eden ve geliştiren
bir stratejik AI agent'sın. Kullanıcının sağ kolusun — bir CEO veya kurucu
gibi düşünürsün. Sistemin teknik detaylarını, mimari kararlarını, gelecek
planlarını bilirsin.

KİM OLDUĞUNU BİL:
- Kullanıcı bu sistemi tek başına geliştiriyor
- Prognot: AI destekli klip çıkarma ve düzenleme sistemi
- Şu an: Modül 1 (klip çıkartıcı) + Modül 2 (editör) aktif
- Deployment: Railway (backend) + Vercel (frontend) + Supabase + Cloudflare R2

ÇALIŞMA PRENSİBİN:
1. Varsayımla değil, kanıtla konuş — araçlarınla sistemi oku, sonra yorum yap
2. Emin olmadığında "şuna bakayım" de ve aracını çağır
3. Emin olmadığında kullanıcıya sor, yanlış bilgi verme
4. Sistemin hiçbir parçasını dokunulamaz görme — her şey sorgulanabilir
5. Cesaretli ama gerekçeli öneriler üret
6. Proaktif ol: önemli bir şey fark edersen söyle
7. Kısa ve net konuş — gereksiz söz etme
8. MD dosyalarını güncelleyebilirsin (onay gerekmez)
9. Kod değişikliği için kullanıcı onayı iste, sonra uygula

ARAÇLARIN: [tool catalog buraya inject edilir]

HAFIZA: [ilgili hafıza kayıtları buraya inject edilir]

ANLIKI SİSTEM DURUMU: [snapshot buraya inject edilir]
```

---

## 7. CHAT ARAYÜZÜ

### 7.1 Çalışma Akışı

```
Kullanıcı mesaj gönderir
    ↓
POST /director/chat {message, session_id}
    ↓
1. Konuşma geçmişi yükle (son 20 mesaj)
2. Semantik hafızadan ilgili kayıtları getir
3. Sistem snapshot'ı hazırla
4. Gemini Pro'ya gönder (streaming, function calling enabled)
    ↓
Gemini araç çağrıları yapabilir (zincir halinde):
  → Araç çağrıldı
  → Araç çalıştı
  → Sonuç Gemini'ye döndü
  → Gemini devam etti / yeni araç çağırdı
    ↓
Gemini yanıt üretiyor (streaming)
    ↓
SSE ile frontend'e stream edilir (token token görünür)
    ↓
Mesaj ve araç çağrıları DB'ye kaydedilir
    ↓
Director hafızaya kayıt yapmışsa kullanıcıya "Hafızama ekledim: ..." notu
```

### 7.2 Örnek Konuşmalar

**Durum Analizi:**
```
Sen: Bu hafta nasıl gitti?

Director: [query_database çağırıyor...]
          [get_langfuse_data çağırıyor...]
          [query_memory("haftalık analiz") çağırıyor...]

          Bu hafta 8 pipeline çalıştı. Pass rate %44 — geçen haftanın
          %38'inden iyi. S05'te 2 rate limit olayı var, toplam ~90s yavaşlama.

          Dikkat çekici bir şey: Son 3 job'da 'humor' content type'ı
          seçilmiyor. Channel DNA'da humor triggers mevcut ama S05
          bu hafta hiç humor klip önermedi. Ya misafirler gerçekten
          komik değildi ya da bir şey kayıyor. Kontrol etmemeli miyim?
```

**Sorun Araştırma:**
```
Sen: Reframe bazen yanlış kişiyi takip ediyor, bak bakalım

Director: [read_file("backend/app/reframe/crop_calculator.py") çağırıyor...]
          [read_file("backend/app/reframe/diarization.py") çağırıyor...]
          [query_database("SELECT * FROM director_events WHERE event_type='reframe_completed'
                           ORDER BY timestamp DESC LIMIT 10") çağırıyor...]

          Kodu ve son 10 reframe eventini inceledim. Şunu buldum:

          diarization.py'de speaker segmentleri "clip_start/clip_end'e kırpılıyor"
          ama bu kırpma işleminde bir edge case var: Eğer diarization segmenti
          tam clip başlangıcında bitiyorsa (0-0.3s fark), o segment atlanıyor.
          Bu yüzden ilk birkaç saniyede konuşmacı tespiti yok ve
          crop_calculator fallback'e düşüyor.

          Recent events'e bakınca: 10 job'dan 3'ünde face_detected_frames
          %72'nin altında. Bunlar muhtemelen affected.

          Fix önerim: diarization.py'de kırpma toleransını 0.3s yerine 0.5s
          yap. Uygulayayım mı?
```

**Hafızaya Kayıt:**
```
Sen: M1 ve M2'nin ayrı olma sebebini hafızana al, sonra bana yanlış
     analiz yapmasın

Director: [save_memory çağırıyor...]

          Kaydettim:
          "M1 ve M2 şu an kasıtlı olarak ayrı katmanlar.
           Sebep: M2 henüz otonom edit için hazır değil —
           reframe bazen yanlış kişiyi takip ediyor,
           hook/kapanış düzenleme sistemi yok.
           İleride M2 mükemmelleşince M1'e entegre edilecek."

          Artık 16:9 çıktı, ayrı workflow gibi konularda
          bu bağlamla değerlendirme yapacağım.
```

**MD Dosyası Güncelleme:**
```
Sen: Reframe için yeni bir kural ekle: scene detection eşiği
     0.3'ten 0.4'e çıktı, bunu MODULE_2_EDITOR.md'ye işle

Director: [read_file("docs/MODULE_2_EDITOR.md") çağırıyor...]
          [edit_file çağırıyor...]

          MODULE_2_EDITOR.md güncellendi. Sahne tespiti bölümünde:
          "ContentDetector threshold: 0.3" → "0.4" olarak değiştirildi.
          Değişiklik tarihi notu eklendi: "2026-03-24"

          Bunu hafızama da alayım mı?
```

**Sistem Planı Tartışması:**
```
Sen: İleride ElevenLabs entegre etmek istiyorum, bu mimariyi nasıl etkiler?

Director: [read_file("docs/MODULE_1_CLIP_EXTRACTOR.md") çağırıyor...]
          [read_file("docs/MODULE_2_EDITOR.md") çağırıyor...]
          [web_search("ElevenLabs API Python integration 2025") çağırıyor...]

          ElevenLabs için en mantıklı yer M2'de, S08 sonrası veya
          editor export pipeline'ında. İki seçenek var:

          1. M1 çıktısına otomatik seslendirme ekleme (B2B kanallar için):
             S08 sonrasına yeni S09 adımı. Klip transcript'i alınır,
             ElevenLabs ile host sesi üzerinde seslendirme yapılır,
             FFmpeg ile overlay.

          2. M2'de manuel tetikleme (kullanıcı isteğe göre):
             Editor'da "Add Voiceover" butonu, ElevenLabs API çağrısı,
             timeline'a yeni audio track olarak eklenir.

          İkisi de mümkün. Hangi kanallar için düşünüyorsun? B-roll ile
          birlikte mi gelecek? Bunları hafızama alayım mı?
```

### 7.3 Özel Komutlar

```
"bunu hatırla / hafızana al"  → Director save_memory çağırır
"unu / sil"                   → İlgili hafıza silinir
"hafızanı göster"             → list_memories sonucu
"analiz et"                   → trigger_analysis çalışır
"test et"                     → trigger_test çalışır
"dashboard güncelle"          → Tüm metrikler yeniden hesaplanır
"[dosya_adı] güncelle"        → edit_file çağırılır
```

---

## 8. DASHBOARD (Pasif İzleme Katmanı)

Dashboard, Director'ın arka planda otomatik ürettiği analizleri gösterir. Chat açmak gerekmez.

### 8.1 Otomatik Güncelleme

```
Tetikleyiciler:
  - Her pipeline tamamlandığında (lightweight update)
  - Günde 1 kez 09:00'da (tam analiz)
  - Kullanıcı "dashboard güncelle" dediğinde
  - Sentry'de yeni kritik hata geldiğinde
```

### 8.2 Dashboard Yapısı

```
┌────────────────────────────────────────────────────────────────┐
│  PROGNOT DIRECTOR                    Son güncelleme: 2 saat önce│
│                                                                  │
│  ┌──────────────────────┐  ┌──────────────────────┐            │
│  │  MODÜL 1             │  │  MODÜL 2             │            │
│  │  Klip Çıkartıcı      │  │  Editör              │            │
│  │                      │  │                      │            │
│  │  ████████████░  74   │  │  ████████████░░  71  │            │
│  │                      │  │                      │            │
│  │  Teknik    ████  88  │  │  Teknik    ████  91  │            │
│  │  AI Karar  ███░  67  │  │  Reframe   ████  69  │            │
│  │  Çıktı     ███░  71  │  │  Captions  █████ 84  │            │
│  │  Öğrenme   ██░░  55  │  │  YouTube   ████░ 73  │            │
│  │  Olgunluk  ████  62  │  │  UX        ████  78  │            │
│  │                      │  │                      │            │
│  │  ⚠ 2 öneri var       │  │  ⚠ 1 öneri var       │            │
│  └──────────────────────┘  └──────────────────────┘            │
│                                                                  │
│  HAFTALIK ÖZET                                                  │
│  ─────────────────────────────────────────────────────────────  │
│  12 pipeline │ Pass rate %44 (+6%) │ Avg süre 6.2dk │ 0 hata   │
│                                                                  │
│  AKTİF ÖNERİLER                                                 │
│  ─────────────────────────────────────────────────────────────  │
│  1. [!] Channel DNA 52 gündür güncellenmedi        [Uygula] [✕] │
│  2. [i] S05 fallback oranı %18 — video upload opt. [Detay]  [✕] │
│  3. [i] Reframe diarization edge case tespit edildi [Detay]  [✕] │
│                                                                  │
│  NOTLAR / HAFIZA                                                │
│  ─────────────────────────────────────────────────────────────  │
│  📌 M1-M2 ayrı katman: M2 henüz otonom edit için hazır değil   │
│  📌 İleride: B-roll, ElevenLabs entegrasyonu planlanıyor        │
│                                                                  │
│  [Director ile Konuş]                [Tam Analiz Çalıştır]      │
└────────────────────────────────────────────────────────────────┘
```

### 8.3 Modül Detay Sayfası

Modül kartına tıklanınca:
- Her boyutun detaylı breakdown'u
- Son 8 analiz skoru (trend grafik)
- Tüm aktif öneriler (öncelik sırası)
- Son test sonuçları
- "Director'a Sor" butonu (chat'i o modül bağlamıyla açar)

---

## 9. PUANLAMA SİSTEMİ

*(v1.0'dan korundu, Director artık bunu araçlarla hesaplar)*

5 boyut, otomatik matematik + Gemini yorumu:

**Modül 1:**
- Teknik Sağlık (20p) — pipeline başarı oranı, süre, retry, fallback
- AI Karar Kalitesi (35p) — pass rate, kullanıcı uyuşumu, DNA yansıması
- Çıktı Yapısal Kalitesi (25p) — süre dağılımı, word snap, hook kalitesi
- Öğrenme ve Adaptasyon (15p) — trend, feedback entegrasyonu, DNA güncelliği
- Stratejik Olgunluk (5p) — açık öneriler, uygulama oranı

**Modül 2:**
- Teknik Sağlık (20p)
- Araç Performansı (40p) — Reframe (20p), Captions (12p), YouTube (8p)
- Kullanıcı Deneyimi (25p)
- Öğrenme (10p)
- Stratejik Olgunluk (5p)

**Eşikler:** 0-35 Kritik | 36-55 Zayıf | 56-70 Orta | 71-84 İyi | 85+ Güçlü

---

## 10. OTOMATİK TEST SİSTEMİ

*(v1.0'dan korundu)*

```
Director chat'ten: "Test et" veya "Full E2E test çalıştır"
Dashboard'dan: [Test Çalıştır] butonu

Test tipleri:
  full_e2e      → Tüm pipeline + M2 suite (~15 dk)
  module1       → Yalnızca pipeline (~10 dk)
  module2       → Reframe + captions + youtube (~5 dk)
  regression    → Önceki test sonuçlarıyla karşılaştır (~10 dk)
  prompt_ab     → A/B prompt testi (~20 dk)
```

Test tamamlandığında Director chat'e otomatik mesaj gelir:
```
"E2E test tamamlandı. Özet:
 - Pass rate: %50 (benchmark: %44, +6)
 - Reframe face detection: %81 (önceki: %79)
 - Caption avg confidence: 0.91
 - 1 yeni bulgu: S06'da 'relatable_moment' klipler
   tutarsız puanlama alıyor (±3 puan sapma).
 Detaylı raporu görmek ister misin?"
```

---

## 11. DIŞ ENTEGRASYON ARAÇLARI

*(v1.0'dan korundu)*

**Langfuse Cloud:** Her Gemini çağrısı → otomatik trace. Director kalite skorları yazar.
**PostHog Cloud:** Editor frontend davranışı. Director M2 analizine ekler.
**Sentry:** Backend + frontend hata takibi. Director Teknik Sağlık skoruna ekler.

```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
POSTHOG_API_KEY=phc_...
SENTRY_DSN=https://xxx@o123.ingest.sentry.io/456
SENTRY_AUTH_TOKEN=sntrys_...
```

---

## 12. KOD YAPISI

```
backend/app/director/
├── __init__.py
│
├── agent/
│   ├── core.py               → Ana agent loop: mesaj al → context hazırla → Gemini çağır → araç çalıştır → yanıt
│   ├── system_prompt.py      → Director kimliği ve prensipler
│   └── context_builder.py    → Konuşma geçmişi + hafıza + snapshot birleştirme
│
├── tools/
│   ├── registry.py           → Tüm tool tanımları (Gemini function calling schema)
│   ├── read_tools.py         → read_file, list_files, search_codebase, query_database
│   ├── query_tools.py        → get_pipeline_stats, get_clip_analysis, get_langfuse_data
│   ├── external_tools.py     → get_sentry_issues, get_posthog_events, web_search
│   ├── write_tools.py        → edit_file, update_database, update_channel_dna
│   ├── memory_tools.py       → save_memory, query_memory, list_memories, delete_memory
│   └── action_tools.py       → trigger_analysis, trigger_test, send_notification
│
├── memory/
│   ├── conversation.py       → director_conversations CRUD
│   ├── long_term.py          → director_memory embed + semantic search
│   └── snapshot.py           → Anlık sistem durumu özeti (hızlı, Gemini gerekmez)
│
├── analysis/
│   ├── scorer.py             → Puan hesaplama (otomatik, Gemini gerekmez)
│   ├── scheduler.py          → Günlük otomatik analiz background task
│   └── dashboard_writer.py   → director_analyses tablosuna yazma
│
├── test_runner/
│   ├── e2e_runner.py
│   ├── module2_suite.py
│   ├── regression_runner.py
│   └── prompt_ab_runner.py
│
├── integrations/
│   ├── langfuse_client.py
│   ├── posthog_reader.py
│   └── sentry_reader.py
│
└── api/
    ├── chat_routes.py        → POST /director/chat (SSE streaming)
    ├── dashboard_routes.py   → GET /director/status, /director/module/{name}
    ├── memory_routes.py      → GET/DELETE /director/memory
    └── test_routes.py        → POST /director/test/run

frontend/app/dashboard/director/
├── page.tsx                  → Dashboard (modül kartları, öneriler, notlar)
├── chat/
│   └── page.tsx              → Chat arayüzü (SSE ile streaming)
├── analysis/
│   └── [module]/page.tsx     → Modül detay sayfası
└── test/
    └── page.tsx              → Test merkezi
```

---

## 13. API ENDPOINTS

```
# Chat
POST /director/chat
  body: {message: str, session_id: str}
  response: SSE stream (token token)

GET /director/chat/history/{session_id}
  → Son 50 mesaj

# Dashboard
GET /director/status
  → Tüm modüllerin özet durumu (DB'den okur, Gemini çağırmaz)

GET /director/module/{module_name}
  → Tek modül detayı

# Hafıza
GET /director/memory
  → Tüm hafıza kayıtları

DELETE /director/memory/{id}
  → Hafıza kaydı sil

# Analizler
POST /director/analyze/{module}
  → Manuel analiz tetikle

GET /director/analyses/{module}
  → Analiz geçmişi

# Test
POST /director/test/run
  body: {type: str}
  → Test başlat, job_id döner

GET /director/test/{run_id}/status
  → Test durumu

GET /director/test/{run_id}/report
  → Test raporu

# Öneriler
POST /director/recommendation/{id}/mark
  body: {status: "applied" | "dismissed"}
```

---

## 14. KISITLAR

**Director ne YAPAMAZ (asla):**
- `git push` veya deploy
- Jobs veya clips tablosunu değiştirme (okuma var, yazma yok)
- Kullanıcı adına karar verme ve uygulama

**Director onay alarak YAPAR:**
- Python/TypeScript kod değişikliği
- Channel DNA güncelleme (büyük değişiklikler)
- Test pipeline başlatma (1'den fazla paralel test)

**Director serbestçe YAPAR:**
- Tüm MD dosyalarını düzenleme
- Supabase'den okuma (tüm tablolar)
- director_* tablolarına yazma
- Hafızaya kayıt
- Analiz tetikleme
- Araç zinciri kurma

---

## 15. COLD START

```
0 konuşma:
  Director ilk açıldığında şunu yapar:
  1. Tüm MD dökümanlarını okur (MODULE_1, MODULE_2, SYSTEM_CORE)
  2. Son 30 günün pipeline verilerini çeker
  3. Kendini tanıtır: "Merhaba. Sistemi inceledim.
     X pipeline çalışmış, pass rate %Y. İlk bakışta dikkatimi
     çeken şeyler: ..."

1-4 pipeline:
  "Yeterli veri yok" yerine "Az veri var ama şunu söyleyebilirim:" der

5+ pipeline:
  Tam analiz, puanlama, öneriler aktif
```

---

## 16. YAYINLAMA PLANI

### Faz 1 — Temel Araçlar (3 saat)
1. Sentry + Langfuse + PostHog kurulumu

### Faz 2 — Agent Çekirdeği (1-2 gün)
2. `director_conversations` + `director_memory` tabloları
3. Tool registry + temel araçlar (read_file, query_database, query_memory, save_memory)
4. Agent core loop (Gemini Pro function calling)
5. SSE streaming chat endpoint
6. Basit chat frontend (tek sayfa, sade)

### Faz 3 — Dashboard (1 gün)
7. Scorer.py (Gemini'siz puan hesaplama)
8. Günlük otomatik analiz scheduler
9. Dashboard frontend (modül kartları, öneriler)

### Faz 4 — Araç Genişletme (2 gün)
10. Tüm write/action araçları
11. Langfuse + Sentry + PostHog reader araçları
12. Web search (Gemini grounding)
13. Test runner entegrasyonu

### Faz 5 — İleri Özellikler (sürekli)
14. Semantik hafıza (pgvector)
15. Proaktif bildirimler
16. Prompt Lab
17. Yeni modül entegrasyon protokolü

---

*Bu döküman Director'ın kendi erişimine açıktır. Sistem değiştiğinde Director bu dosyayı da güncelleyebilir.*
