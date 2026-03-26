# Prognot Landing Page — Redesign Plan

## Hedef
- Microsoft / AWS startup kredisi başvurusu için inandırıcı bir ürün sayfası
- Yatırımcı sunumu için investor-grade görünüm
- Opus Clip'ten net biçimde ayrışan mesajlaşma
- Gerçek verilerle dolu, animasyonlu, modern

---

## Mevcut Durum (index.html)
Zaten iyi bir temel var:
- Aurora background + starfield animasyonları ✅
- Glass morphism UI sistemi ✅
- Hero, Stats, How It Works, Features Bento, Demo Mockup, Pricing, Footer ✅
- Responsive ✅

Eksikler:
- Gerçek veriler yok (placeholder stat'lar)
- Opus Clip'ten fark yok (aynı "viral clips" mesajı)
- Pipeline derinliği gösterilmiyor
- Director AI hiç yok
- Social proof / testimonial yok
- Waitlist / early access formu yok
- Animasyonlar çok basit (sadece scroll reveal)
- Feature comparison tablosu yok
- Mobile hero kötü

---

## Yeni Mimari — 10 Bölüm

### 1. NAVBAR (revize)
- Logo animasyonu (shimmer kalır)
- "Early Access" CTA → waitlist formuna scroll
- "Director AI" menu item ekle
- Scroll'da blur yoğunlaşsın

### 2. HERO (tamamen yeniden yaz)

**Başlık değişikliği:**
```
Opus Clip: "Turn Long Videos Into Viral Clips"
Prognot:   "Your AI Content Director — Not Just a Clipper"
```

**Ana mesaj:**
- Opus Clip: clip oluşturur, biter
- Prognot: 8-adım pipeline + Director AI + Channel DNA + multi-channel management
- "The only platform that thinks like a content strategist"

**Hero Animasyonu:**
- Sağ tarafta animasyonlu bir "Pipeline Visualizer" kartı
- S01→S08 adımları sırayla highlight olsun (her 1.5s bir adım)
- Clip kartları yukarı çıkıp score badge'i görünsün

**CTA:**
- "Join Waitlist" butonu (primary)
- "See How It Works" link (secondary)
- "No credit card required" + kaç kişi beklediyor (örn: "47 creators waiting")

### 3. SOCIAL PROOF BAR (YENİ)
Hero'nun hemen altında, stats'tan önce:
- "Used by creators on: YouTube · Podcast · TikTok · Instagram"
- Platform ikonları + animasyonlu scroll (marquee)
- Gerçek kanallardan toplanan metrikler varsa eklenebilir

### 4. STATS (gerçek verilerle)
Supabase'den alınacak gerçek sayılar:
- Toplam işlenmiş dakika (jobs tablosundan)
- Toplam üretilen clip sayısı
- Ortalama işlem süresi
- Kanal sayısı

Animasyon: Counter Up effect (0'dan hedefe animasyonlu sayım)

### 5. PIPELINE DEEP DIVE (YENİ — en güçlü bölüm)

**Opus Clip vs Prognot farkı burada:**

Vertical timeline formatı:
```
[S01] Audio Extract    — FFmpeg precision extraction
[S02] Transcribe       — Deepgram word-level timestamps
[S03] Speaker ID       — Diarization + human confirmation
[S04] Labeled Transcript — Context mapping
[S05] Unified Discovery — Gemini Pro + Video analysis
[S06] Batch Evaluation  — 8-dimension scoring
[S07] Precision Cut     — Word boundary snapping
[S08] Export            — R2 cloud delivery
```

Her adım tıklanabilir/hover'da detay görünsün.
Sol: adım numarası + isim
Sağ: animated visualization (mini kart)
Ortada: progress line animasyonu

### 6. FEATURES BENTO (revize)

Mevcut kartlar genişletilsin:

**Yeni kartlar:**
1. **Director AI** — "Your channel's autonomous agent. Detects performance anomalies, suggests actions, runs analyses while you sleep." (en büyük kart)
2. **Channel DNA** — "Every channel gets its own persona, tone, and content strategy. Gemini learns your brand."
3. **8-Dim Viral Scoring** — humor, energy, revelation, controversy, quotability, completeness, hook_strength, visual_interest
4. **Multi-Channel** — "Manage 20+ channels from one dashboard"
5. **Content Finder** — "Discover trending topics in your niche" (yakında badge'i ile)

**Animasyon:**
- Hover'da kart "open" efekti (detail göster)
- Director AI kartı: typing animasyonu (AI analiz yazısı)
- Viral scoring kartı: 8 bar animated olarak dolsun

### 7. VS COMPARISON TABLE (YENİ — kritik)

| Feature | Prognot | Opus Clip | Descript |
|---------|---------|-----------|----------|
| AI Pipeline Steps | 8 | 3 | 2 |
| Director AI Agent | ✅ | ❌ | ❌ |
| Channel DNA | ✅ | ❌ | ❌ |
| Speaker Confirmation | ✅ | ❌ | ❌ |
| Multi-Channel (20+) | ✅ | ❌ | ❌ |
| Content Finder | ✅ | ❌ | ❌ |
| Viral Score (8-dim) | ✅ | Temel | ❌ |
| Cloud Storage (R2) | ✅ | Extra | Extra |
| Processing Speed | < 2 min | < 5 min | Manuel |

### 8. DEMO / MOCKUP (revize)
Mevcut static mockup yerine:

**Animated App Preview:**
- Sol: Upload → Processing state → Clips grid
- State machine animasyonu (her 3s farklı state)
- Gerçek screenshot'lar eklenecek (dashboard, clips sayfası, director)
- "Actual product UI" badge'i

### 9. TESTIMONIALS / EARLY ACCESS (YENİ)

Eğer gerçek kullanıcı yoksa:
- "Early Access" section
- Büyük bir waitlist CTA
- Email input + "Join 47 creators on the waitlist"
- "What early users are saying" (kendi test sonuçların kullanılabilir)

### 10. PRICING (revize)
- Monthly/Yearly toggle (yearly'de %20 off)
- Starter / Pro / Agency üç plan
- Enterprise "Contact us" seçeneği
- Feature comparison checklist daha detaylı

---

## Animasyon Sistemi

### Yeni animasyonlar:
1. **Counter Up** — Stats sayıları 0'dan gelsin
2. **Pipeline Pulse** — S01-S08 sırayla animasyonlu highlight
3. **Typing Effect** — Director AI kartında
4. **Stagger Reveal** — Kartlar sırayla gelsin (60ms offset)
5. **Tilt on hover** — Kartlarda 3D tilt (perspective)
6. **Magnetic button** — CTA butonları fareyi takip etsin
7. **Scroll Progress** — Sayfanın üstünde ince progress bar
8. **Particle burst** — CTA tıklandığında confetti/particle efekti
9. **Gradient orb follow** — Mouse hareketi aurora orb'ları etkilesin

---

## Gerçek Veri Entegrasyonu

### Supabase'den çekilecekler (build-time veya static):
```python
# Backend endpoint eklenecek: GET /public/stats
{
  "total_clips": 847,        # clips tablosu COUNT
  "total_minutes": 2340,     # jobs tablosu SUM(duration)
  "avg_processing_sec": 94,  # jobs tablosu AVG
  "channels_count": 12       # channels tablosu COUNT
}
```

### Alternatif (statik):
Gerçek sayıları direkt HTML'e yaz, her güncelleme ile manuel update.

---

## Teknik Stack

Landing page: **tek HTML dosyası** (deploy kolaylığı için)
- Inline CSS + JS (CDN yok, hız için)
- Font: Google Fonts CDN (zaten var)
- Icons: inline SVG
- Animasyon: CSS + vanilla JS (GSAP gerekmez)

Dosya konumu: `/landing/index.html`
Deploy: GitHub Pages veya Vercel'in `landing/` static folder'ı

---

## Opus Clip'ten Fark Mesajları

### Onlar:
- "AI-powered clip creation"
- "Auto reframe for TikTok/Reels"
- "Basic captions"

### Biz (Prognot):
- "8-Step AI Pipeline — not a single model, an orchestrated system"
- "Director AI Agent — proactive anomaly detection, 24/7 channel monitoring"
- "Channel DNA — your brand's voice, encoded"
- "Speaker-confirmed diarization — human-in-the-loop quality"
- "Multi-dimensional viral scoring — 8 axes, not a single number"

---

## İmplementasyon Sırası

1. **Phase 1** (Hemen): Mevcut HTML'i projeye al, eksik bölümleri tamamla
2. **Phase 2**: Pipeline Deep Dive bölümü ekle (en güçlü bölüm)
3. **Phase 3**: VS Comparison table ekle
4. **Phase 4**: Animasyonları güçlendir (counter, tilt, magnetic)
5. **Phase 5**: Gerçek verilerle doldur (backend endpoint veya statik)
6. **Phase 6**: Waitlist form entegre et (Tally.so embed veya custom endpoint)

---

## Notlar

- "14-step pipeline" yazıyor hero'da, S01-S08 = 8 adım — DÜZELTİLECEK
- Pricing: $29/mo makul ama "Starter" daha cazip yapılacak
- Footer'da "Content Finder" var ama henüz bitmedi — "Coming Soon" badge eklenecek
- Mobile görünüm hero kısmında düzeltilebilir
