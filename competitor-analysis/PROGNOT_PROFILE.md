# Prognot AI — Full Company & Product Profile

> **Bu dosya Prognot'a aittir.** Rakip analizi dosyalarıyla birlikte NotebookLM'e yüklenmek üzere hazırlanmıştır.
> Prognot = bizim ürünümüz. Rakipler = diğer tüm dosyalar.

---

## 1. Kimlik & Konumlandırma

**Ürün adı:** Prognot AI
**Slogan:** "Your AI Content Director" / "Not just a clipper."
**Kategori:** AI-powered video repurposing & content operations
**Aşama:** Private Beta (2026 Q1)
**Web siteleri:**
- `prognot.com` — landing/marketing sayfası
- `clip.prognot.com` — Prognot Studio (ana uygulama)
- `edit.prognot.com` — AI Video Editor

**İletişim:** akram@prognot.com
**Bekleme listesi:** ~1 creator (2026 Nisan başı itibarıyla)

---

## 2. Temel Ürün Felsefesi

Prognot kendisini rakiplerden şu şekilde ayırıyor:

> "Diğer araçlar klipler ve durur. Prognot 9 adımlı bir AI pipeline çalıştırır."

Konumlandırma: **Clipper değil, content operating system.**
Rakipler (OpusClip, Vizard, Klap vb.) yalnızca video kırpma yapar.
Prognot ise brand learning (Channel DNA), proactive AI agent (Director AI), ve 8 boyutlu viral scoring ile "akıllı bir içerik direktörü" olarak konumlanıyor.

Hedef kitle:
- Podcast creators (özellikle uzun format, 30+ dk video)
- Content agency'ler (birden fazla müşteri kanalı yöneten)
- Faceless channel sahipleri
- Interview & talk show yapımcıları
- Gaming content creators
- Marketing ekipleri

---

## 3. Pipeline — 9 Adımlı AI Sistemi

Prognot'un temel fark yaratan özelliği tam otomasyon pipeline'ı:

```
S01 Audio Extract     → Lossless audio isolation, her format desteklenir (MP4, MOV, MKV, WebM)
S02 Transcribe        → Deepgram (word-level timestamps, speaker diarization)
S03 Speaker ID        → Otomatik konuşmacı tanıma + kullanıcı onayı (pause noktası)
S04 Labeled Transcript→ Transcript'i konuşmacı bazlı etiketleme, Channel DNA entegrasyonu
S05 Unified Discovery → Gemini 2.5 Pro — hem video görüntüsü hem metin analizi (multimodal)
S06 Batch Evaluation  → Claude claude-sonnet-4-6 — 8 boyutlu viral scoring + quality gate
S07 Precision Cut     → FFmpeg lossless stream copy, word-boundary snapping
S08 Export & Deliver  → FFmpeg re-encode (4K capable), Cloudflare R2'ye yükleme, DB yazımı
[S09 AI Editor]       → Yakında — tam otomatik post-production (edit.prognot.com)
```

**Hız:** 60 dakikalık podcast → 7–12 scored ve cut klip → 10 dakika altında
**Çıktı platformları:** YouTube Shorts, TikTok, Instagram Reels, LinkedIn Video

---

## 4. Ana Özellikler

### 4.1 Channel DNA
- Kanal bağlandığında mevcut içerik analiz edilir
- Tone, pacing, vocabulary, content themes, audience engagement patterns çıkarılır
- Tüm downstream kararlar (clip selection, scoring, Director AI önerileri) bu DNA'ya göre yapılır
- Kullanıcı tanımlı kurallar: yasak konular, öncelikli anlar, posting stili, forbidden words
- Her video işledikçe model gelişir

### 4.2 Director AI
- Gemini 2.5 Pro destekli otonom agent
- Saatlik schedule ile çalışır, manuel tetikleme gerekmez
- Yaptıkları:
  - Engagement drop detection
  - Viral spike tanıma
  - Posting pattern anomalileri
  - Kanal hafızasına tam erişim
  - Actionable öneri üretme
- Dashboard her zaman güncel, fresh intelligence
- Araçları: DB sorgu, clip analiz, Langfuse logging, channel memory okuma/yazma

### 4.3 8-Boyutlu Viral Scoring
Her klip 8 boyutta skorlanır:
1. **Humor** — mizahi içerik potansiyeli
2. **Energy** — konuşma hızı, canlılık
3. **Revelation** — "aha moment" yoğunluğu
4. **Hook Strength** — ilk 3 saniyenin çekiciliği
5. **Quotability** — alıntılanabilirlik, paylaşılabilir cümle
6. **Visual Quality** — görsel netlik, frame kalitesi
7. **Controversy** — tartışma potansiyeli
8. **Completeness** — klipin başlangıç-bitiş bütünlüğü

Her skor doğal dil açıklamasıyla birlikte gelir.
Minimum skor eşiğini geçemeyen klipler otomatik filtrelenir.
Scoring Channel DNA-aware: yüksek skor = senin kitlen için yüksek performans.

### 4.4 AI Video Editor (edit.prognot.com)
- OpenCut tabanlı, tamamen Prognot'a entegre
- Supabase + Cloudflare R2 backend
- Prognot Studio'dan tek tıkla klip import (`?clipUrl=` parametresi)
- Özellikler: timeline editing, captions, auto-reframe (keyframe engine), Freesound entegrasyonu
- Status: **çalışıyor, beta**

### 4.5 Content Finder (Yakında)
- Trend detection: arama trendleri, viral spike'lar, platform davranışları
- Competitor intelligence: niche kanalların engagement driver'ları
- Channel DNA matching: her fikir senin sesine ve kitlenine uygunluğa göre skorlanır
- Status: **aktif geliştirme, skeleton aşamasında**

---

## 5. Teknik Altyapı

| Bileşen | Teknoloji |
|---------|-----------|
| Backend | FastAPI, Python 3.11, Railway (CPU only, 8GB RAM) |
| Frontend (Studio) | Next.js 16, TypeScript, Tailwind, Vercel |
| Frontend (Editor) | Next.js 16, Bun, Turbopack, Vercel |
| Veritabanı | Supabase (PostgreSQL + pgvector, connection pooler 6543) |
| Dosya depolama | Cloudflare R2 (clip export + editor media) |
| AI — Discovery | Gemini 2.5 Pro (video + text multimodal) |
| AI — Scoring | Claude claude-sonnet-4-6 (Anthropic SDK) |
| AI — Director | Gemini 2.5 Pro (function calling, agentic loop) |
| AI — Fast calls | Gemini 2.5 Flash |
| Transkripsiyon | Deepgram (diarization, word timestamps) |
| Video işleme | FFmpeg, yt-dlp |
| Auth | Supabase SSR (email + Google OAuth) |
| Monitoring | Langfuse (LLM call tracing) |
| Analytics | PostHog |
| Hata takibi | Sentry |

**YouTube URL desteği:** yt-dlp ile doğrudan YouTube linki yapıştırılabilir, video indirilip pipeline'a sokulur.

---

## 6. Fiyatlandırma

| Plan | Fiyat | Krediler | Export | Kanallar | Director AI | Notlar |
|------|-------|----------|--------|----------|-------------|--------|
| Free | $0 | 100/ay | 720p | 1 | — | Kredi kartı yok, watermark |
| Pro Creator | $19/mo | 500/ay | 4K | 3 | ✓ | En popüler plan |
| Agency | Açıklanmadı | İsteğe göre/ay | 4K | 20+ | ✓ | Content Finder erken erişim, API, ekip üyeleri, dedicated onboarding |

**Kredi sistemi:** Kullandıkça öde modeli. 1 kredi = 1 dakika video (tahmin).
**Billed monthly** (yıllık seçenek belirsiz).

---

## 7. Rekabetçi Konum

### Biz ne yapıyoruz ki rakipler yapmıyor?

| Özellik | Prognot | OpusClip | Vizard | InVideo | Flowjin | Quso |
|---------|---------|----------|--------|---------|---------|------|
| Pipeline adım sayısı | 9 | ~3 | ~3 | ~3 | ~3 | ~3 |
| Director AI agent | ✓ | — | — | — | — | — |
| Channel DNA | ✓ | Kısmi | — | — | — | — |
| 8-dim viral scoring | ✓ | 1 skor | — | — | — | — |
| Multimodal discovery | ✓ (video+text) | Text | Text | Text | Text | Text |
| Word-boundary cut | ✓ | Yaklaşık | — | — | — | — |
| Built-in editor | ✓ | Kısmi | ✓ | ✓ | — | — |
| YouTube URL input | ✓ | ✓ | ✓ | ✓ | ? | ? |
| Content Finder | Yakında | — | — | — | — | — |
| API erişimi | Yakında | — | — | — | — | — |

### Rakiplerin üstün olduğu alanlar (dürüst değerlendirme):
- **Vizard:** Capterra'da 424 yorum, 4.9/5 — çok daha büyük kullanıcı tabanı, güçlü sosyal kanıt
- **InVideo:** 301K YouTube abonesi, 23M görüntülenme — video marketing'te çok güçlü
- **OpusClip:** 63K YouTube, 3.9M görüntülenme, 47+ waitlist'e karşı çok büyük topluluk
- **Flowjin:** Product Hunt'ta 700+ beğeni — launch stratejisi güçlü
- **Restream:** 79.8K YouTube, 9.6M görüntülenme — geniş content library

---

## 8. Mevcut Durumu (2026 Nisan)

### ✅ Tamamlananlar
- 8 adımlı pipeline tamamen çalışıyor (S01-S08)
- Director AI agent çalışıyor (saatlik analiz)
- Channel DNA sistemi çalışıyor
- 8-boyutlu scoring (Claude) çalışıyor
- AI Video Editor çalışıyor (edit.prognot.com)
- Supabase auth (email + Google) çalışıyor
- Cloudflare R2 entegrasyonu çalışıyor
- YouTube URL import çalışıyor
- Landing sayfası yayında (prognot.com)
- Waitlist sistemi aktif (~47 kişi)
- Pricing sayfası yayında

### 🔄 Geliştirme Aşamasında
- Content Finder (Module 3) — skeleton kodlanmış, aktif geliştirme
- S09 AI Editor entegrasyonu — edit.prognot.com ile derin entegrasyon
- Channel memory & feedback sistemi — dondurulmuş, ilerleyen süreçte

### ❌ Henüz Yapılmadı — Planlanması Gerek

---

## 9. Yapılmayanlar — Tüm Alanlar

### 9.1 Pazarlama & İçerik
**Henüz yapılmadı — planlanması gerek.**
- Sosyal medya varlığı yok (Twitter/X, Instagram, TikTok hesabı aktif değil)
- YouTube kanalı yok (rakiplerin en büyük trafiği YouTube üzerinden geliyor)
- Blog / içerik pazarlaması yok (SEO sıfır)
- Case study / success story yayınlanmamış
- Creator topluluğu oluşturulmamış (Discord, Slack, Circle vb.)
- Influencer/creator partnership kurulmamış
- Karşılaştırma makaleleri ("Prognot vs OpusClip") yok
- Newsletter/email marketing stratejisi yok

### 9.2 Lansman Stratejisi
**Henüz yapılmadı — planlanması gerek.**
- Product Hunt launch yapılmamış (rakiplerin büyük çoğunluğu PH üzerinden büyüdü)
- AppSumo launch yapılmamış
- BetaList, Launching Next gibi platformlarda listelenmemiş
- Hacker News "Show HN" post yapılmamış
- Yayıncı/podcast topluluklarında (Reddit r/podcasting, r/Creator, Creator Economy groups) tanıtım yapılmamış

### 9.3 Ücretli Reklam
**Henüz yapılmadı — planlanması gerek.**
- Meta Ads (Facebook/Instagram) kampanyası yok
- Google Ads kampanyası yok
- YouTube Ads kampanyası yok
- TikTok Ads kampanyası yok
- Retargeting kampanyası yok

### 9.4 SEO & Organik Trafik
**Henüz yapılmadı — planlanması gerek.**
- Domain otoritesi düşük (yeni domain)
- Anahtar kelime stratejisi kurulmamış ("AI clip generator", "podcast to shorts", vb.)
- Backlink profili yok
- "vs" sayfaları yok (Prognot vs OpusClip, Prognot vs Vizard)
- Use case sayfaları zayıf (podcast creators, content agencies, vb.)
- Changelog/updates sayfası yok (rakipler bu sayfayla SEO kazanıyor)

### 9.5 Topluluk & Sosyal Kanıt
**Henüz yapılmadı — planlanması gerek.**
- G2 listesi yok
- Capterra listesi yok
- Trustpilot listesi yok
- Gerçek kullanıcı yorumları toplanmamış (landing'deki testimonial'lar beta test)
- Discord/community server yok
- Creator referral programı yok
- Affiliate/partner programı yok

### 9.6 Satış & Growth
**Henüz yapılmadı — planlanması gerek.**
- Outbound sales yok
- Agency partnership programı yok
- Reseller/white-label teklif yok
- Enterprise/özel fiyatlandırma süreci yok
- Onboarding email dizisi yok (activation sequence)
- Churn prevention sistemi yok
- Upsell akışı yok (free → pro dönüşüm)

### 9.7 Ürün (Eksik Özellikler)
- Content Finder tamamlanmamış
- S09 (AI Editor tam otomasyonu) tamamlanmamış
- API erişimi yok (Agency planında vaat edilmiş)
- Takım hesabı / workspace özelliği yok
- Toplu upload (batch processing) arayüzü belirsiz
- Scheduled post / doğrudan sosyal medya yayını yok
- Mobile app yok
- Webhook / Zapier entegrasyonu yok
- White-label çıktı yok (watermark'sız marka seçeneği)

### 9.8 Altyapı & Operasyon
- Yedekleme ve disaster recovery prosedürü belgelenmemiş
- SLA / uptime guarantee yok
- Müşteri destek sistemi yok (Intercom açık ama yapılandırılmamış)
- Usage analytics dashboard (kredit tüketimi, pipeline başarı oranı) kullanıcıya gösterilmiyor
- Billing portal / fatura yönetimi yok (ödeme altyapısı aktif değil)

---

## 10. Güçlü Yönler (Rakiplere Karşı)

1. **Pipeline derinliği** — 9 adım, multimodal AI, word-boundary cut: hiçbir rakip bu kadar derin pipeline sunmuyor
2. **Director AI** — rakiplerde hiçbirinde proaktif, 24/7 çalışan otonom agent yok
3. **Channel DNA** — brand learning sistemi OpusClip'te kısmi var, diğerlerinde yok
4. **8-boyutlu scoring** — rakipler tek sayı veriyor, Prognot "neden?" sorusunu da yanıtlıyor
5. **Entegre editor** — Studio + Editor entegrasyonu rakiplerin çoğunda kopuk veya yok
6. **Claude tabanlı scoring** — kaliteli doğal dil reasoning, rakipler daha basit modeller kullanıyor

## 11. Zayıf Yönler (Açıkçası)

1. **Topluluk yok** — Vizard'ın 424, Restream'in 500+ Capterra yorumuna karşı Prognot'un 0 kamuya açık yorumu var
2. **Trafik yok** — tüm rakipler SimilarWeb'de görünürken Prognot görünmüyor (çok yeni)
3. **İçerik yok** — YouTube 0, blog 0, sosyal medya 0 — rakiplerin %100'ü içerik üretiyor
4. **Waitlist küçük** — ~47 kişi vs rakiplerin binlerce-milyonlarca kullanıcısı
5. **Fiyatlandırma netliği** — Agency planı fiyatı yok; rakipler şeffaf fiyatlıyor
6. **Ödeme altyapısı** — aktif billing yok, gerçek para almıyor henüz

---

## 12. Rakip Analizi Özeti (Karşılaştırmalı)

| Rakip | Ana Güç | Ana Zayıflık | Prognot'tan Farkı |
|-------|---------|--------------|-------------------|
| **OpusClip** | Viral score, büyük topluluk, YouTube varlığı | Tek skor, sığ pipeline, pahalı | Prognot: daha derin AI, Director yok onlarda |
| **Vizard** | 424 Capterra yorumu 4.9/5, çok güçlü sosyal kanıt | Basit klipleme, DNA yok | Prognot: AI zekası daha derin |
| **Flowjin** | Product Hunt'ta güçlü, temiz UX | Küçük trafik, özellik sığ | Prognot: pipeline çok daha kapsamlı |
| **Quso** | Blog/SEO güçlü, çok özellik | Odak kayması (AI asistan da var) | Prognot: focused product |
| **InVideo** | 301K YouTube, devasa içerik library | AI editör yoğun, klipten çok yapımcı aracı | Farklı kategori, klip odaklı değil |
| **Restream** | 79.8K YouTube, streaming odaklı dev | Klip çıkarma ana özellik değil | Farklı kategori |
| **Exemplary AI** | Transkripsiyon güçlü, çoklu kullanım alanı | Klip kalitesi düşük | Farklı odak |
| **QuickReel** | Basit, hızlı | Çok sığ özellik, küçük trafik | Prognot: tam otomasyon |
| **Swiftia** | Düşük fiyat | Çok az kullanıcı, özellik az | Prognot: enterprise-grade |
| **Wayin** | Template odaklı | Yeni, çok küçük | Farklı segment |

---

*Bu doküman Prognot'un NotebookLM rakip analizine katkısı için hazırlanmıştır. Son güncelleme: 2026-04-05*
