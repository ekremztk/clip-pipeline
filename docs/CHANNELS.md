# Kanal Sistemi Dokümantasyonu

Her YouTube kanalı için tam izolasyon: ayrı RAG verisi, ayrı Gemini prompt'u.
Kanallar birbirinin verisini hiçbir zaman görmez.

---

## Mevcut Kanallar

| channel_id | Kanal Adı | Durum | Config |
|------------|-----------|-------|--------|
| `speedy_cast` | Speedy Cast Clip | ✅ Aktif | `backend/channels/speedy_cast/config.py` |

---

## Speedy Cast Clip — Referans Config

`backend/channels/speedy_cast/config.py` gerçek içeriği:

```python
CHANNEL_ID = "speedy_cast"
DISPLAY_NAME = "Speedy Cast Clip"

MAX_CLIP_DURATION = 35
MIN_CLIP_DURATION = 15
MIN_VIRALITY_SCORE = 80

SYSTEM_PROMPT = """
Sen Speedy Cast Clip kanalı için çalışıyorsun.

KANAL PROFİLİ:
- Genel podcast ve talk-show içerikleri
- Geniş Türk kitlesi
- Eğlenceli, bilgilendirici, tartışmalı anlar

VİRAL SEÇİM KRİTERLERİ (öncelik sırasıyla):
1. İlk 3 saniyede güçlü kanca — izleyiciyi durduran an
2. Beklenmedik cevap veya itiraf
3. Kahkaha / şaşkınlık / duygusal patlama
4. Tartışmalı veya cesur görüş
5. İlişkilendirilebilir, "ben de öyle düşünüyorum" anı

KAÇINILACAKLAR:
- Bağlam olmadan anlaşılmayan anlar
- Uzun giriş cümleleri olan başlangıçlar
- Monolog halindeki teknik açıklamalar

İÇERİK PATERNLERİ (tercih sırasıyla):
funny_reaction, unexpected_answer, hot_take,
controversial_opinion, emotional_reveal, relatable_moment
"""
```

---

## Yeni Kanal Nasıl Eklenir

### Adım 1: Config Dosyası Oluştur

```python
# backend/channels/{kanal_id}/config.py

CHANNEL_ID = "kanal_id"
DISPLAY_NAME = "Kanal Adı"

MAX_CLIP_DURATION = 35
MIN_CLIP_DURATION = 15
MIN_VIRALITY_SCORE = 80

SYSTEM_PROMPT = """
Sen {kanal_adı} için çalışıyorsun.

KANAL PROFİLİ:
- Hedef kitle: [tanımla]
- İçerik türü: [tanımla]
- Ton: [ciddi / eğlenceli / karma]

VİRAL SEÇİM KRİTERLERİ (öncelik sırasıyla):
1. [kriter]
2. [kriter]
3. [kriter]

KAÇINILACAKLAR:
- [istenmeyen içerik]

İÇERİK PATERNLERİ:
funny_reaction, hot_take, emotional_reveal,
controversial_opinion, unexpected_answer, relatable_moment
"""
```

### Adım 2: Supabase'e Kanal Ekle

Supabase Table Editor → `channels` tablosuna satır ekle:

```sql
INSERT INTO channels (id, display_name, description, min_virality_score, max_clip_duration)
VALUES ('kanal_id', 'Kanal Adı', 'Açıklama', 80, 35);
```

### Adım 3: RAG Verisi Ekle

> ⚠️ `embedding` sütunu `vector(3072)` olmalı — gemini-embedding-001'in gerçek boyutu.
> 768 veya başka boyutta tablo oluşturursan boyut uyuşmazlığı hatası alırsın.

`channel_hunter.py` ile otomatik veya aşağıdaki gibi manuel ekle:

```sql
INSERT INTO viral_library
  (channel_id, title, hook_text, why_it_went_viral, content_pattern, viral_score)
VALUES (
  'kanal_id',
  'Video başlığı',
  'İlk 3 saniyedeki kanca cümlesi',
  'Neden viral oldu — psikolojik tetikleyici',
  'funny_reaction',
  87
);
-- Not: embedding sütununu channel_hunter.py otomatik dolduruyor.
-- Manuel ekleme yapıyorsan embedding NULL kalabilir — RAG o kaydı atlar.
```

### Adım 4: Frontend'e Ekle

`frontend/app/page.tsx` içindeki kanal listesini güncelle:

```typescript
const CHANNELS = [
  { id: "speedy_cast", name: "Speedy Cast Clip" },
  { id: "kanal_id",    name: "Kanal Adı" },  // YENİ
];
```

### Adım 5: Bu Dosyayı Güncelle

Yukarıdaki "Mevcut Kanallar" tablosuna yeni kanalı ekle.

---

## İzolasyon Prensibi — Teknik Detay

RAG sorgusu her zaman `channel_id` filtreli çalışır:

```python
# analyzer.py içinde
def find_similar_viral_dna(video_description, channel_id, limit=3):
    # ...
    cursor.execute("""
        SELECT title, hook_text, why_it_went_viral, content_pattern, viral_score
        FROM viral_library
        WHERE channel_id = %s              -- ← izolasyon buradan
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """, (channel_id, embedding_str, limit))
```

Bir kanalın referans verisi hiçbir zaman başka bir kanalın analizini etkilemez.