

# MODÜL 3 — CONTENT FINDER: Tam Sistem Planı

Tüm sistemi inceledim. Şimdi sana Content Finder modülünü, ben olsam nasıl baştan sona kurardım, her katmanıyla anlatıyorum.

---

## 1. MODÜLÜN KONUMU VE AMACI

Şu anda pipeline'da bir boşluk var:

```
[???] → Modül 1 (Clip Extractor) → Modül 2 (Editor) → YouTube Upload
  ↑
  Bu boşluğu Content Finder dolduracak
```

**Giriş:** Channel DNA + geçmiş performans verileri
**Çıkış:** Her kanal için günlük 5 adet puanlanmış, analiz edilmiş, "neden seçildi" açıklaması olan long-form video önerisi

---

## 2. TEMEL FELSEFİ YAKLAŞIM

Content creator olarak düşündüğümde şu gerçekleri görüyorum:

1. **En iyi klipler en iyi konuşmalardan çıkar** — her podcast'te viral moment yok. Guest, konu, kimya önemli.
2. **Altın kaynaklar var** — bazı podcast kanalları sürekli iyi materyal üretir. Bunları bulmak, rastgele aramaktan çok daha değerli.
3. **Eski içerikler altın madeni** — 2-3 yıl önceki podcast'lerin çoğu hiç shorts'a çevrilmemiş. Rekabet sıfır.
4. **Guest kalitesi = klip kalitesi** — sıkıcı bir konuktan viral clip çıkmaz.
5. **Çeşitlilik şart** — aynı kaynak kanaldan arka arkaya klip almak izleyiciyi sıkar.
6. **Trend konular patlama yaratır** — gündem konusuyla örtüşen eski bir podcast bile viral olabilir.

Bu yüzden sistem sadece "YouTube'da arama yap" değil, **çok katmanlı bir keşif motoru** olacak.

---

## 3. SİSTEM MİMARİSİ — DISCOVERY PIPELINE

```
CONTENT FINDER PIPELINE (6 Faz):

F01 → F02 → F03 → F04 → F05 → F06
Query    YouTube    Filter    Quick     Deep       Rank &
Gen      Search     & Dedup   Score     Analysis   Present

Faz   İsim                Model/Araç              Amaç
F01   Query Generation     Gemini Flash            DNA'dan arama sorguları üret
F02   Multi-Strategy       YouTube Data API v3     Çoklu stratejiyle video bul
      Search
F03   Filter & Dedup       Python + Supabase       Format, süre, tekrar filtrele
F04   Quick Score          Heuristik algoritma     Metadata'dan hızlı puanlama
F05   Deep Analysis        Gemini Flash + YT       Transkript analizi, klip
                           Captions                potansiyeli tahmini
F06   Final Ranking        Ağırlıklı skor          Top 5 seç ve sun
```

---

## 4. F01 — QUERY GENERATION (Akıllı Arama Sorgusu Üretimi)

### Neden AI ile sorgu üretimi?
Manuel anahtar kelime listesi yazmak kısıtlayıcı. Channel DNA zaten kanalın ne istediğini tam olarak tanımlıyor. Gemini bunu okuyup, YouTube'da en iyi sonuç verecek arama sorgularını üretebilir.

### Çalışma Mantığı

```python
def generate_queries(channel_id: str, strategy: str) -> list[dict]:
    """
    Channel DNA + geçmiş verilerden arama sorguları üretir.
    Her sorguyla birlikte hangi stratejiyle aranacağı da belirlenir.
    """
    
    channel = get_channel(channel_id)
    dna = channel.channel_dna
    memory = get_discovery_memory(channel_id)  # son 90 gün
    recent_successes = get_recent_successful_sources(channel_id, limit=10)
    trending_topics = get_trending_topics(dna.niche)  # opsiyonel
```

### Gemini'ye Gönderilen Prompt

```
Sen bir YouTube Shorts kanalı için içerik araştırmacısısın.

KANAL PROFİLİ:
- Hedef kitle: {audience_identity}
- Ton: {tone}
- Aranan moment türleri: {do_list}
- Kaçınılan konular: {dont_list}
- Yasak konular: {no_go_zones}
- En iyi içerik türleri: {best_content_types}
- Mizah stili: {humor_profile}
- Kutsal konular: {sacred_topics}

SON BAŞARILI KAYNAKLAR:
{recent_successes - başlık, kanal, konu listesi}

GEÇMİŞTE ZAYIF SONUÇ VEREN ARAMALAR:
{weak_queries - düşük skor alan sorgular}

GÜNCEL TRENDLER (varsa):
{trending_topics}

GÖREV:
Bu kanal için YouTube'da long-form podcast ve röportaj bulmak üzere 
{query_count} adet arama sorgusu üret.

KURALLAR:
1. Sorgular İngilizce olmalı (YouTube araması için)
2. Her sorgu 2-5 kelime arası (YouTube aramasında uzun sorgular kötü çalışır)
3. Hem geniş hem dar sorgular karışık olsun
4. En az 3 sorgu "eski ama altın" içerik bulabilecek tipte olsun
   (evergreen konular, klasik konuşmalar)
5. En az 2 sorgu güncel/trend konularda olsun
6. Misafir odaklı sorgular dahil et (ünlü isimler + podcast)
7. Geçmişte zayıf sonuç veren sorgu kalıplarından kaçın

HER SORGU İÇİN FORMAT:
{
  "query": "arama sorgusu",
  "strategy": "topic | guest | niche_deep | trending | evergreen",
  "expected_content": "Bu sorgudan ne tür içerik bekleniyor",
  "priority": 1-5  // 5 = çok önemli
}
```

### Çıktı Örneği (erkek konuklu komedi/mizah kanalı için)

```json
[
  {
    "query": "comedian podcast interview funny story",
    "strategy": "topic",
    "expected_content": "Komedyenlerin komik hikaye anlattığı podcast bölümleri",
    "priority": 5
  },
  {
    "query": "Joe Rogan funniest guest moments",
    "strategy": "niche_deep",
    "expected_content": "JRE'nin en komik konuk anları",
    "priority": 4
  },
  {
    "query": "podcast awkward moment hilarious",
    "strategy": "topic",
    "expected_content": "Garip ama komik podcast anları",
    "priority": 4
  },
  {
    "query": "Theo Von interview 2024",
    "strategy": "guest",
    "expected_content": "Theo Von'un son röportajları (mizah potansiyeli yüksek)",
    "priority": 5
  },
  {
    "query": "male comedian long interview",
    "strategy": "evergreen",
    "expected_content": "Eski ama kaliteli komedyen röportajları",
    "priority": 3
  }
]
```

### Sorgu Sayısı
- Günlük otomatik çalışma: Kanal başına **12-15 sorgu**
- Manuel "derin tarama": Kanal başına **25-30 sorgu**
- Her sorgu ~100 YouTube API unit = 15 sorgu × 100 = 1,500 unit/kanal

---

## 5. F02 — MULTI-STRATEGY SEARCH (Çoklu Strateji Arama)

### 5 Arama Stratejisi

YouTube Data API v3 üzerinden paralel çalışır.

#### Strateji A: Topic Search (Konu Araması)
```
YouTube Search API:
  q = "{generated_query}"
  type = video
  videoDuration = long (>20 dakika)
  order = relevance VEYA viewCount
  maxResults = 15
  relevanceLanguage = en
  publishedAfter = (strateji tipine göre değişir)
```

**Zaman penceresi mantığı:**
```
Sorgu strategy = "trending"   → publishedAfter: son 30 gün
Sorgu strategy = "topic"      → publishedAfter: yok (tüm zamanlar)
Sorgu strategy = "evergreen"  → publishedBefore: 6 ay önce (eski içerik)
Sorgu strategy = "guest"      → publishedAfter: yok
Sorgu strategy = "niche_deep" → publishedAfter: yok
```

#### Strateji B: Source Channel Mining (Kaynak Kanal Tarama)
```python
def mine_source_channels(channel_id: str):
    """
    Bilinen iyi kaynak kanalların videolarını tarar.
    source_channels tablosundan goldmine kanallar çekilir.
    """
    sources = get_source_channels(channel_id, is_goldmine=True)
    
    for source in sources:
        # Kanalın uploads playlist'ini al
        playlist_id = get_uploads_playlist(source.youtube_channel_id)
        
        # Son taramadan bu yana yeni video var mı?
        new_videos = get_playlist_items(
            playlist_id, 
            published_after=source.last_scanned_at
        )
        
        # Back catalog taraması (henüz taranmamışsa)
        if source.scan_depth == 'recent':
            old_videos = get_playlist_items(
                playlist_id,
                max_results=50,  # son 50 video
                published_before=source.last_scanned_at
            )
```

**Kaynak kanal nasıl keşfediliyor?**
1. **Manuel ekleme:** Kullanıcı bildiği podcast kanallarını ekler
2. **Otomatik keşif:** Clip Extractor'a gönderilen her video'nun kaynak kanalı otomatik eklenir
3. **Goldmine tespiti:** Aynı kaynaktan 3+ başarılı klip → goldmine olarak işaretlenir
4. **Gemini önerisi:** Channel DNA analiz edildiğinde Gemini potansiyel kaynak kanallar önerebilir

#### Strateji C: Guest Hunt (Konuk Avı)
```python
def hunt_guests(channel_id: str):
    """
    Kanal DNA'sına uygun konukların podcast görünümlerini bulur.
    """
    dna = get_channel_dna(channel_id)
    
    # Gemini'den bu kanal için ideal konuk profilleri iste
    ideal_guests = gemini_generate_ideal_guests(dna)
    # Örnek çıktı: ["Theo Von", "Andrew Schulz", "Mark Normand", ...]
    
    for guest in ideal_guests:
        search(f"{guest} podcast interview")
        search(f"{guest} funny moment interview")
```

#### Strateji D: Related Video Chain (İlişkili Video Zinciri)
```python
def follow_related_chain(channel_id: str):
    """
    Geçmişte başarılı olan kaynak videoların 'related videos'larını takip eder.
    YouTube API'ın relatedToVideoId parametresini kullanır.
    """
    seed_videos = get_successful_source_videos(channel_id, limit=5)
    
    for seed in seed_videos:
        related = youtube_search(relatedToVideoId=seed.youtube_video_id)
        # İlişkili videolar genelde benzer format ve konudadır
```

#### Strateji E: Niche Explorer (Niş Keşifçi)
```python
def explore_niche(channel_id: str):
    """
    Kanalın nişindeki popüler playlist'leri ve koleksiyonları tarar.
    """
    dna = get_channel_dna(channel_id)
    
    # Niş bazlı geniş aramalar
    search(f"best {dna.niche} podcasts")
    search(f"top {dna.niche} interviews")
    search(f"viral {dna.niche} moments")
```

### API Quota Yönetimi

```
YouTube Data API: 10,000 unit/gün (varsayılan kota)

Operasyon başına maliyet:
  search.list         = 100 unit
  videos.list         = 1 unit  
  channels.list       = 1 unit
  playlistItems.list  = 1 unit
  captions.list       = 50 unit
  captions.download   = 200 unit

Günlük bütçe (2 kanal için):
  Arama: 15 sorgu × 2 kanal × 100 = 3,000 unit
  Video detay: 100 video × 2 × 1 = 200 unit
  Kanal detay: 20 kanal × 1 = 20 unit
  Transkript: 10 deep analysis × 2 × 200 = 4,000 unit
  ─────────────────────────────────────────
  Toplam: ~7,220 unit (kota içinde)

Kota aşım önlemi:
  - Kalan kotayı takip et (response headers)
  - Kota %80'e ulaşınca deep analysis'i ertele
  - Günlük çalışma saati: gece 03:00 (kota sıfırlandıktan sonra)
```

---

## 6. F03 — FILTER & DEDUP (Filtreleme ve Tekrar Engelleme)

Bu fazda AI kullanılmaz. Tamamen heuristik ve veritabanı sorguları.

### Filtreleme Kuralları

```python
def filter_candidates(raw_results: list[dict], channel_id: str) -> list[dict]:
    filtered = []
    
    for video in raw_results:
        # 1. SÜRE FİLTRESİ
        # Çok kısa = klip çıkarmak için yeterli materyal yok
        # Çok uzun = genelde konferans/ders formatı
        if video.duration_seconds < 600:    # < 10 dakika
            continue  # reject
        if video.duration_seconds > 14400:  # > 4 saat
            continue  # reject
        # İdeal aralık: 20-120 dakika
        
        # 2. TEKRARcHECK — Daha önce keşfettik mi?
        exists = supabase.select("discovered_content")
            .eq("youtube_video_id", video.id)
            .eq("channel_id", channel_id)
            .execute()
        if exists.data:
            continue  # zaten biliyoruz
        
        # 3. CLIP EXTRACTOR'DA İŞLENMİŞ Mİ?
        processed = supabase.select("jobs")
            .eq("youtube_video_id", video.id)
            .execute()
        if processed.data:
            continue  # zaten klip çıkardık
        
        # 4. DİL KONTROLÜ
        # title ve description'dan dil tahmini
        if detect_language(video.title) not in ["en"]:  # kanal diline göre
            continue
        
        # 5. FORMAT TAHMİNİ (Basit heuristik)
        # Podcast/interview olma ihtimali düşük formatları ele
        bad_keywords = ["music video", "live concert", "gameplay", 
                       "tutorial", "how to", "compilation", "ASMR",
                       "meditation", "sleep", "white noise", "news"]
        title_lower = video.title.lower()
        if any(kw in title_lower for kw in bad_keywords):
            continue
        
        # 6. PODCAST/İNTERVİEW FORMATI TAHMİNİ (Pozitif sinyal)
        good_keywords = ["podcast", "interview", "conversation", 
                        "episode", "ep.", "talk", "sits down with",
                        "guest", "ft.", "feat.", "w/", "with"]
        format_signal = any(kw in title_lower for kw in good_keywords)
        video["format_signal"] = format_signal
        
        filtered.append(video)
    
    return filtered
```

### Deduplication Katmanları

```
Katman 1: Aynı YouTube video ID → kesin tekrar
Katman 2: Aynı başlık + aynı kanal → muhtemelen re-upload
Katman 3: Aynı konuk + aynı konu (±6 ay) → içerik tekrarı riski
          → tamamen engellenmez ama uniqueness_score düşer
```

---

## 7. F04 — QUICK SCORE (Hızlı Puanlama)

Bu fazda **AI kullanılmaz**. Tamamen metadata üzerinden heuristik hesaplama yapılır. Hızlı ve ucuz.

### 6 Puanlama Boyutu

#### 7.1 Topic Match Score (Konu Uyumu) — 0-10

```python
def calc_topic_match(video: dict, dna: dict) -> float:
    score = 5.0  # başlangıç: ortalama
    
    title_desc = (video.title + " " + video.description).lower()
    
    # do_list eşleşmeleri (her eşleşme +1, max +3)
    do_matches = sum(1 for item in dna.do_list 
                     if any(kw in title_desc for kw in item.lower().split()))
    score += min(do_matches, 3)
    
    # dont_list eşleşmeleri (her eşleşme -1.5)
    dont_matches = sum(1 for item in dna.dont_list
                       if any(kw in title_desc for kw in item.lower().split()))
    score -= dont_matches * 1.5
    
    # no_go_zones eşleşmeleri (anında 0)
    for zone in dna.no_go_zones:
        if zone.lower() in title_desc:
            return 0.0
    
    # sacred_topics eşleşmeleri (+2)
    for topic in dna.sacred_topics:
        if topic.lower() in title_desc:
            score += 2
            break
    
    # best_content_types ipuçları
    type_keywords = {
        "humor": ["funny", "comedy", "hilarious", "laugh"],
        "debate": ["debate", "argument", "disagree", "vs"],
        "revelation": ["secret", "truth", "reveal", "never told"],
        "emotional": ["emotional", "cried", "broke down", "vulnerable"],
        "storytelling": ["story", "crazy story", "insane story"]
    }
    for ctype in dna.best_content_types:
        if ctype in type_keywords:
            if any(kw in title_desc for kw in type_keywords[ctype]):
                score += 1.5
                break
    
    # Format sinyali bonusu
    if video.get("format_signal"):
        score += 0.5
    
    return max(0, min(10, score))
```

#### 7.2 Guest Potential Score (Konuk Potansiyeli) — 0-10

```python
def calc_guest_potential(video: dict, channel_id: str) -> float:
    score = 5.0
    
    # Başlıktan konuk adı çıkar
    guest_name = extract_guest_name(video.title)
    # Heuristik: "ft.", "with", "w/", "|", "-" sonrasındaki isim
    # Veya "X sits down with Y", "X interviews Y" kalıpları
    
    if not guest_name:
        return 5.0  # bilinmiyor, ortalama ver
    
    # Daha önce bu konuktan başarılı klip çıktı mı?
    past_success = supabase.select("clips")
        .eq("channel_id", channel_id)
        .ilike("hook_text", f"%{guest_name}%")
        .eq("quality_verdict", "pass")
        .execute()
    if past_success.data:
        score += 2.0  # kanıtlanmış konuk
    
    # guest_profiles tablosunda var mı?
    profile = supabase.select("guest_profiles")
        .eq("normalized_name", guest_name.lower())
        .execute()
    if profile.data:
        p = profile.data[0]["profile_data"]
        if p.get("viral_moments"):
            score += 1.5
        if p.get("controversies"):
            score += 1.0
    
    # Kaynak videonun kendi performansı (çok izlenen = ilgi çekici konuk)
    if video.view_count > 1_000_000:
        score += 2.0
    elif video.view_count > 500_000:
        score += 1.5
    elif video.view_count > 100_000:
        score += 1.0
    
    video["detected_guest_name"] = guest_name
    return max(0, min(10, score))
```

#### 7.3 Format Score (Format Uygunluğu) — 0-10

```python
def calc_format_score(video: dict) -> float:
    score = 5.0
    
    title_lower = video.title.lower()
    desc_lower = (video.description or "").lower()
    
    # Podcast/interview formatı güçlü sinyalleri
    strong_signals = ["podcast", "interview", "episode", "ep "]
    if any(s in title_lower for s in strong_signals):
        score += 3.0
    
    # Konuşma formatı sinyalleri
    conv_signals = ["conversation", "talk", "chat", "discuss",
                    "sits down", "joins", "ft.", "feat.", "w/"]
    if any(s in title_lower or s in desc_lower for s in conv_signals):
        score += 2.0
    
    # İdeal süre aralığı (20-120 dakika)
    dur = video.duration_seconds / 60  # dakika
    if 20 <= dur <= 120:
        score += 2.0
    elif 10 <= dur < 20 or 120 < dur <= 180:
        score += 1.0
    elif dur > 180:
        score += 0.5  # çok uzun ama olabilir
    
    # Kötü format sinyalleri
    bad_signals = ["lecture", "keynote", "presentation", "course",
                   "documentary", "react", "compilation"]
    if any(s in title_lower for s in bad_signals):
        score -= 3.0
    
    # Kanal adından format tahmini
    channel_name = video.channel_title.lower()
    if "podcast" in channel_name:
        score += 1.5
    
    return max(0, min(10, score))
```

#### 7.4 Engagement Score (Etkileşim) — 0-10

```python
def calc_engagement_score(video: dict) -> float:
    views = video.view_count or 0
    likes = video.like_count or 0
    comments = video.comment_count or 0
    
    # View bazlı skor
    if views >= 5_000_000:
        view_score = 10
    elif views >= 1_000_000:
        view_score = 9
    elif views >= 500_000:
        view_score = 8
    elif views >= 100_000:
        view_score = 7
    elif views >= 50_000:
        view_score = 6
    elif views >= 10_000:
        view_score = 5
    elif views >= 5_000:
        view_score = 4
    else:
        view_score = 3
    
    # Like/View oranı
    if views > 0:
        like_ratio = likes / views
        if like_ratio > 0.05:    # %5+ like oranı = çok iyi
            ratio_bonus = 2.0
        elif like_ratio > 0.03:
            ratio_bonus = 1.0
        elif like_ratio > 0.02:
            ratio_bonus = 0.5
        else:
            ratio_bonus = 0.0
    else:
        ratio_bonus = 0.0
    
    # Comment/View oranı (yüksek = tartışmalı veya ilgi çekici)
    if views > 0:
        comment_ratio = comments / views
        if comment_ratio > 0.01:
            comment_bonus = 1.5
        elif comment_ratio > 0.005:
            comment_bonus = 0.75
        else:
            comment_bonus = 0.0
    else:
        comment_bonus = 0.0
    
    score = view_score * 0.6 + (ratio_bonus + comment_bonus) * 2
    return max(0, min(10, score))
```

#### 7.5 Freshness Score (Tazelik) — 0-10

```python
def calc_freshness_score(video: dict) -> float:
    age_days = (now() - video.published_at).days
    
    # "Freshness" sadece yenilik değil!
    # Stratejik yaklaşım:
    
    if age_days <= 7:
        score = 8.0    # Çok taze: güncel ama henüz başkaları clip'lemiş olabilir
    elif age_days <= 30:
        score = 9.5    # Sweet spot: yeterli view almış + henüz over-clip'lenmemiş
    elif age_days <= 90:
        score = 8.5    # Hala güncel
    elif age_days <= 180:
        score = 7.0    # Orta yaş
    elif age_days <= 365:
        score = 6.5    # Muhtemelen clip'lenmemiş, evergreen olabilir
    elif age_days <= 730:
        score = 6.0    # 1-2 yıl: rekabet düşük, evergreen potansiyeli
    elif age_days <= 1825:
        score = 5.0    # 2-5 yıl: sadece gerçekten iyi içerik
    else:
        score = 4.0    # 5+ yıl: çok eski
    
    # Eski ama çok izlenen = evergreen bonusu
    if age_days > 365 and video.view_count > 1_000_000:
        score += 1.5  # kanıtlanmış evergreen
    
    return max(0, min(10, score))
```

#### 7.6 Uniqueness Score (Benzersizlik) — 0-10

```python
def calc_uniqueness_score(video: dict, channel_id: str) -> float:
    score = 8.0  # başlangıç: yüksek (bilinmiyor = muhtemelen benzersiz)
    
    # Son 30 günde bu kanaldan önerdiğimiz videolar
    recent = supabase.select("discovered_content")
        .eq("channel_id", channel_id)
        .gt("discovered_at", now() - timedelta(days=30))
        .neq("status", "dismissed")
        .execute()
    
    for r in recent.data:
        # Aynı YouTube kanalından mı? (-1.5 her tekrar için)
        if r["youtube_channel_id"] == video.channel_id:
            score -= 1.5
        
        # Aynı konuk mu? (-2.0)
        if (r.get("detected_guest_name") and 
            video.get("detected_guest_name") and
            r["detected_guest_name"].lower() == video["detected_guest_name"].lower()):
            score -= 2.0
        
        # Başlık benzerliği kontrolü (basit jaccard)
        similarity = title_similarity(r["title"], video.title)
        if similarity > 0.6:
            score -= 2.0  # çok benzer konu
    
    return max(0, min(10, score))
```

### Quick Score Bileşik Hesaplama

```python
def calculate_quick_score(video: dict, channel_id: str, dna: dict) -> float:
    scores = {
        "topic_match": calc_topic_match(video, dna),
        "guest_potential": calc_guest_potential(video, channel_id),
        "format_score": calc_format_score(video),
        "engagement": calc_engagement_score(video),
        "freshness": calc_freshness_score(video),
        "uniqueness": calc_uniqueness_score(video, channel_id)
    }
    
    # Ağırlıklı ortalama
    weights = {
        "topic_match":    0.30,  # En önemli: kanal DNA uyumu
        "guest_potential": 0.20,  # Konuk kalitesi çok önemli
        "format_score":   0.10,  # Format uygunluğu
        "engagement":     0.15,  # Kanıtlanmış ilgi
        "freshness":      0.10,  # Tazelik stratejisi
        "uniqueness":     0.15   # Çeşitlilik
    }
    
    composite = sum(scores[k] * weights[k] for k in scores)
    
    # Kaydet (F05'te lazım)
    video["scores"] = scores
    video["quick_score"] = composite
    
    return composite
```

### F04 Çıktısı
Tüm videolar quick_score'a göre sıralanır. **Top 15** video F05'e (deep analysis) gönderilir.

---

## 8. F05 — DEEP ANALYSIS (Derin Analiz)

Bu faz kritik. Quick Score yüzeysel. Burada videonun **içeriğine** bakıyoruz.

### 8.1 Transkript Elde Etme

```python
def get_transcript(youtube_video_id: str) -> str | None:
    """
    Öncelik sırası:
    1. YouTube auto-captions (ücretsiz, hızlı)
    2. YouTube manual captions (ücretsiz, daha doğru)
    3. None (transkript yoksa metadata ile devam)
    """
    
    # YouTube Captions API
    captions = youtube.captions().list(
        part="snippet",
        videoId=youtube_video_id
    ).execute()
    
    for caption in captions.get("items", []):
        if caption["snippet"]["language"] == "en":
            # Download caption
            transcript = youtube.captions().download(
                id=caption["id"],
                tfmt="srt"  # SRT format
            ).execute()
            return parse_srt_to_text(transcript)
    
    return None
```

**Neden Deepgram kullanmıyoruz?**
- Discovery fazında 15 video için Deepgram çalıştırmak çok pahalı
- YouTube auto-captions %85-90 doğrulukta, keşif için yeterli
- Deepgram ancak Clip Extractor'a gönderildikten sonra (S02'de) kullanılır

### 8.2 Transkript Örneklemesi

Tüm transkripti Gemini'ye göndermek gereksiz token harcaması. Stratejik örnekleme yapıyoruz:

```python
def sample_transcript(full_transcript: str, duration_minutes: float) -> str:
    """
    Transkriptin stratejik bölümlerini seç.
    Başlangıç, orta ve son kısımlardan örnekler al.
    """
    lines = full_transcript.split('\n')
    total = len(lines)
    
    # İlk %10 (giriş, konu tanıtımı)
    intro = lines[:int(total * 0.10)]
    
    # %20-%35 arası (ısınma sonrası, ilk güçlü konular)
    early_mid = lines[int(total * 0.20):int(total * 0.35)]
    
    # %45-%60 arası (ortalar, genelde en iyi konuşmalar)
    mid = lines[int(total * 0.45):int(total * 0.60)]
    
    # %70-%85 arası (derinleşme, kişisel hikayeler)
    late = lines[int(total * 0.70):int(total * 0.85)]
    
    # Son %5 (kapanış, özet)
    outro = lines[int(total * 0.95):]
    
    sampled = "\n".join(intro + ["...[SKIP]..."] + 
                       early_mid + ["...[SKIP]..."] + 
                       mid + ["...[SKIP]..."] + 
                       late + ["...[SKIP]..."] + 
                       outro)
    
    # Token limiti: max ~4000 kelime
    words = sampled.split()
    if len(words) > 4000:
        sampled = " ".join(words[:4000])
    
    return sampled
```

### 8.3 Gemini Deep Analysis Prompt

```
Sen bir YouTube Shorts kanalı için kaynak video değerlendirmecisisin.
Sana bir long-form videonun transkript örneklemesi ve metadata'sı verilecek.
Bu videonun kısa viral klipler çıkarmak için ne kadar potansiyelli olduğunu analiz et.

KANAL DNA:
{channel_context}  ← build_channel_context() ile oluşturulan (S05 ile aynı format)

VİDEO BİLGİLERİ:
Başlık: {title}
Kanal: {channel_title}
Süre: {duration_minutes} dakika
Görüntülenme: {view_count}
Yayın tarihi: {published_at}
Açıklama: {description[:500]}

TRANSKRİPT ÖRNEKLEMESİ:
{sampled_transcript}

GÖREV:
Bu videonun kanal DNA'sına uygun kısa klipler üretme potansiyelini değerlendir.

CEVAP FORMAT (JSON):
{
  "clip_potential_score": 1-10,
  
  "estimated_clip_count": int,  // bu videodan yaklaşık kaç iyi klip çıkabilir
  
  "detected_moments": [
    {
      "type": "humor | revelation | debate | emotional | storytelling | ...",
      "description": "Bu anda ne oluyor, neden potansiyelli",
      "approximate_location": "başlangıç | erken-orta | orta | geç-orta | son",
      "strength": 1-10
    }
  ],
  
  "guest_assessment": {
    "name": "konuk adı (tespit edildiyse)",
    "charisma_level": 1-10,
    "humor_potential": 1-10,
    "storytelling_ability": 1-10,
    "controversial_potential": 1-10
  },
  
  "conversation_dynamics": {
    "energy_level": "low | medium | high | variable",
    "chemistry": "weak | decent | strong | electric",
    "format_type": "interview | casual_chat | debate | monologue | panel"
  },
  
  "channel_fit_analysis": "Bu videonun bu kanal için neden uygun veya uygun olmadığının 2-3 cümlelik açıklaması",
  
  "risk_factors": ["Potansiyel sorunlar: konu kaymış, konuk sıkıcı, vb."],
  
  "selection_reasoning": "Bu videonun seçilmesi veya atlanması için en önemli 3 sebep"
}

ÖNEMLİ KURALLAR:
1. clip_potential_score 7+ ise = güçlü tavsiye
2. clip_potential_score 5-6 ise = olabilir ama riskli
3. clip_potential_score 4- ise = tavsiye etme
4. Transkript örneklemesinde "[SKIP]" gördüğünde o kısımlar atlanmış demektir, 
   kalan kısımlardan çıkarım yap
5. Konuşma enerjisi ve dinamiği en önemli gösterge — monoton konuşma = kötü clip
6. Kanal DNA'sındaki do_list ile moment türlerini eşleştir
7. Abartma. Gerçekçi ol. 10/10 nadirdir.
```

### 8.4 Transkript Yoksa Ne Olur?

```python
if transcript is None:
    # Sadece metadata ile hafif analiz yap
    # Gemini'ye transkript yerine video title + description + comments gönder
    
    # YouTube API'den top comments çek (50 unit, ucuz)
    comments = youtube.commentThreads().list(
        part="snippet",
        videoId=video_id,
        maxResults=20,
        order="relevance"
    ).execute()
    
    # Yorumlar çok değerli bilgi kaynağı:
    # "32:45 this part killed me 😂" → komik moment var
    # "The story about his childhood was heartbreaking" → duygusal moment var
    # Timestamps içeren yorumlar = potansiyel klip noktaları
    
    # Gemini'ye metadata + comments gönder
    # clip_potential_score max 7 olabilir (transkript olmadan kesinlik düşük)
```

### 8.5 F05 Çıktısı

Her deep-analyzed video için:

```python
{
    # Quick Score'dan gelen
    "quick_scores": {...},
    "quick_composite": 7.2,
    
    # Deep Analysis'ten gelen
    "deep_analysis": {
        "clip_potential_score": 8,
        "estimated_clip_count": 4,
        "detected_moments": [...],
        "guest_assessment": {...},
        "conversation_dynamics": {...},
        "channel_fit_analysis": "...",
        "selection_reasoning": "..."
    },
    
    # Birleşik skor
    "final_score": None  # F06'da hesaplanacak
}
```

---

## 9. F06 — FINAL RANKING & PRESENTATION

### 9.1 Final Skor Hesaplama

```python
def calculate_final_score(video: dict) -> float:
    qs = video["quick_composite"]           # 0-10
    da = video["deep_analysis"]["clip_potential_score"]  # 0-10
    ecc = video["deep_analysis"]["estimated_clip_count"]  # int
    
    # Quick Score ve Deep Analysis birleşimi
    # Deep analysis daha güvenilir, ağırlığı daha yüksek
    blended = qs * 0.35 + da * 0.50 + min(ecc / 6, 1.0) * 10 * 0.15
    
    # Bonus/ceza modülleri
    
    # Goldmine kanal bonusu
    source = get_source_channel(video["youtube_channel_id"])
    if source and source.is_goldmine:
        blended += 0.5
    
    # Conversation dynamics bonusu
    dynamics = video["deep_analysis"]["conversation_dynamics"]
    if dynamics["chemistry"] == "electric":
        blended += 0.75
    elif dynamics["chemistry"] == "strong":
        blended += 0.25
    if dynamics["energy_level"] == "high" or dynamics["energy_level"] == "variable":
        blended += 0.25
    
    # Risk cezası
    risks = video["deep_analysis"].get("risk_factors", [])
    blended -= len(risks) * 0.3
    
    return max(0, min(10, blended))
```

### 9.2 Çeşitlilik Sıralaması (Diversity-Aware Ranking)

Top 5'i seçerken sadece en yüksek skoru sıralamak yetmez. Çeşitlilik şart:

```python
def select_top_5_diverse(candidates: list[dict]) -> list[dict]:
    """
    Hem skor hem çeşitlilik dengeleyerek top 5 seç.
    """
    candidates.sort(key=lambda x: x["final_score"], reverse=True)
    
    selected = []
    used_channels = set()      # kaynak kanal tekrarını engelle
    used_guests = set()        # konuk tekrarını engelle
    used_content_types = []    # moment türü çeşitliliği
    
    for candidate in candidates:
        if len(selected) >= 5:
            break
        
        yt_channel = candidate["youtube_channel_id"]
        guest = candidate.get("detected_guest_name", "").lower()
        
        # Aynı kaynak kanaldan max 2
        if yt_channel in used_channels:
            channel_count = sum(1 for s in selected 
                              if s["youtube_channel_id"] == yt_channel)
            if channel_count >= 2:
                continue
        
        # Aynı konuk max 1
        if guest and guest in used_guests:
            continue
        
        selected.append(candidate)
        used_channels.add(yt_channel)
        if guest:
            used_guests.add(guest)
    
    # Yetersiz kaldıysa (diversity kısıtı çok daraltmışsa)
    # geri kalan en yüksek skorlardan doldur
    if len(selected) < 5:
        for candidate in candidates:
            if candidate not in selected:
                selected.append(candidate)
            if len(selected) >= 5:
                break
    
    return selected
```

### 9.3 Sunum Verisi

Her video kartı için kullanıcıya sunulan bilgiler:

```python
presentation = {
    "video_id": "youtube_video_id",
    "title": "Video başlığı",
    "channel_name": "Kaynak kanal adı",
    "thumbnail_url": "https://img.youtube.com/...",
    "youtube_url": f"https://youtube.com/watch?v={video_id}",
    "duration_formatted": "1:23:45",
    "view_count_formatted": "1.2M views",
    "published_date": "Mar 15, 2024",
    
    # Skorlar (görsel gösterge olarak)
    "final_score": 8.3,
    "score_breakdown": {
        "topic_match": 9,
        "guest_potential": 8,
        "format": 7,
        "engagement": 8,
        "freshness": 9,
        "uniqueness": 8,
        "clip_potential": 8
    },
    
    # Neden seçildi? (Kullanıcının göreceği açıklama)
    "why_selected": {
        "summary": "Bu video kanalınız için güçlü bir kaynak çünkü...",
        "key_reasons": [
            "Konuk (Theo Von) yüksek mizah potansiyeline sahip",
            "Konuşma dinamiği çok enerjik — chemistry electric",
            "En az 4 potansiyel klip noktası tespit edildi"
        ],
        "detected_moments": [
            {"type": "humor", "description": "Konuğun çocukluk hikayesi — şaşırtıcı final"},
            {"type": "revelation", "description": "Sektör hakkında şok edici itiraf"},
            {"type": "funny_reaction", "description": "Host'un beklenmedik tepkisi"}
        ],
        "risk_warnings": ["Videonun son 20 dakikası teknik konulara kayıyor"]
    },
    
    # Konuk bilgisi
    "guest_info": {
        "name": "Theo Von",
        "assessment": "Yüksek karizmatik, güçlü hikaye anlatıcısı, mizah stili kanalınıza uygun"
    },
    
    # Aksiyonlar
    "actions": {
        "can_send_to_clipper": True,
        "can_download": True,
        "can_bookmark": True,
        "can_dismiss": True
    }
}
```

---

## 10. VERİTABANI ŞEMASI

### 10.1 discovered_content Tablosu

```sql
CREATE TABLE discovered_content (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id            TEXT NOT NULL REFERENCES channels(id),
    
    -- YouTube Video Bilgileri
    youtube_video_id      TEXT NOT NULL,
    youtube_channel_id    TEXT,
    youtube_channel_name  TEXT,
    title                 TEXT NOT NULL,
    description           TEXT,
    duration_seconds      INT,
    published_at          TIMESTAMPTZ,
    view_count            INT,
    like_count            INT,
    comment_count         INT,
    thumbnail_url         TEXT,
    youtube_url           TEXT,
    tags                  JSONB,           -- YouTube video tags
    
    -- Quick Score (F04)
    topic_match_score     FLOAT,
    guest_potential_score  FLOAT,
    format_score          FLOAT,
    engagement_score      FLOAT,
    freshness_score       FLOAT,
    uniqueness_score      FLOAT,
    quick_composite_score FLOAT,
    
    -- Deep Analysis (F05)
    deep_analyzed         BOOLEAN DEFAULT false,
    clip_potential_score  FLOAT,           -- Gemini'den (1-10)
    estimated_clip_count  INT,
    detected_moments      JSONB,           -- [{type, description, strength}]
    guest_assessment      JSONB,           -- {name, charisma, humor, ...}
    conversation_dynamics JSONB,           -- {energy, chemistry, format_type}
    channel_fit_analysis  TEXT,            -- Gemini açıklaması
    risk_factors          JSONB,           -- ["risk1", "risk2"]
    selection_reasoning   TEXT,            -- Gemini reasoning
    transcript_available  BOOLEAN DEFAULT false,
    
    -- Final Score (F06)
    final_score           FLOAT,
    
    -- Konuk Bilgisi
    detected_guest_name   TEXT,
    guest_profile_id      UUID REFERENCES guest_profiles(id),
    
    -- Discovery Metadata
    discovery_run_id      UUID REFERENCES discovery_runs(id),
    discovery_strategy    TEXT,            -- topic_search | channel_mining | guest_hunt | related_chain | niche_explorer
    search_query          TEXT,            -- bu videoyu bulan sorgu
    
    -- Kullanıcı Aksiyonları
    status                TEXT DEFAULT 'new',
    -- 'new' | 'recommended' | 'bookmarked' | 'sent_to_clipper' | 
    -- 'dismissed' | 'processed' | 'archived'
    
    presented_at          TIMESTAMPTZ,     -- kullanıcıya gösterildi mi
    bookmarked_at         TIMESTAMPTZ,
    dismissed_at          TIMESTAMPTZ,
    dismiss_reason        TEXT,            -- kullanıcı neden geçti?
    
    -- Clip Extractor Entegrasyonu
    sent_to_clipper_at    TIMESTAMPTZ,
    job_id                UUID REFERENCES jobs(id),
    clips_produced        INT,             -- kaç klip çıktı (geri bildirim)
    clips_passed          INT,             -- kaç klip quality gate'i geçti
    
    -- Tekrar engelleme
    UNIQUE(channel_id, youtube_video_id),
    
    discovered_at         TIMESTAMPTZ DEFAULT now(),
    updated_at            TIMESTAMPTZ DEFAULT now()
);

-- İndeksler
CREATE INDEX idx_dc_channel_status ON discovered_content(channel_id, status);
CREATE INDEX idx_dc_channel_score ON discovered_content(channel_id, final_score DESC);
CREATE INDEX idx_dc_youtube_vid ON discovered_content(youtube_video_id);
CREATE INDEX idx_dc_discovered_at ON discovered_content(discovered_at DESC);
```

### 10.2 source_channels Tablosu

```sql
CREATE TABLE source_channels (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id               TEXT NOT NULL REFERENCES channels(id),
    
    -- YouTube Kanal Bilgileri
    youtube_channel_id       TEXT NOT NULL,
    youtube_channel_name     TEXT,
    youtube_channel_url      TEXT,
    subscriber_count         INT,
    total_video_count        INT,
    
    -- Skorlama
    relevance_score          FLOAT DEFAULT 5.0,  -- kanal DNA uyumu (1-10)
    quality_score            FLOAT DEFAULT 5.0,  -- tarihsel klip kalitesi (1-10)
    hit_rate                 FLOAT DEFAULT 0.0,  -- başarılı klip / toplam video oranı
    
    -- İstatistikler
    total_videos_discovered  INT DEFAULT 0,
    total_videos_processed   INT DEFAULT 0,
    successful_clips_produced INT DEFAULT 0,
    avg_clip_score           FLOAT,
    
    -- Tarama Durumu
    last_scanned_at          TIMESTAMPTZ,
    scan_depth               TEXT DEFAULT 'recent',  -- 'recent' | 'partial' | 'full_catalog'
    last_video_checked_at    TIMESTAMPTZ,  -- en son kontrol edilen videonun tarihi
    
    -- Goldmine Tespiti
    is_goldmine              BOOLEAN DEFAULT false,
    goldmine_detected_at     TIMESTAMPTZ,
    
    -- Kaynak
    added_by                 TEXT DEFAULT 'algorithm',  -- 'algorithm' | 'manual' | 'auto_from_clipper'
    notes                    TEXT,
    
    -- Aktiflik
    is_active                BOOLEAN DEFAULT true,
    
    UNIQUE(channel_id, youtube_channel_id),
    
    created_at               TIMESTAMPTZ DEFAULT now(),
    updated_at               TIMESTAMPTZ DEFAULT now()
);
```

### 10.3 discovery_runs Tablosu

```sql
CREATE TABLE discovery_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id          TEXT NOT NULL REFERENCES channels(id),
    
    run_type            TEXT NOT NULL,  -- 'daily_auto' | 'manual' | 'deep_scan'
    
    -- Strateji Detayları
    strategies_used     JSONB,          -- ["topic_search", "channel_mining", ...]
    queries_generated   INT,
    queries_executed    INT,
    
    -- Sonuçlar
    raw_results_count   INT,            -- API'den gelen toplam
    after_filter_count  INT,            -- filtreleme sonrası
    deep_analyzed_count INT,            -- derin analiz yapılan
    final_recommended   INT,            -- top 5'e giren
    
    -- Skor Dağılımı
    avg_final_score     FLOAT,
    max_final_score     FLOAT,
    min_final_score     FLOAT,
    
    -- API Kullanımı
    youtube_api_units_used INT,
    gemini_tokens_used  INT,
    
    -- Zamanlama
    started_at          TIMESTAMPTZ DEFAULT now(),
    completed_at        TIMESTAMPTZ,
    duration_seconds    INT,
    
    status              TEXT DEFAULT 'running',  -- 'running' | 'completed' | 'failed'
    error_message       TEXT
);
```

### 10.4 discovery_queries Tablosu

```sql
CREATE TABLE discovery_queries (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id            UUID REFERENCES discovery_runs(id),
    channel_id        TEXT NOT NULL,
    
    query             TEXT NOT NULL,
    strategy          TEXT NOT NULL,
    priority          INT,
    
    results_count     INT,              -- bu sorgudan kaç video geldi
    new_discoveries   INT,              -- kaç tanesi yeni (daha önce bilinmeyen)
    high_score_count  INT,              -- kaç tanesi eşik üstü skor aldı
    
    api_units_used    INT,
    executed_at       TIMESTAMPTZ DEFAULT now()
);
```

---

## 11. API ENDPOINTLERİ

```python
# Dosya: backend/app/api/routes/content_finder.py

# ── Discovery Çalıştırma ──────────────────────────

POST /content-finder/discover/{channel_id}
    """Manuel discovery başlat"""
    Input: {
        "run_type": "manual" | "deep_scan",  # varsayılan: manual
        "strategies": ["topic_search", "channel_mining", ...]  # opsiyonel
    }
    Output: { "run_id": uuid, "status": "started" }
    İşlem: Arka planda discovery pipeline başlatır (BackgroundTasks)

GET /content-finder/discover/{run_id}/status
    """Discovery çalışmasının durumunu kontrol et"""
    Output: {
        "status": "running" | "completed" | "failed",
        "progress": {
            "current_phase": "F01" | "F02" | "F03" | "F04" | "F05" | "F06",
            "queries_done": 8,
            "queries_total": 15,
            "videos_analyzed": 3,
            "videos_total": 15
        }
    }

# ── Öneriler ──────────────────────────────────────

GET /content-finder/recommendations/{channel_id}
    """Kanal için güncel önerileri getir"""
    Query params:
        limit: int = 5
        offset: int = 0
        min_score: float = 5.0  (opsiyonel filtre)
        status: str = "recommended"
    Output: {
        "recommendations": [
            {
                "id": uuid,
                "video": { ...video bilgileri... },
                "scores": { ...skor detayları... },
                "why_selected": { ...açıklama... },
                "guest_info": { ...konuk bilgisi... }
            }
        ],
        "last_discovery_at": timestamp,
        "total_available": int
    }

GET /content-finder/feed/{channel_id}
    """Tüm keşfedilen içerikleri getir (filtrelenebilir)"""
    Query params:
        status: str (filtre)
        sort_by: "score" | "date" | "views"
        search: str (başlık araması)
        limit: int = 20
        offset: int = 0

GET /content-finder/content/{content_id}
    """Tek bir içerik detayı"""

# ── Kullanıcı Aksiyonları ─────────────────────────

POST /content-finder/content/{content_id}/send-to-clipper
    """İçeriği Clip Extractor'a gönder"""
    Input: {
        "guest_name": str,           # opsiyonel override
        "trim_start_seconds": float, # opsiyonel
        "trim_end_seconds": float    # opsiyonel
    }
    İşlem:
        1. YouTube'dan video indir (yt-dlp)
        2. jobs tablosuna yeni job oluştur
        3. discovered_content.status → 'sent_to_clipper'
        4. discovered_content.job_id → yeni job_id
        5. Pipeline başlat (Modül 1)
    Output: { "job_id": uuid, "status": "queued" }

POST /content-finder/content/{content_id}/bookmark
    """İçeriği yer imlerine ekle"""
    Output: { "status": "bookmarked" }

POST /content-finder/content/{content_id}/dismiss
    """İçeriği geç"""
    Input: { "reason": str }  # opsiyonel
    Output: { "status": "dismissed" }

POST /content-finder/content/{content_id}/download
    """Videoyu indir (yt-dlp ile)"""
    İşlem: yt-dlp ile video indirilir, geçici URL döner
    Output: { "download_url": str, "expires_in": 3600 }

# ── Kaynak Kanal Yönetimi ─────────────────────────

GET /content-finder/sources/{channel_id}
    """Kaynak kanalları listele"""
    Output: { "sources": [...], "goldmine_count": int }

POST /content-finder/sources/{channel_id}
    """Yeni kaynak kanal ekle"""
    Input: {
        "youtube_channel_url": str,
        "notes": str
    }
    İşlem: YouTube API ile kanal bilgilerini çek, kaydet

PATCH /content-finder/sources/{source_id}
    """Kaynak kanal güncelle"""
    Input: { "is_active": bool, "notes": str }

DELETE /content-finder/sources/{source_id}
    """Kaynak kanal sil"""

# ── İstatistikler ─────────────────────────────────

GET /content-finder/stats/{channel_id}
    """Discovery performans istatistikleri"""
    Output: {
        "total_discovered": int,
        "total_sent_to_clipper": int,
        "total_clips_produced": int,
        "avg_clips_per_video": float,
        "best_source_channels": [...],
        "best_strategies": [...],
        "discovery_success_rate": float
    }
```

---

## 12. VIDEO İNDİRME SİSTEMİ (yt-dlp Entegrasyonu)

```python
# Dosya: backend/app/services/video_downloader.py

import subprocess
import os

class VideoDownloader:
    """
    yt-dlp ile YouTube video indirme.
    Content Finder → Clip Extractor entegrasyonu için.
    """
    
    def download(self, youtube_url: str, output_dir: str, 
                 max_quality: str = "1080") -> str:
        """
        Video indir, dosya yolunu döndür.
        """
        output_template = os.path.join(output_dir, "%(id)s.%(ext)s")
        
        cmd = [
            "yt-dlp",
            "-f", f"bestvideo[height<={max_quality}]+bestaudio/best[height<={max_quality}]",
            "--merge-output-format", "mp4",
            "-o", output_template,
            "--no-playlist",           # playlist değil, tek video
            "--no-post-overwrites",
            "--socket-timeout", "30",
            youtube_url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        if result.returncode != 0:
            raise RuntimeError(f"yt-dlp failed: {result.stderr}")
        
        # İndirilen dosyayı bul
        video_id = extract_video_id(youtube_url)
        downloaded = os.path.join(output_dir, f"{video_id}.mp4")
        
        if not os.path.exists(downloaded):
            raise FileNotFoundError(f"Downloaded file not found: {downloaded}")
        
        return downloaded
    
    def get_info(self, youtube_url: str) -> dict:
        """Video bilgilerini indir, indirmeden."""
        cmd = ["yt-dlp", "--dump-json", "--no-download", youtube_url]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return json.loads(result.stdout)
```

**Dockerfile'a eklenmesi gereken:**
```dockerfile
RUN pip install yt-dlp
# veya
RUN apt-get install -y yt-dlp
```

---

## 13. FRONTEND TASARIMI

### 13.1 Sayfa Yapısı

```
app/
├── content-finder/
│   └── page.tsx                    → Content Finder ana sayfası
├── components/
│   └── content-finder/
│       ├── RecommendationCard.tsx   → Video öneri kartı
│       ├── ScoreBreakdown.tsx       → Skor detay gösterimi
│       ├── WhySelected.tsx         → "Neden seçildi" açılır panel
│       ├── SourceChannels.tsx      → Kaynak kanal yönetimi
│       ├── DiscoveryStatus.tsx     → Keşif durumu gösterimi
│       ├── ContentFeed.tsx         → Tüm keşfedilen içerik listesi
│       └── FilterBar.tsx           → Filtreleme ve sıralama
├── stores/
│   └── content-finder-store.ts     → Zustand store
```

### 13.2 Ana Sayfa Layout

```
┌──────────────────────────────────────────────────────────────┐
│  [Logo]  [Clip Extractor] [Editor] [★ Content Finder]       │
│                                      Kanal: [▼ SpeedyCast]  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─ TODAY'S TOP PICKS ────────────────────────────────────┐  │
│  │                                                         │  │
│  │  Son keşif: 2 saat önce  [🔄 Yeni Keşif Başlat]       │  │
│  │                                                         │  │
│  │  ┌─────────────────────────────────────────────────┐   │  │
│  │  │ 📺  🏆 8.3/10                                   │   │  │
│  │  │  [thumbnail]  "Theo Von on Joe Rogan - Craziest │   │  │
│  │  │               Stories"                           │   │  │
│  │  │  JRE · 2.1M views · 1:42:30 · Mar 2024         │   │  │
│  │  │                                                  │   │  │
│  │  │  ✨ 4 potansiyel klip · Guest: Theo Von         │   │  │
│  │  │                                                  │   │  │
│  │  │  [▶ Neden Seçildi?]                             │   │  │
│  │  │                                                  │   │  │
│  │  │  [🚀 Klip Çıkartıcıya Gönder] [⬇ İndir]       │   │  │
│  │  │  [🔖 Yer İmi] [✕ Geç]                          │   │  │
│  │  └─────────────────────────────────────────────────┘   │  │
│  │                                                         │  │
│  │  ┌─────────────────────────────────────────────────┐   │  │
│  │  │  ... (kart 2)                                    │   │  │
│  │  └─────────────────────────────────────────────────┘   │  │
│  │  ... (toplam 5 kart)                                   │  │
│  │                                                         │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─ BROWSE ALL ───────────────────────────────────────────┐  │
│  │  [Hepsi|Yeni|Yer İmleri|Gönderildi|Geçildi]           │  │
│  │  Sort: [Skor ▼] [Tarih] [View]  Search: [______]      │  │
│  │                                                         │  │
│  │  (tüm keşfedilen içerik listesi, sayfalı)             │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─ SOURCE CHANNELS ─────────────────────────────────────┐  │
│  │  ⭐ JRE (goldmine) · 12 klip çıktı                    │  │
│  │  ⭐ Flagrant (goldmine) · 8 klip çıktı                │  │
│  │  📺 IMPAULSIVE · 3 klip çıktı                         │  │
│  │  [+ Kaynak Kanal Ekle]                                 │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 13.3 "Neden Seçildi?" Açılır Panel

```
▼ Neden Seçildi?

┌───────────────────────────────────────────────────────┐
│                                                       │
│  📊 Skor Kırılımı                                    │
│  ┌──────────────────────────────────────────────┐    │
│  │ Konu Uyumu     ████████░░  9/10             │    │
│  │ Konuk Potansiyeli ███████░░░  8/10           │    │
│  │ Format          ███████░░░  7/10             │    │
│  │ Etkileşim       ████████░░  8/10             │    │
│  │ Tazelik         █████████░  9/10             │    │
│  │ Benzersizlik    ████████░░  8/10             │    │
│  │ Klip Potansiyeli ████████░░  8/10            │    │
│  └──────────────────────────────────────────────┘    │
│                                                       │
│  🎯 Seçilme Nedenleri                                │
│  • Theo Von, kanalınızın hedef kitlesine çok uygun   │
│    bir mizah tarzına sahip (hard humor, şaşırtıcı    │
│    hikayeler)                                         │
│  • Konuşma dinamiği çok enerjik, chemistry           │
│    "electric" seviyesinde                             │
│  • En az 4 potansiyel viral klip noktası tespit      │
│    edildi                                             │
│                                                       │
│  🎬 Tespit Edilen Momentler                          │
│  1. 😂 Humor — Çocukluk hikayesi, şaşırtıcı final  │
│  2. 💥 Revelation — Sektör hakkında şok edici itiraf│
│  3. 😄 Funny Reaction — Host'un beklenmedik tepkisi  │
│  4. 🎭 Storytelling — Ünlü ile karşılaşma hikayesi  │
│                                                       │
│  👤 Konuk Değerlendirmesi                            │
│  Theo Von — Komedyen                                 │
│  Karizma: 9/10 · Mizah: 10/10 · Hikaye: 8/10       │
│                                                       │
│  ⚠️ Risk Uyarıları                                   │
│  • Son 20 dakika teknik konulara kayıyor             │
│                                                       │
└───────────────────────────────────────────────────────┘
```

### 13.4 Zustand Store

```typescript
// stores/content-finder-store.ts

interface ContentFinderState {
  // Aktif kanal
  activeChannelId: string | null;
  
  // Öneriler
  recommendations: DiscoveredContent[];
  isLoadingRecommendations: boolean;
  
  // Feed
  feed: DiscoveredContent[];
  feedFilter: {
    status: string;
    sortBy: 'score' | 'date' | 'views';
    search: string;
  };
  feedPagination: { offset: number; total: number };
  
  // Discovery durumu
  activeDiscoveryRun: DiscoveryRun | null;
  isDiscovering: boolean;
  
  // Kaynak kanallar
  sourceChannels: SourceChannel[];
  
  // Aksiyonlar
  fetchRecommendations: (channelId: string) => Promise<void>;
  fetchFeed: (channelId: string, filters?: any) => Promise<void>;
  startDiscovery: (channelId: string) => Promise<void>;
  sendToClipper: (contentId: string, options?: any) => Promise<void>;
  bookmarkContent: (contentId: string) => Promise<void>;
  dismissContent: (contentId: string, reason?: string) => Promise<void>;
  downloadContent: (contentId: string) => Promise<string>;
  addSourceChannel: (channelId: string, youtubeUrl: string) => Promise<void>;
}
```

---

## 14. GERİ BİLDİRİM DÖNGÜSÜ (Learning Loop)

Bu en kritik kısım. Sistem zamanla **öğrenmeli**.

### 14.1 Clip Extractor'dan Geri Bildirim

```python
# Her Clip Extractor job tamamlandığında:

async def on_clipper_job_completed(job_id: str):
    """
    Modül 1 tamamlandığında Content Finder'ı güncelle.
    """
    job = get_job(job_id)
    clips = get_clips_for_job(job_id)
    
    # 1. discovered_content güncelle
    discovery = supabase.select("discovered_content")
        .eq("job_id", job_id)
        .single()
        .execute()
    
    if discovery.data:
        total_clips = len(clips)
        passed_clips = len([c for c in clips if c.quality_verdict == "pass"])
        
        supabase.update("discovered_content")
            .eq("id", discovery.data["id"])
            .set({
                "status": "processed",
                "clips_produced": total_clips,
                "clips_passed": passed_clips
            })
            .execute()
    
    # 2. source_channels güncelle
    source = get_source_channel_by_youtube_id(
        job.channel_id,
        discovery.data["youtube_channel_id"]
    )
    
    if source:
        source.total_videos_processed += 1
        source.successful_clips_produced += passed_clips
        source.hit_rate = source.successful_clips_produced / max(source.total_videos_processed, 1)
        
        # Goldmine tespiti: 3+ video işlendi ve hit_rate > %50
        if (source.total_videos_processed >= 3 and 
            source.hit_rate > 0.5 and 
            not source.is_goldmine):
            source.is_goldmine = True
            source.goldmine_detected_at = now()
        
        save_source_channel(source)
    else:
        # Yeni kaynak kanal otomatik ekle
        create_source_channel(
            channel_id=job.channel_id,
            youtube_channel_id=discovery.data["youtube_channel_id"],
            youtube_channel_name=discovery.data["youtube_channel_name"],
            added_by="auto_from_clipper"
        )
    
    # 3. Gelecek sorgular için öğrenme
    # Hangi arama sorgusu bu başarılı videoyu buldu?
    if passed_clips > 0:
        query = supabase.select("discovery_queries")
            .eq("run_id", discovery.data["discovery_run_id"])
            .execute()
        # Başarılı sorgu kalıplarını kaydet → gelecek F01'de kullan
```

### 14.2 Discovery Memory (Keşif Hafızası)

```python
def get_discovery_memory(channel_id: str) -> dict:
    """
    Son 90 günün keşif performansını özetler.
    F01 (Query Generation) ve F04 (Quick Score) için kullanılır.
    """
    
    # En başarılı kaynak kanallar
    best_sources = supabase.rpc("get_best_source_channels", {
        "p_channel_id": channel_id,
        "p_days": 90,
        "p_limit": 5
    }).execute()
    
    # En başarılı arama sorguları
    best_queries = supabase.rpc("get_best_queries", {
        "p_channel_id": channel_id,
        "p_days": 90,
        "p_limit": 10
    }).execute()
    
    # Başarısız içerik türleri (dismiss edilen veya klip çıkamayan)
    failed_patterns = supabase.rpc("get_failed_patterns", {
        "p_channel_id": channel_id,
        "p_days": 90
    }).execute()
    
    # En başarılı konuk tipleri
    best_guest_types = supabase.rpc("get_best_guest_types", {
        "p_channel_id": channel_id,
        "p_days": 90
    }).execute()
    
    return {
        "best_sources": best_sources.data,
        "best_queries": best_queries.data,
        "failed_patterns": failed_patterns.data,
        "best_guest_types": best_guest_types.data,
        "total_discovered": total,
        "total_processed": processed,
        "success_rate": success_rate
    }
```

---

## 15. OTOMASYON VE ZAMANLAMA

### 15.1 Günlük Otomatik Keşif

```python
# Dosya: backend/app/content_finder/scheduler.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

@scheduler.scheduled_job('cron', hour=3, minute=0)  # Her gün gece 3:00
async def daily_discovery():
    """
    Tüm aktif kanallar için otomatik keşif çalıştır.
    Gece 3:00 → YouTube API kotası sıfırlandıktan sonra.
    """
    channels = get_active_channels()
    
    for channel in channels:
        try:
            run_id = await run_discovery_pipeline(
                channel_id=channel.id,
                run_type="daily_auto",
                strategies=["topic_search", "channel_mining", "guest_hunt"],
                query_count=12
            )
            print(f"[ContentFinder] Daily discovery for {channel.id}: {run_id}")
        except Exception as e:
            print(f"[ContentFinder] Daily discovery failed for {channel.id}: {e}")
        
        # Kanallar arası bekleme (API rate limit)
        await asyncio.sleep(60)

# main.py'de scheduler başlat
@app.on_event("startup")
async def startup():
    scheduler.start()
```

### 15.2 Manuel Tetikleme

Kullanıcı "Yeni Keşif Başlat" butonuna bastığında manuel tetikleme yapılır. Bu ek stratejilerle daha derin tarama yapabilir.

---

## 16. ORCHESTRATOR

```python
# Dosya: backend/app/content_finder/orchestrator.py

async def run_discovery_pipeline(
    channel_id: str,
    run_type: str = "manual",
    strategies: list[str] = None,
    query_count: int = 15
) -> str:
    """
    Content Finder ana pipeline'ı.
    """
    
    # 1. Discovery run oluştur
    run_id = create_discovery_run(channel_id, run_type)
    
    try:
        # F01: Sorgu Üretimi
        update_run_phase(run_id, "F01")
        channel = get_channel(channel_id)
        dna = channel.channel_dna
        memory = get_discovery_memory(channel_id)
        
        queries = await generate_queries(dna, memory, query_count)
        
        # F02: Çoklu Strateji Arama
        update_run_phase(run_id, "F02")
        raw_results = []
        
        if "topic_search" in (strategies or []):
            raw_results += await topic_search(queries)
        if "channel_mining" in (strategies or []):
            raw_results += await mine_source_channels(channel_id)
        if "guest_hunt" in (strategies or []):
            raw_results += await hunt_guests(channel_id, dna)
        if "related_chain" in (strategies or []):
            raw_results += await follow_related_chain(channel_id)
        if "niche_explorer" in (strategies or []):
            raw_results += await explore_niche(dna)
        
        # F03: Filtreleme
        update_run_phase(run_id, "F03")
        filtered = filter_candidates(raw_results, channel_id)
        
        # Veritabanına kaydet (status: 'new')
        save_discovered_content(filtered, channel_id, run_id)
        
        # F04: Hızlı Puanlama
        update_run_phase(run_id, "F04")
        for video in filtered:
            video["quick_score"] = calculate_quick_score(video, channel_id, dna)
        
        # Quick score'a göre sırala, top 15 seç
        filtered.sort(key=lambda x: x["quick_score"], reverse=True)
        top_candidates = filtered[:15]
        
        # F05: Derin Analiz
        update_run_phase(run_id, "F05")
        for i, video in enumerate(top_candidates):
            update_run_progress(run_id, f"F05", i+1, len(top_candidates))
            
            transcript = await get_transcript(video["youtube_video_id"])
            if transcript:
                sampled = sample_transcript(transcript, video["duration_seconds"]/60)
                analysis = await deep_analyze(video, sampled, dna)
                video["deep_analysis"] = analysis
                video["deep_analyzed"] = True
            else:
                # Transkript yoksa yorumlardan analiz
                comments = await get_top_comments(video["youtube_video_id"])
                analysis = await analyze_from_metadata(video, comments, dna)
                video["deep_analysis"] = analysis
                video["deep_analyzed"] = True
            
            # Veritabanını güncelle
            update_discovered_content(video)
        
        # F06: Final Sıralama
        update_run_phase(run_id, "F06")
        for video in top_candidates:
            video["final_score"] = calculate_final_score(video)
        
        # Çeşitlilik-bilinçli top 5 seç
        top_5 = select_top_5_diverse(top_candidates)
        
        # Status güncelle
        for video in top_5:
            update_content_status(video["id"], "recommended")
        
        # Run tamamlandı
        complete_discovery_run(run_id, {
            "raw_results": len(raw_results),
            "filtered": len(filtered),
            "deep_analyzed": len(top_candidates),
            "recommended": len(top_5),
            "avg_score": mean([v["final_score"] for v in top_5]),
            "max_score": max([v["final_score"] for v in top_5])
        })
        
        return run_id
        
    except Exception as e:
        fail_discovery_run(run_id, str(e))
        raise
```

---

## 17. DOSYA YAPISI

```
backend/app/
├── content_finder/
│   ├── __init__.py
│   ├── orchestrator.py           → Ana pipeline yöneticisi
│   ├── scheduler.py              → Günlük otomatik çalıştırma
│   │
│   ├── phases/
│   │   ├── f01_query_generation.py    → Gemini ile sorgu üretimi
│   │   ├── f02_multi_search.py        → YouTube API aramaları
│   │   ├── f03_filter_dedup.py        → Filtreleme ve tekrar engelleme
│   │   ├── f04_quick_score.py         → Heuristik puanlama
│   │   ├── f05_deep_analysis.py       → Gemini transkript analizi
│   │   └── f06_final_ranking.py       → Çeşitlilik-bilinçli sıralama
│   │
│   ├── prompts/
│   │   ├── query_generation.py        → F01 prompt şablonu
│   │   ├── deep_analysis.py           → F05 prompt şablonu
│   │   ├── guest_discovery.py         → Konuk keşif promptu
│   │   └── metadata_analysis.py       → Transkript yoksa kullanılan prompt
│   │
│   ├── strategies/
│   │   ├── topic_search.py            → Konu bazlı YouTube arama
│   │   ├── channel_mining.py          → Kaynak kanal tarama
│   │   ├── guest_hunt.py              → Konuk avı
│   │   ├── related_chain.py           → İlişkili video zinciri
│   │   └── niche_explorer.py          → Niş keşifçi
│   │
│   └── utils/
│       ├── youtube_api.py             → YouTube Data API wrapper
│       ├── transcript_fetcher.py      → YouTube Captions API
│       ├── guest_extractor.py         → Başlıktan konuk adı çıkarma
│       └── score_calculator.py        → Puanlama fonksiyonları
│
├── services/
│   ├── video_downloader.py            → yt-dlp entegrasyonu (yeni)
│   └── youtube_client.py              → YouTube Data API client (yeni)
│
├── api/routes/
│   └── content_finder.py             → API endpoint'leri (yeni)
```

---

## 18. MODEL KULLANIMI VE MALİYET

| Faz | Model | Kullanım | Günlük Çağrı (2 kanal) |
|-----|-------|----------|------------------------|
| F01 Query Gen | gemini-2.5-flash | Sorgu üretimi | 2 çağrı |
| F05 Deep Analysis | gemini-2.5-flash | Transkript analizi | 30 çağrı (15/kanal) |
| Guest Discovery | gemini-2.5-flash | Konuk araştırma | ~10 çağrı |
| **Toplam Gemini** | | | **~42 çağrı/gün** |

| Harici API | Operasyon | Günlük Kullanım |
|------------|-----------|-----------------|
| YouTube Data API | Search + Video details + Captions | ~7,200 unit/gün |
| Deepgram | Kullanılmıyor (YouTube captions yeterli) | 0 |

**Maliyet tahmini:** Gemini Flash çok ucuz (~$0.01/çağrı). YouTube API ücretsiz (kota dahilinde). Toplam günlük maliyet: **~$0.50**

---

## 19. TEKNİK NOTLAR VE KISITLAMALAR

### YouTube API Kısıtlamaları
1. **Kota:** 10,000 unit/gün. Dikkatli kullanım şart.
2. **Search API sınırlı bilgi verir:** Tam video istatistikleri için ayrı `videos.list` çağrısı gerekir.
3. **Captions her zaman mevcut değil:** Bazı videolarda auto-captions kapalı olabilir.
4. **Related videos:** `relatedToVideoId` parametresi kaldırılabilir (YouTube bu özelliği kısıtlıyor).

### yt-dlp Kısıtlamaları
1. **Büyük dosyalar:** 2+ saatlik videolar GB'lerce olabilir. Disk alanı kontrolü gerekli.
2. **Rate limiting:** YouTube çok fazla indirme yapılırsa IP bloklayabilir.
3. **Güncelleme:** yt-dlp sık güncellenir, Dockerfile'da `pip install --upgrade yt-dlp` kullanılmalı.

### Performans
```
Beklenen süreler:
  F01 (Query Gen):    ~5 saniye
  F02 (Search):       ~30 saniye (15 sorgu, seri)
  F03 (Filter):       ~2 saniye
  F04 (Quick Score):  ~3 saniye
  F05 (Deep Analysis): ~5 dakika (15 video, her biri ~20 saniye)
  F06 (Ranking):      ~1 saniye
  ──────────────────────────────
  Toplam:             ~6-7 dakika / kanal
```

---

## 20. BAŞARI METRİKLERİ

| Metrik | Nasıl Ölçülür | Hedef |
|--------|---------------|-------|
| Discovery Hit Rate | sent_to_clipper'dan pass klip çıkan / toplam gönderilen | > %60 |
| Recommendation Acceptance | sent_to_clipper / recommended | > %40 |
| Dismiss Rate | dismissed / recommended | < %30 |
| Avg Clips Per Video | clips_passed / videos_processed | > 3.0 |
| Source Channel Goldmine Rate | goldmine_count / total_sources | > %20 |
| Query Effectiveness | high_score_results / total_results per query | > %15 |
| Avg Discovery Time | run duration | < 8 dakika |
| Duplicate Detection Rate | duplicates caught / total raw results | izle |
| Transcript Availability | videos with transcript / total deep analyzed | > %80 |
| Daily Recommendation Coverage | channels with fresh recommendations / active channels | %100 |

---

## 21. GELİŞTİRME FAZLARI (Önerilen Sıra)

### Faz 1: Temel Altyapı (1-2 hafta)
- [ ] Veritabanı tabloları oluştur
- [ ] YouTube Data API client yazılması
- [ ] Temel F02 (topic search) implementasyonu
- [ ] F03 (filter & dedup) implementasyonu
- [ ] F04 (quick score) implementasyonu
- [ ] API endpoint'leri (temel CRUD)
- [ ] Frontend: basit liste görünümü

### Faz 2: AI Katmanı (1 hafta)
- [ ] F01 (Gemini query generation) implementasyonu
- [ ] F05 (deep analysis) implementasyonu
- [ ] F06 (final ranking) implementasyonu
- [ ] YouTube Captions API entegrasyonu
- [ ] "Neden seçildi?" açıklama sistemi

### Faz 3: Clip Extractor Entegrasyonu (3-5 gün)
- [ ] yt-dlp video downloader
- [ ] "Klip Çıkartıcıya Gönder" akışı
- [ ] Geri bildirim döngüsü (job tamamlanınca güncelleme)
- [ ] Source channel otomatik keşfi

### Faz 4: Gelişmiş Stratejiler (1 hafta)
- [ ] Channel mining stratejisi
- [ ] Guest hunt stratejisi
- [ ] Related chain stratejisi
- [ ] Goldmine tespit sistemi
- [ ] Discovery memory / öğrenme döngüsü

### Faz 5: Otomasyon ve Polish (3-5 gün)
- [ ] Günlük otomatik keşif scheduler
- [ ] Frontend: tam tasarım (kartlar, filtreler, kaynak kanallar)
- [ ] WebSocket ile discovery progress
- [ ] İstatistik dashboard
- [ ] Performans optimizasyonları

---

Bu plan, mevcut sisteminle tam uyumlu, Channel DNA'yı merkeze alan, hem yeni hem eski içerikleri bulan, zaman içinde öğrenen ve tamamen otomatize edilebilen bir Content Finder modülü tarif ediyor. Her faz bağımsız olarak çalışabilir — Faz 1 bile tek başına işlevsel bir sistem verir.

BEN DİYORUM: şimdi sistemi kurdun çok güzel iyi ama bana şurada yardımcı olman lazım, ben aynısını director modülünü kurarkende yaşadım ve çok büyük bir modül olduklarından bunlar ve bunları yapay zeka geliştirttiğimden bağlam hafızaları sistemin tamamını kapsamıyor,  yani 1 modülde toplam 100 özellik varsa 20-30 tanesini iyi yapıyorum kalan 70-80 özelliği ya hiç yapmıyor yada bir kısmını hatalı ve eksik yapıp diğer kısmını yine hiç yapmıyor gibi bir durum oluyor ama en büyük hata bana yaptım demesine rağmen yapmamış oluyor. Şimdi parça parça verirsem bu seferde gelecek fazları bilmediği için yanlış kodlama ve ya eksik kodlama yapıyor ve ya ben parça parça verirken benim bile aklımda kalmadığından bazı bölümleri yanlış yaptırabiliyorum. Şimdi ben claude code kullanıyorum antigravity terminalinde ona kodlama yaptırıyorum, benim istediğim tüm sistemi bilsin anlasın yani biz ne yapıyoruz bilsin tüm senin bu gönderdiğin planı anlasın ve unutmasın fazlası bölüm bölüm birer birer üzerine inşa etsin istiyorum fakat md dosyası kurmayı denedim bağlam hafızasını arttırmayı denedim ne yaptıysam hiç çözemedim sen olsan nasıl yaptırıdın kısaca? yapay zekaya senin gönderdiğin bu tüm sistemi tanıtıp birebir hiç atlattırmadan yaptırabileceğin bir taktik varmı piyasada

OPUS DİYOR : 

# AI ile Büyük Modül Geliştirme Stratejisi

## Temel Problem

Senin yaşadığın sorun şu: AI'ya büyük bir plan veriyorsun, o da "tamam yaptım" diyor ama aslında %30'unu yapıp %70'ini atlamış oluyor. Ya da parça parça verince bütünü bilmediği için parçalar birbirine uymuyor.

**Çözüm tek kelimeyle: "İskelet önce, et sonra, doğrulama her zaman."**

---

## STRATEJİ: Skeleton → Flesh → Verify

### Mantık

AI'ya plan **döküman olarak değil, kod olarak** ver. Tüm dosyaları, tüm tipleri, tüm fonksiyon imzalarını, tüm API route'larını ÖNCE oluştur — ama içleri boş olsun. Sonra her fonksiyonu TEK TEK doldurt. Her doldurduktan sonra doğrulat.

Neden bu çalışıyor? Çünkü AI bir markdown dökümanını "okuyup unutabiliyor" ama **kodda tanımlı bir type veya fonksiyon imzası varsa, onu takip etmek zorunda kalıyor.** Import hatası alır, type mismatch olur — bunlar onu doğru yolda tutar.

---

## ADIM 0: Veritabanı Tablolarını Oluştur

Bu en önce yapılmalı çünkü her şey bunun üzerine inşa ediliyor.

Claude Code'a vereceğin prompt:

```
Şu 4 tabloyu Supabase'de oluştur. SQL migration dosyalarını yaz.
Hiçbir tabloyu atlama, hiçbir kolonu atlama.

[discovered_content tablosu SQL'ini buraya yapıştır]
[source_channels tablosu SQL'ini buraya yapıştır]
[discovery_runs tablosu SQL'ini buraya yapıştır]
[discovery_queries tablosu SQL'ini buraya yapıştır]

Bitince bana 4 tablonun da kolon listesini göster, doğrulama yapacağım.
```

**Doğrulama:** Sana kolon listesini gösterdiğinde, plan ile karşılaştır. Eksik var mı?

---

## ADIM 1: İskelet Oluşturma (TEK SEFERDE)

Bu en kritik adım. Tüm dosya yapısını, tüm tipleri, tüm fonksiyon imzalarını oluştur ama **hiçbir fonksiyonun içini yazdırma**.

Claude Code'a vereceğin prompt:

```
Content Finder modülü için iskelet kod yapısı oluşturacaksın.

KURALLAR:
1. Tüm dosyaları oluştur
2. Tüm fonksiyon imzalarını yaz
3. Her fonksiyona detaylı docstring yaz (ne alır, ne döner, ne yapar)
4. HİÇBİR FONKSİYONUN İÇİNİ YAZMA — sadece `raise NotImplementedError("TODO")` koy
5. Tüm Pydantic model/type tanımlarını TAMAMEN yaz (bunlar boş OLMAMALI)
6. Tüm import'ları doğru yaz

DOSYA YAPISI:
backend/app/content_finder/
├── __init__.py
├── orchestrator.py
├── scheduler.py
├── models.py              ← TÜM Pydantic modelleri BURADA
├── phases/
│   ├── __init__.py
│   ├── f01_query_generation.py
│   ├── f02_multi_search.py
│   ├── f03_filter_dedup.py
│   ├── f04_quick_score.py
│   ├── f05_deep_analysis.py
│   └── f06_final_ranking.py
├── strategies/
│   ├── __init__.py
│   ├── topic_search.py
│   ├── channel_mining.py
│   ├── guest_hunt.py
│   ├── related_chain.py
│   └── niche_explorer.py
├── prompts/
│   ├── query_generation.py
│   ├── deep_analysis.py
│   └── metadata_analysis.py
└── utils/
    ├── __init__.py
    ├── youtube_api.py
    ├── transcript_fetcher.py
    ├── guest_extractor.py
    └── score_calculator.py

backend/app/api/routes/content_finder.py
backend/app/services/video_downloader.py
backend/app/services/youtube_client.py

Şimdi sana her dosyanın içinde ne olması gerektiğini anlatıyorum:

[Aşağıdaki iskelet spesifikasyonunu yapıştır]
```

Sonra şu iskelet spesifikasyonunu ver:

```python
# ============================================
# models.py — TÜM TİP TANIMLARI (tam yazılacak)
# ============================================

"""
Bu dosyada şu modeller olacak:

1. QueryGenerationResult:
   - query: str
   - strategy: str  ("topic" | "guest" | "niche_deep" | "trending" | "evergreen")
   - expected_content: str
   - priority: int (1-5)

2. YouTubeVideoResult:
   - youtube_video_id: str
   - title: str
   - description: str | None
   - channel_id: str
   - channel_title: str
   - duration_seconds: int
   - published_at: datetime
   - view_count: int
   - like_count: int
   - comment_count: int
   - thumbnail_url: str
   - tags: list[str]
   - format_signal: bool (podcast/interview formatı mı)

3. QuickScores:
   - topic_match: float (0-10)
   - guest_potential: float (0-10)
   - format_score: float (0-10)
   - engagement: float (0-10)
   - freshness: float (0-10)
   - uniqueness: float (0-10)
   - composite: float (0-10, ağırlıklı ortalama)

4. DeepAnalysisResult:
   - clip_potential_score: float (1-10)
   - estimated_clip_count: int
   - detected_moments: list[DetectedMoment]
   - guest_assessment: GuestAssessment | None
   - conversation_dynamics: ConversationDynamics
   - channel_fit_analysis: str
   - risk_factors: list[str]
   - selection_reasoning: str

5. DetectedMoment:
   - type: str (humor | revelation | debate | emotional | storytelling | ...)
   - description: str
   - approximate_location: str
   - strength: int (1-10)

6. GuestAssessment:
   - name: str
   - charisma_level: int (1-10)
   - humor_potential: int (1-10)
   - storytelling_ability: int (1-10)
   - controversial_potential: int (1-10)

7. ConversationDynamics:
   - energy_level: str (low | medium | high | variable)
   - chemistry: str (weak | decent | strong | electric)
   - format_type: str (interview | casual_chat | debate | monologue | panel)

8. DiscoveredContentPresentation:
   - id: str (uuid)
   - video: YouTubeVideoResult
   - scores: QuickScores
   - deep_analysis: DeepAnalysisResult | None
   - final_score: float
   - why_selected: WhySelected
   - guest_info: GuestAssessment | None
   - status: str
   - discovered_at: datetime

9. WhySelected:
   - summary: str
   - key_reasons: list[str]
   - detected_moments: list[DetectedMoment]
   - risk_warnings: list[str]

10. DiscoveryRunStatus:
    - run_id: str
    - status: str (running | completed | failed)
    - current_phase: str (F01-F06)
    - progress: dict
    - started_at: datetime
    - completed_at: datetime | None
"""

# ============================================
# orchestrator.py — ANA PIPELINE
# ============================================

"""
Fonksiyonlar:

1. run_discovery_pipeline(channel_id, run_type, strategies, query_count) -> str
   Docstring: Ana keşif pipeline'ını çalıştırır. F01-F06 fazlarını sırayla çalıştırır.
   Parametreler:
     channel_id: str — hangi kanal için keşif yapılacak
     run_type: str — "daily_auto" | "manual" | "deep_scan"
     strategies: list[str] | None — kullanılacak stratejiler
     query_count: int — üretilecek sorgu sayısı (varsayılan 15)
   Dönüş: run_id (str, uuid)
   İçeride çağırılanlar:
     - f01_query_generation.generate_queries()
     - f02_multi_search.execute_searches()
     - f03_filter_dedup.filter_candidates()
     - f04_quick_score.score_all()
     - f05_deep_analysis.analyze_top_candidates()
     - f06_final_ranking.select_top_diverse()
     - Supabase: discovery_runs INSERT + UPDATE
   Hata: Exception yakalanır, discovery_runs.status → 'failed'

2. get_discovery_memory(channel_id) -> dict
   Docstring: Son 90 günün keşif performansını özetler.
   Dönüş: {"best_sources", "best_queries", "failed_patterns", "success_rate"}
   Kullanıldığı yer: F01 ve F04

3. on_clipper_job_completed(job_id) -> None
   Docstring: Clip Extractor tamamlandığında geri bildirim döngüsünü çalıştırır.
   İşlem: discovered_content güncelle, source_channels güncelle, goldmine tespit
"""

# ============================================
# f01_query_generation.py
# ============================================

"""
Fonksiyonlar:

1. generate_queries(dna, memory, query_count) -> list[QueryGenerationResult]
   Docstring: Channel DNA + hafızadan Gemini ile arama sorguları üretir.
   Kullanılan model: gemini-2.5-flash
   Prompt: prompts/query_generation.py'den alınır
   Giriş: channel_dna (dict), discovery_memory (dict), query_count (int)
   Çıkış: QueryGenerationResult listesi

2. build_query_prompt(dna, memory, query_count) -> str
   Docstring: Gemini'ye gönderilecek prompt'u oluşturur.
"""

# ============================================
# f02_multi_search.py
# ============================================

"""
Fonksiyonlar:

1. execute_searches(queries, channel_id, strategies) -> list[YouTubeVideoResult]
   Docstring: Sorguları ve stratejileri kullanarak YouTube'da arama yapar.
   İçeride çağırılanlar: strategy modüllerindeki fonksiyonlar
   Her strateji paralel veya sıralı çalıştırılabilir.

2. merge_results(all_results) -> list[YouTubeVideoResult]
   Docstring: Farklı stratejilerden gelen sonuçları birleştirir, tekrarları temizler.
"""

# ============================================
# f03_filter_dedup.py
# ============================================

"""
Fonksiyonlar:

1. filter_candidates(raw_results, channel_id) -> list[YouTubeVideoResult]
   Docstring: Ham sonuçları filtreler.
   Filtreler:
     - Süre: 10dk-4saat arası
     - Tekrar: discovered_content + jobs tablosunda kontrol
     - Dil: İngilizce
     - Format: podcast/interview olma ihtimali düşükleri ele
     - No-go zones: channel_dna.no_go_zones kontrolü
   AI kullanmaz, tamamen heuristik.

2. check_duplicate(youtube_video_id, channel_id) -> bool
   Docstring: Bu video daha önce keşfedilmiş mi kontrol eder.

3. estimate_format(title, description) -> tuple[bool, float]
   Docstring: Başlık ve açıklamadan podcast/interview formatı tahmini yapar.
   Dönüş: (is_likely_podcast: bool, confidence: float)
"""

# ============================================
# f04_quick_score.py
# ============================================

"""
Fonksiyonlar:

1. score_all(candidates, channel_id, dna) -> list[dict]
   Docstring: Tüm adayları hızlıca puanlar.
   Her aday için 6 alt skor + composite skor hesaplar.
   AI kullanmaz, tamamen heuristik.

2. calc_topic_match(video, dna) -> float
3. calc_guest_potential(video, channel_id) -> float
4. calc_format_score(video) -> float
5. calc_engagement_score(video) -> float
6. calc_freshness_score(video) -> float
7. calc_uniqueness_score(video, channel_id) -> float
8. calculate_composite(scores) -> float
   Docstring: 6 alt skoru ağırlıklı ortalama ile birleştirir.
   Ağırlıklar: topic_match=0.30, guest_potential=0.20, format=0.10,
               engagement=0.15, freshness=0.10, uniqueness=0.15
"""

# ============================================
# f05_deep_analysis.py
# ============================================

"""
Fonksiyonlar:

1. analyze_top_candidates(candidates, dna, limit=15) -> list[dict]
   Docstring: Top N adayın transkript'ini alıp Gemini ile derin analiz yapar.
   Her aday için: transkript al → örnekle → Gemini'ye gönder → sonuç parse et

2. get_transcript(youtube_video_id) -> str | None
   Docstring: YouTube Captions API ile transkript alır.
   Sıra: auto-captions → manual captions → None

3. sample_transcript(full_transcript, duration_minutes) -> str
   Docstring: Transkriptin stratejik bölümlerini seçer.
   %10 başlangıç + %20-35 erken orta + %45-60 orta + %70-85 geç + %5 son

4. deep_analyze_single(video, sampled_transcript, dna) -> DeepAnalysisResult
   Docstring: Tek bir video için Gemini derin analiz çalıştırır.
   Model: gemini-2.5-flash
   Prompt: prompts/deep_analysis.py'den

5. analyze_from_metadata(video, comments, dna) -> DeepAnalysisResult
   Docstring: Transkript yoksa metadata + yorumlardan analiz yapar.
   clip_potential_score max 7 olabilir.
"""

# ============================================
# f06_final_ranking.py
# ============================================

"""
Fonksiyonlar:

1. calculate_final_scores(candidates) -> list[dict]
   Docstring: Quick score + deep analysis birleştirerek final skor hesaplar.
   Formül: quick*0.35 + deep*0.50 + clip_count_norm*0.15 + bonuslar - cezalar

2. select_top_diverse(candidates, count=5) -> list[dict]
   Docstring: Çeşitlilik-bilinçli top N seçer.
   Kurallar: aynı kanaldan max 2, aynı konuktan max 1

3. generate_presentation(video) -> DiscoveredContentPresentation
   Docstring: Kullanıcıya sunulacak formata dönüştürür.
   why_selected alanını doldurur.
"""

# ============================================
# strategies/topic_search.py
# ============================================

"""
Fonksiyonlar:

1. search_by_topic(queries, channel_id) -> list[YouTubeVideoResult]
   Docstring: Konu bazlı YouTube araması yapar.
   Her sorgunun strategy tipine göre publishedAfter ayarlanır.
   YouTube Search API kullanır (100 unit/sorgu).
"""

# ============================================
# strategies/channel_mining.py
# ============================================

"""
Fonksiyonlar:

1. mine_source_channels(channel_id) -> list[YouTubeVideoResult]
   Docstring: Kayıtlı kaynak kanalların videolarını tarar.
   Goldmine kanallar öncelikli.
   Her kanalın uploads playlist'ini alır.

2. scan_channel_uploads(youtube_channel_id, since) -> list[YouTubeVideoResult]
   Docstring: Tek bir kanalın son videolarını alır.
"""

# ============================================
# strategies/guest_hunt.py
# ============================================

"""
Fonksiyonlar:

1. hunt_guests(channel_id, dna) -> list[YouTubeVideoResult]
   Docstring: Kanal DNA'sına uygun konukları arar.
   Gemini'den ideal konuk listesi alır, her konuk için arama yapar.

2. generate_ideal_guests(dna) -> list[str]
   Docstring: Gemini ile bu kanal için ideal konuk isimleri üretir.
"""

# ============================================
# strategies/related_chain.py
# ============================================

"""
1. follow_related(channel_id) -> list[YouTubeVideoResult]
   Docstring: Başarılı kaynak videoların ilişkili videolarını bulur.
"""

# ============================================
# strategies/niche_explorer.py
# ============================================

"""
1. explore_niche(dna) -> list[YouTubeVideoResult]
   Docstring: Kanalın nişinde geniş kapsamlı arama yapar.
"""

# ============================================
# utils/youtube_api.py
# ============================================

"""
YouTube Data API v3 wrapper fonksiyonları:

1. search_videos(query, max_results, order, published_after, published_before, 
                 video_duration, relevance_language) -> list[dict]
2. get_video_details(video_ids: list[str]) -> list[dict]
3. get_channel_info(channel_id) -> dict
4. get_channel_uploads_playlist(channel_id) -> str
5. get_playlist_items(playlist_id, max_results, published_after) -> list[dict]
6. get_video_comments(video_id, max_results) -> list[dict]
"""

# ============================================
# utils/transcript_fetcher.py
# ============================================

"""
1. fetch_youtube_captions(video_id) -> str | None
   Docstring: YouTube Captions API ile İngilizce transkript alır.
   Sıra: auto → manual → None
"""

# ============================================
# utils/guest_extractor.py
# ============================================

"""
1. extract_guest_name(title) -> str | None
   Docstring: Video başlığından konuk adını çıkarır.
   Kalıplar: "ft.", "with", "w/", "|", "-", "interviews", "sits down with"
"""

# ============================================
# utils/score_calculator.py
# ============================================

"""
Paylaşılan hesaplama utilities:
1. title_similarity(a, b) -> float  (Jaccard similarity)
2. detect_language(text) -> str
3. format_view_count(n) -> str  ("1.2M views")
4. format_duration(seconds) -> str  ("1:23:45")
"""

# ============================================
# services/youtube_client.py
# ============================================

"""
YouTube Data API client (Singleton):

1. YouTubeClient sınıfı
   - __init__: API key ile client oluşturur
   - search(): search.list API çağrısı
   - videos(): videos.list API çağrısı
   - channels(): channels.list API çağrısı
   - playlist_items(): playlistItems.list API çağrısı
   - captions_list(): captions.list API çağrısı
   - captions_download(): captions.download API çağrısı
   - _track_quota(units): kota takibi
   - get_remaining_quota() -> int
"""

# ============================================
# services/video_downloader.py
# ============================================

"""
yt-dlp wrapper:

1. VideoDownloader sınıfı
   - download(youtube_url, output_dir, max_quality) -> str (dosya yolu)
   - get_info(youtube_url) -> dict (indirmeden bilgi al)
"""

# ============================================
# api/routes/content_finder.py
# ============================================

"""
API Endpoint'leri:

POST /content-finder/discover/{channel_id} → start_discovery()
GET  /content-finder/discover/{run_id}/status → get_discovery_status()
GET  /content-finder/recommendations/{channel_id} → get_recommendations()
GET  /content-finder/feed/{channel_id} → get_feed()
GET  /content-finder/content/{content_id} → get_content_detail()
POST /content-finder/content/{content_id}/send-to-clipper → send_to_clipper()
POST /content-finder/content/{content_id}/bookmark → bookmark_content()
POST /content-finder/content/{content_id}/dismiss → dismiss_content()
POST /content-finder/content/{content_id}/download → download_content()
GET  /content-finder/sources/{channel_id} → get_source_channels()
POST /content-finder/sources/{channel_id} → add_source_channel()
PATCH /content-finder/sources/{source_id} → update_source_channel()
DELETE /content-finder/sources/{source_id} → delete_source_channel()
GET  /content-finder/stats/{channel_id} → get_discovery_stats()
"""
```

Sonra Claude Code'a diyorsun ki:

```
Yukarıdaki spesifikasyona göre TÜM dosyaları oluştur.
Her fonksiyonun içi sadece `raise NotImplementedError("TODO: [fonksiyon açıklaması]")` olacak.
AMA şunlar TAM YAZILACAK:
- models.py'deki tüm Pydantic modeller (class tanımları, field'lar, validator'lar)
- Tüm import'lar
- Tüm fonksiyon imzaları ve docstring'ler
- API route'larındaki request/response modelleri

Bitince bana oluşturduğun TÜM dosya isimlerini ve her dosyadaki fonksiyon isimlerini listele.
```

**Doğrulama:** Sana listeyi gösterdiğinde, yukarıdaki spec ile karşılaştır. Eksik dosya veya fonksiyon var mı?

---

## ADIM 2: TASK TRACKER Oluştur

Projenin kök dizinine bir `TASK_TRACKER.md` koy:

```markdown
# Content Finder — Task Tracker

## Durum Simgeleri
- ❌ Yapılmadı
- 🔄 Yapılıyor  
- ✅ Yapıldı
- ✔️ Doğrulandı

## PHASE 1: Temel Altyapı

### Veritabanı
- ✔️ discovered_content tablosu
- ✔️ source_channels tablosu
- ✔️ discovery_runs tablosu
- ✔️ discovery_queries tablosu

### YouTube API Client (services/youtube_client.py)
- ❌ YouTubeClient.__init__
- ❌ YouTubeClient.search
- ❌ YouTubeClient.videos
- ❌ YouTubeClient.channels
- ❌ YouTubeClient.playlist_items
- ❌ YouTubeClient.captions_list
- ❌ YouTubeClient.captions_download
- ❌ YouTubeClient._track_quota
- ❌ YouTubeClient.get_remaining_quota

### YouTube API Utils (utils/youtube_api.py)
- ❌ search_videos
- ❌ get_video_details
- ❌ get_channel_info
- ❌ get_channel_uploads_playlist
- ❌ get_playlist_items
- ❌ get_video_comments

### Topic Search (strategies/topic_search.py)
- ❌ search_by_topic

### Filter & Dedup (phases/f03_filter_dedup.py)
- ❌ filter_candidates
- ❌ check_duplicate
- ❌ estimate_format

### Quick Score (phases/f04_quick_score.py)
- ❌ score_all
- ❌ calc_topic_match
- ❌ calc_guest_potential
- ❌ calc_format_score
- ❌ calc_engagement_score
- ❌ calc_freshness_score
- ❌ calc_uniqueness_score
- ❌ calculate_composite

### Utils
- ❌ guest_extractor.extract_guest_name
- ❌ score_calculator.title_similarity
- ❌ score_calculator.detect_language
- ❌ score_calculator.format_view_count
- ❌ score_calculator.format_duration

### API Routes (Temel)
- ❌ POST /content-finder/discover/{channel_id}
- ❌ GET /content-finder/recommendations/{channel_id}
- ❌ GET /content-finder/feed/{channel_id}
- ❌ POST /content-finder/content/{id}/bookmark
- ❌ POST /content-finder/content/{id}/dismiss

## PHASE 2: AI Katmanı

### Query Generation (phases/f01_query_generation.py)
- ❌ generate_queries
- ❌ build_query_prompt
- ❌ prompts/query_generation.py prompt şablonu

### Deep Analysis (phases/f05_deep_analysis.py)
- ❌ analyze_top_candidates
- ❌ get_transcript
- ❌ sample_transcript
- ❌ deep_analyze_single
- ❌ analyze_from_metadata
- ❌ prompts/deep_analysis.py prompt şablonu
- ❌ prompts/metadata_analysis.py prompt şablonu

### Transcript Fetcher (utils/transcript_fetcher.py)
- ❌ fetch_youtube_captions

### Final Ranking (phases/f06_final_ranking.py)
- ❌ calculate_final_scores
- ❌ select_top_diverse
- ❌ generate_presentation

## PHASE 3: Clip Extractor Entegrasyonu

### Video Downloader (services/video_downloader.py)
- ❌ VideoDownloader.download
- ❌ VideoDownloader.get_info

### Send to Clipper Akışı
- ❌ POST /content-finder/content/{id}/send-to-clipper
- ❌ POST /content-finder/content/{id}/download

### Geri Bildirim Döngüsü
- ❌ orchestrator.on_clipper_job_completed
- ❌ orchestrator.get_discovery_memory

## PHASE 4: Gelişmiş Stratejiler

### Channel Mining (strategies/channel_mining.py)
- ❌ mine_source_channels
- ❌ scan_channel_uploads

### Guest Hunt (strategies/guest_hunt.py)
- ❌ hunt_guests
- ❌ generate_ideal_guests

### Related Chain (strategies/related_chain.py)
- ❌ follow_related

### Niche Explorer (strategies/niche_explorer.py)
- ❌ explore_niche

### Source Channel Yönetimi
- ❌ GET /content-finder/sources/{channel_id}
- ❌ POST /content-finder/sources/{channel_id}
- ❌ PATCH /content-finder/sources/{source_id}
- ❌ DELETE /content-finder/sources/{source_id}
- ❌ Goldmine tespit sistemi

## PHASE 5: Orchestrator & Otomasyon

### Orchestrator (orchestrator.py)
- ❌ run_discovery_pipeline (tüm fazları birleştir)

### Scheduler (scheduler.py)
- ❌ daily_discovery cron job

### Discovery Status
- ❌ GET /content-finder/discover/{run_id}/status

### İstatistikler
- ❌ GET /content-finder/stats/{channel_id}
```

---

## ADIM 3: Fonksiyon Fonksiyon İmplementasyon

İşte burada sihir oluyor. Her seferinde Claude Code'a **sadece 1-3 fonksiyon** ver.

### Prompt Şablonu (Her Fonksiyon İçin Kullan)

```
GÖREV: [fonksiyon_adı] fonksiyonunu implement et.

DOSYA: [dosya_yolu]

FONKSİYON İMZASI (zaten dosyada var):
[fonksiyon imzasını ve docstring'ini yapıştır]

BU FONKSİYON ŞU TİPLERİ KULLANIYOR (models.py'den):
[ilgili Pydantic modelleri yapıştır]

BU FONKSİYON ŞU DİĞER FONKSİYONLARI ÇAĞIRIYOR:
[çağırdığı fonksiyonların imzalarını yapıştır]

BU FONKSİYONU ŞU ÇAĞIRIYOR:
[bu fonksiyonu çağıran yerin imzasını yapıştır]

VERİTABANI TABLOLARI (kullanıyorsa):
[ilgili tablo CREATE SQL'ini yapıştır]

DETAYLI MANTIK:
[planımdaki ilgili bölümü yapıştır — sadece bu fonksiyon ile ilgili kısmı]

KURALLAR:
1. raise NotImplementedError satırını kaldır ve gerçek implementasyonu yaz
2. Docstring'i koru
3. Hata yönetimini ekle (try/except + print log)
4. Fonksiyon dışındaki hiçbir şeyi değiştirme
5. Bitince fonksiyonun tam kodunu göster
```

### Örnek — calc_topic_match İçin

```
GÖREV: calc_topic_match fonksiyonunu implement et.

DOSYA: backend/app/content_finder/phases/f04_quick_score.py

FONKSİYON İMZASI:
def calc_topic_match(video: YouTubeVideoResult, dna: dict) -> float:
    """
    Video başlığı ve açıklamasını channel DNA'nın do_list, dont_list,
    no_go_zones ve sacred_topics alanlarıyla karşılaştırarak
    konu uyum skoru hesaplar.
    
    AI kullanmaz, tamamen keyword matching.
    
    Returns: float 0-10 arası skor
    """
    raise NotImplementedError("TODO")

KULLANILAN TİP:
class YouTubeVideoResult(BaseModel):
    youtube_video_id: str
    title: str
    description: str | None
    ...

CHANNEL DNA YAPISI (dna parametresi):
{
    "do_list": ["Underdog stories", "Gelir detayları", ...],
    "dont_list": ["Ünlü dedikoduları", ...],
    "no_go_zones": ["siyaset", "sağlık iddiaları"],
    "sacred_topics": ["mental health", "relationships"],
    "best_content_types": ["revelation", "debate", "humor"]
}

DETAYLI MANTIK:
[Plandaki calc_topic_match kodunu aynen yapıştır]

Bitince fonksiyonun tam kodunu göster.
```

### Her Fonksiyon Bittikten Sonra Doğrulama

```
TASK_TRACKER.md dosyasında [fonksiyon_adı] satırını ❌ → ✅ olarak güncelle.

Sonra bana şunları doğrula:
1. Fonksiyonun return tipi docstring'deki ile uyuşuyor mu?
2. Kullandığı tüm import'lar dosyanın başında var mı?
3. Çağırdığı diğer fonksiyonlar doğru isim ve parametrelerle çağrılıyor mu?
4. Hata yönetimi var mı?
```

---

## ADIM 4: Faz Sonu Entegrasyon Doğrulaması

Her faz bittiğinde (örneğin Phase 1 tamamen ✅ olduğunda):

```
Phase 1 tamamlandı. Şimdi entegrasyon doğrulaması yap:

1. content_finder/ altındaki TÜM dosyaları oku
2. Şunları kontrol et:
   a. Tüm import'lar çözülüyor mu? (var olmayan modül import ediliyor mu?)
   b. Fonksiyon çağrıları doğru parametrelerle mi yapılıyor?
   c. Veritabanı sorguları doğru tablo ve kolon isimlerini mi kullanıyor?
   d. API route'ları doğru fonksiyonları mı çağırıyor?
   e. Hala `raise NotImplementedError` içeren fonksiyon var mı? (Phase 1 kapsamında olmayanlar hariç)

3. TASK_TRACKER.md'yi oku ve Phase 1'deki tüm satırların ✅ olduğunu doğrula.

4. Sorun varsa listele, ben düzeltme talimatı vereceğim.
```

---

## CLAUDE.md YAPISI

Claude Code'un CLAUDE.md'si kısa ve net olmalı. Tüm planı oraya koyma. Sadece kuralları ve mevcut durumu koy:

```markdown
# CLAUDE.md — Content Finder Modülü

## PROJE BAĞLAMI
Bu proje YouTube Shorts kanalları için otomatik içerik keşif sistemidir.
Mevcut modüller: Clip Extractor (Modül 1), Editor (Modül 2).
Content Finder (Modül 3) long-form podcast/interview videolarını bulur.

## MEVCUT DURUM
Şu an: Phase 1 implementasyonu
Tamamlanan: Veritabanı tabloları, İskelet yapı
Çalışılan: YouTube API client implementasyonu
Referans: TASK_TRACKER.md dosyasına bak

## İMPLEMENTASYON KURALLARI
1. HER ZAMAN mevcut fonksiyon imzasını ve docstring'i koru
2. models.py'deki tipleri kullan, yeni tip ekleme (bana sor önce)
3. Supabase client: services/supabase_client.py'den get_client() kullan
4. Gemini client: services/gemini_client.py'den generate_json() kullan  
5. Hata yönetimi: try/except + print(f"[ContentFinder] Error: {e}")
6. Dosya temizliği: finally bloğunda geçici dosyaları sil
7. Prompt'larda .format() KULLANMA, .replace() kullan
8. Supabase port: 6543 (5432 değil)
9. Tek fonksiyon implement et, diğerlerine dokunma
10. Bitince TASK_TRACKER.md'yi güncelle

## KRİTİK REFERANSLAR
- Veritabanı şeması: migration dosyaları veya system_core.md
- Tip tanımları: backend/app/content_finder/models.py
- Fonksiyon kontratları: Her dosyadaki docstring'ler
- Genel plan: content_finder_plan.md (SADECE referans, değiştirme)
```

---

## ÖZET — Akış Sırası

```
1. DB tablolarını oluştur → doğrula
2. İskelet kodu oluştur (tüm dosyalar, boş fonksiyonlar) → doğrula
3. TASK_TRACKER.md oluştur
4. CLAUDE.md kur
5. Phase 1 fonksiyonlarını TEK TEK implement et
   Her fonksiyon sonrası: doğrula + tracker güncelle
6. Phase 1 bitti → entegrasyon doğrulaması
7. Phase 2 fonksiyonlarını TEK TEK implement et
   ...
8. Phase 5'e kadar tekrarla
```

## Neden Bu Çalışıyor

| Problem | Çözüm |
|---------|-------|
| AI %70'ini atlıyor | Her seferinde sadece 1 fonksiyon, kaçacak yeri yok |
| "Yaptım" diyor ama yapmamış | Doğrulama adımı var, kontrol ediyorsun |
| Parça verince bütünü bilmiyor | İskelet kod zaten tüm yapıyı tanımlıyor, import'lar ve tipler mevcut |
| MD dosyası unutuluyor | MD yerine **gerçek kod** (tip tanımları, fonksiyon imzaları) kullanılıyor |
| Fazlar arası uyumsuzluk | models.py merkezi tip kaynağı, herkes onu kullanıyor |
| Benim aklımda kalmıyor | TASK_TRACKER.md tam liste, nerede olduğun her zaman belli |

Anahtar ilke: **AI'ya plan dökümanı verme, yapısallaşmış kod ver.** Kod yalan söyleyemez — import çalışmazsa hata verir, tip uyuşmazsa patlır. Döküman ise gözden kaçar.

BEN DİYORUM : tamam seninle geliştirelim beraber promptları verelim yapay zekaya o yapsın ne dersin? kod olarak veremeden sırayla her şeyi açıklayarak promptlerını vererek yaptıralım?

OPUS DİYOR : 

Hadi başlayalım. Adım adım gideceğiz. Ben promptu yazacağım, sen Claude Code'a vereceksin, o yapacak, sonra bana sonucu söyleyeceksin, ben doğrulayacağım, sonraki adıma geçeceğiz.

---

## ADIM 0: Veritabanı Tabloları

Bu SQL'leri **Supabase Dashboard → SQL Editor**'de çalıştır (Claude Code'a vermeye gerek yok, direkt Supabase'de çalıştır):

```sql
-- ========================================
-- CONTENT FINDER — VERİTABANI TABLOLARI
-- ========================================

-- 1. Discovery Runs (keşif çalışmaları)
CREATE TABLE discovery_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id          TEXT NOT NULL REFERENCES channels(id),
    run_type            TEXT NOT NULL DEFAULT 'manual',
    strategies_used     JSONB,
    queries_generated   INT DEFAULT 0,
    queries_executed    INT DEFAULT 0,
    raw_results_count   INT DEFAULT 0,
    after_filter_count  INT DEFAULT 0,
    deep_analyzed_count INT DEFAULT 0,
    final_recommended   INT DEFAULT 0,
    avg_final_score     FLOAT,
    max_final_score     FLOAT,
    min_final_score     FLOAT,
    youtube_api_units_used INT DEFAULT 0,
    gemini_tokens_used  INT DEFAULT 0,
    current_phase       TEXT,
    phase_progress      JSONB,
    started_at          TIMESTAMPTZ DEFAULT now(),
    completed_at        TIMESTAMPTZ,
    duration_seconds    INT,
    status              TEXT DEFAULT 'running',
    error_message       TEXT
);

-- 2. Discovery Queries (üretilen arama sorguları)
CREATE TABLE discovery_queries (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id            UUID REFERENCES discovery_runs(id) ON DELETE CASCADE,
    channel_id        TEXT NOT NULL,
    query             TEXT NOT NULL,
    strategy          TEXT NOT NULL,
    priority          INT DEFAULT 3,
    expected_content  TEXT,
    results_count     INT DEFAULT 0,
    new_discoveries   INT DEFAULT 0,
    high_score_count  INT DEFAULT 0,
    api_units_used    INT DEFAULT 0,
    executed_at       TIMESTAMPTZ DEFAULT now()
);

-- 3. Discovered Content (keşfedilen içerikler — ana tablo)
CREATE TABLE discovered_content (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id            TEXT NOT NULL REFERENCES channels(id),
    youtube_video_id      TEXT NOT NULL,
    youtube_channel_id    TEXT,
    youtube_channel_name  TEXT,
    title                 TEXT NOT NULL,
    description           TEXT,
    duration_seconds      INT,
    published_at          TIMESTAMPTZ,
    view_count            INT DEFAULT 0,
    like_count            INT DEFAULT 0,
    comment_count         INT DEFAULT 0,
    thumbnail_url         TEXT,
    youtube_url           TEXT,
    tags                  JSONB,
    detected_guest_name   TEXT,
    guest_profile_id      UUID REFERENCES guest_profiles(id),
    topic_match_score     FLOAT,
    guest_potential_score FLOAT,
    format_score          FLOAT,
    engagement_score      FLOAT,
    freshness_score       FLOAT,
    uniqueness_score      FLOAT,
    quick_composite_score FLOAT,
    deep_analyzed         BOOLEAN DEFAULT false,
    clip_potential_score  FLOAT,
    estimated_clip_count  INT,
    detected_moments      JSONB,
    guest_assessment      JSONB,
    conversation_dynamics JSONB,
    channel_fit_analysis  TEXT,
    risk_factors          JSONB,
    selection_reasoning   TEXT,
    transcript_available  BOOLEAN DEFAULT false,
    final_score           FLOAT,
    discovery_run_id      UUID REFERENCES discovery_runs(id),
    discovery_strategy    TEXT,
    search_query          TEXT,
    status                TEXT DEFAULT 'new',
    presented_at          TIMESTAMPTZ,
    bookmarked_at         TIMESTAMPTZ,
    dismissed_at          TIMESTAMPTZ,
    dismiss_reason        TEXT,
    sent_to_clipper_at    TIMESTAMPTZ,
    job_id                UUID REFERENCES jobs(id),
    clips_produced        INT,
    clips_passed          INT,
    discovered_at         TIMESTAMPTZ DEFAULT now(),
    updated_at            TIMESTAMPTZ DEFAULT now(),
    UNIQUE(channel_id, youtube_video_id)
);

CREATE INDEX idx_dc_channel_status ON discovered_content(channel_id, status);
CREATE INDEX idx_dc_channel_score ON discovered_content(channel_id, final_score DESC);
CREATE INDEX idx_dc_youtube_vid ON discovered_content(youtube_video_id);
CREATE INDEX idx_dc_discovered_at ON discovered_content(discovered_at DESC);

-- 4. Source Channels (kaynak kanallar)
CREATE TABLE source_channels (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id                TEXT NOT NULL REFERENCES channels(id),
    youtube_channel_id        TEXT NOT NULL,
    youtube_channel_name      TEXT,
    youtube_channel_url       TEXT,
    subscriber_count          INT,
    total_video_count         INT,
    relevance_score           FLOAT DEFAULT 5.0,
    quality_score             FLOAT DEFAULT 5.0,
    hit_rate                  FLOAT DEFAULT 0.0,
    total_videos_discovered   INT DEFAULT 0,
    total_videos_processed    INT DEFAULT 0,
    successful_clips_produced INT DEFAULT 0,
    avg_clip_score            FLOAT,
    last_scanned_at           TIMESTAMPTZ,
    scan_depth                TEXT DEFAULT 'recent',
    last_video_checked_at     TIMESTAMPTZ,
    is_goldmine               BOOLEAN DEFAULT false,
    goldmine_detected_at      TIMESTAMPTZ,
    added_by                  TEXT DEFAULT 'manual',
    notes                     TEXT,
    is_active                 BOOLEAN DEFAULT true,
    created_at                TIMESTAMPTZ DEFAULT now(),
    updated_at                TIMESTAMPTZ DEFAULT now(),
    UNIQUE(channel_id, youtube_channel_id)
);
```

**Bunu Supabase'de çalıştırdıktan sonra** bana söyle, doğrulayacağım ve ADIM 1'e geçeceğiz — iskelet kod yapısı.

İlk bu tabloları oluştur, geri dönüş yap 👍

OPUS DİYOR : 

Güzel. Şimdi ADIM 1'e geçiyoruz — iskelet kod yapısı. Bu en kritik adım çünkü tüm modülün omurgasını kuracağız.

Bunu Claude Code'a birden fazla parçada vereceğiz çünkü tek seferde çok büyük. Önce dosya yapısı ve modeller, sonra fazlar, sonra stratejiler ve utils, sonra API routes.

---

## ADIM 1A: Models + Dosya Yapısı

Şunu Claude Code'a ver:

```
Content Finder modülü için iskelet yapı oluşturacaksın. Bu modül YouTube'dan long-form podcast/interview videoları keşfeden bir sistemdir.

ÖNEMLİ KURALLAR:
1. Tüm dosyaları oluştur
2. models.py'deki Pydantic modelleri TAMAMEN yaz (field'lar, tipler, default'lar dahil)
3. Diğer tüm dosyalarda fonksiyon imzaları + docstring yaz ama içlerini YAZMA — sadece raise NotImplementedError("TODO") koy
4. Tüm __init__.py dosyalarını boş oluştur
5. Her dosyanın başına gerekli import'ları yaz

ADIM 1: Önce şu dosyaları oluştur:

=== DOSYA 1: backend/app/content_finder/__init__.py ===
Boş dosya

=== DOSYA 2: backend/app/content_finder/models.py ===
Bu dosyada aşağıdaki Pydantic modellerin TAMAMEN yazılması gerekiyor (BaseModel'den türeyen, tüm field'lar, tipler ve default değerler dahil):

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class QueryGenerationResult(BaseModel):
    query: str
    strategy: str  # "topic" | "guest" | "niche_deep" | "trending" | "evergreen"
    expected_content: str
    priority: int = Field(ge=1, le=5, default=3)

class YouTubeVideoResult(BaseModel):
    youtube_video_id: str
    title: str
    description: Optional[str] = None
    channel_id: str
    channel_title: str
    duration_seconds: int
    published_at: Optional[datetime] = None
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    thumbnail_url: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    format_signal: bool = False
    detected_guest_name: Optional[str] = None

class QuickScores(BaseModel):
    topic_match: float = 5.0
    guest_potential: float = 5.0
    format_score: float = 5.0
    engagement: float = 5.0
    freshness: float = 5.0
    uniqueness: float = 8.0
    composite: float = 5.0

class DetectedMoment(BaseModel):
    type: str  # humor | revelation | debate | emotional | storytelling vs.
    description: str
    approximate_location: str  # başlangıç | erken-orta | orta | geç-orta | son
    strength: int = Field(ge=1, le=10, default=5)

class GuestAssessment(BaseModel):
    name: str
    charisma_level: int = Field(ge=1, le=10, default=5)
    humor_potential: int = Field(ge=1, le=10, default=5)
    storytelling_ability: int = Field(ge=1, le=10, default=5)
    controversial_potential: int = Field(ge=1, le=10, default=5)

class ConversationDynamics(BaseModel):
    energy_level: str = "medium"  # low | medium | high | variable
    chemistry: str = "decent"  # weak | decent | strong | electric
    format_type: str = "interview"  # interview | casual_chat | debate | monologue | panel

class DeepAnalysisResult(BaseModel):
    clip_potential_score: float = Field(ge=1, le=10, default=5)
    estimated_clip_count: int = 0
    detected_moments: list[DetectedMoment] = Field(default_factory=list)
    guest_assessment: Optional[GuestAssessment] = None
    conversation_dynamics: ConversationDynamics = Field(default_factory=ConversationDynamics)
    channel_fit_analysis: str = ""
    risk_factors: list[str] = Field(default_factory=list)
    selection_reasoning: str = ""

class WhySelected(BaseModel):
    summary: str
    key_reasons: list[str] = Field(default_factory=list)
    detected_moments: list[DetectedMoment] = Field(default_factory=list)
    risk_warnings: list[str] = Field(default_factory=list)

class DiscoveredContentPresentation(BaseModel):
    id: str
    video: YouTubeVideoResult
    scores: QuickScores
    deep_analysis: Optional[DeepAnalysisResult] = None
    final_score: float = 0.0
    why_selected: Optional[WhySelected] = None
    guest_info: Optional[GuestAssessment] = None
    status: str = "new"
    discovered_at: Optional[datetime] = None

class DiscoveryRunStatus(BaseModel):
    run_id: str
    status: str = "running"  # running | completed | failed
    channel_id: str = ""
    current_phase: str = ""  # F01 | F02 | F03 | F04 | F05 | F06
    queries_done: int = 0
    queries_total: int = 0
    videos_found: int = 0
    videos_analyzed: int = 0
    videos_total: int = 0
    recommendations_count: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

=== DOSYA 3: backend/app/content_finder/phases/__init__.py ===
Boş dosya

=== DOSYA 4: backend/app/content_finder/strategies/__init__.py ===
Boş dosya

=== DOSYA 5: backend/app/content_finder/prompts/__init__.py ===
Boş dosya

=== DOSYA 6: backend/app/content_finder/utils/__init__.py ===
Boş dosya

Sadece bu 6 dosyayı oluştur. Bitince bana oluşturduğun dosya listesini ve models.py'deki class isimlerini göster.
```

Claude Code bunu yapınca bana söyle, doğrulayıp ADIM 1B'ye geçeceğiz (utils ve services dosyaları).

OPUS DİYOR : 

Güzel. Şimdi ADIM 1B — Utils, Services ve Prompts dosyaları.

Claude Code'a ver:

```
Content Finder modülü için iskelet yapıya devam ediyoruz. Şimdi utils, services ve prompts dosyalarını oluşturacaksın.

ÖNEMLİ KURALLAR:
1. Her fonksiyonun imzasını ve docstring'ini TAMAMEN yaz
2. Fonksiyon içlerini YAZMA — sadece raise NotImplementedError("TODO") koy
3. Import'ları doğru yaz
4. models.py'den gerekli tipleri import et

=== DOSYA 1: backend/app/content_finder/utils/youtube_api.py ===

from app.content_finder.models import YouTubeVideoResult
from typing import Optional
from datetime import datetime


async def search_videos(
    query: str,
    max_results: int = 15,
    order: str = "relevance",
    published_after: Optional[datetime] = None,
    published_before: Optional[datetime] = None,
    video_duration: str = "long",
    relevance_language: str = "en"
) -> list[dict]:
    """
    YouTube Data API v3 search.list çağrısı yapar.
    
    Args:
        query: Arama sorgusu
        max_results: Maksimum sonuç sayısı (1-50)
        order: Sıralama ("relevance" | "viewCount" | "date")
        published_after: Bu tarihten sonra yayınlananlar
        published_before: Bu tarihten önce yayınlananlar
        video_duration: "long" (>20dk) | "medium" (4-20dk) | "any"
        relevance_language: Dil filtresi
    
    Returns:
        YouTube API'den gelen ham video sonuçları listesi
    
    API Cost: 100 unit per call
    """
    raise NotImplementedError("TODO")


async def get_video_details(video_ids: list[str]) -> list[dict]:
    """
    YouTube Data API v3 videos.list çağrısı yapar.
    Birden fazla video ID'si tek çağrıda gönderilebilir (max 50).
    
    Args:
        video_ids: YouTube video ID listesi
    
    Returns:
        Video detayları listesi (statistics, contentDetails, snippet dahil)
    
    API Cost: 1 unit per call (50 video'ya kadar)
    """
    raise NotImplementedError("TODO")


async def get_channel_info(channel_id: str) -> dict:
    """
    YouTube Data API v3 channels.list çağrısı yapar.
    
    Args:
        channel_id: YouTube kanal ID'si
    
    Returns:
        Kanal bilgileri (snippet, statistics, contentDetails)
    
    API Cost: 1 unit
    """
    raise NotImplementedError("TODO")


async def get_channel_uploads_playlist_id(channel_id: str) -> Optional[str]:
    """
    Bir kanalın uploads playlist ID'sini alır.
    channels.list → contentDetails.relatedPlaylists.uploads
    
    Args:
        channel_id: YouTube kanal ID'si
    
    Returns:
        Uploads playlist ID'si veya None
    
    API Cost: 1 unit
    """
    raise NotImplementedError("TODO")


async def get_playlist_items(
    playlist_id: str,
    max_results: int = 50,
    published_after: Optional[datetime] = None
) -> list[dict]:
    """
    YouTube Data API v3 playlistItems.list çağrısı yapar.
    
    Args:
        playlist_id: YouTube playlist ID'si
        max_results: Maksimum sonuç (1-50)
        published_after: Bu tarihten sonra eklenenler (client-side filtre)
    
    Returns:
        Playlist item listesi
    
    API Cost: 1 unit per call
    """
    raise NotImplementedError("TODO")


async def get_video_comments(
    video_id: str,
    max_results: int = 20
) -> list[dict]:
    """
    YouTube Data API v3 commentThreads.list çağrısı yapar.
    En alakalı yorumları alır.
    
    Args:
        video_id: YouTube video ID'si
        max_results: Maksimum yorum sayısı
    
    Returns:
        Yorum listesi [{text, like_count, published_at}, ...]
    
    API Cost: 1 unit per call
    """
    raise NotImplementedError("TODO")


def parse_duration_to_seconds(duration_str: str) -> int:
    """
    YouTube API'nin ISO 8601 süre formatını saniyeye çevirir.
    Örnek: "PT1H23M45S" -> 5025
    
    Args:
        duration_str: ISO 8601 duration string
    
    Returns:
        Saniye cinsinden süre
    """
    raise NotImplementedError("TODO")


def build_youtube_url(video_id: str) -> str:
    """
    Video ID'den YouTube URL'si oluşturur.
    
    Returns:
        "https://www.youtube.com/watch?v={video_id}"
    """
    return f"https://www.youtube.com/watch?v={video_id}"


def build_thumbnail_url(video_id: str) -> str:
    """
    Video ID'den thumbnail URL'si oluşturur.
    maxresdefault tercih edilir.
    
    Returns:
        "https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
    """
    return f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"


=== DOSYA 2: backend/app/content_finder/utils/transcript_fetcher.py ===

from typing import Optional


async def fetch_youtube_captions(video_id: str) -> Optional[str]:
    """
    YouTube video'sunun otomatik veya manuel İngilizce altyazısını alır.
    
    Öncelik sırası:
    1. Manuel İngilizce altyazı (daha doğru)
    2. Otomatik İngilizce altyazı
    3. None (altyazı yoksa)
    
    youtube-transcript-api kütüphanesini kullanır.
    
    Args:
        video_id: YouTube video ID'si
    
    Returns:
        Düz metin transkript veya None
    """
    raise NotImplementedError("TODO")


=== DOSYA 3: backend/app/content_finder/utils/guest_extractor.py ===

from typing import Optional
import re


def extract_guest_name(title: str) -> Optional[str]:
    """
    Video başlığından konuk adını çıkarmaya çalışır.
    
    Tanınan kalıplar:
    - "ft. {Name}" veya "feat. {Name}"
    - "with {Name}"
    - "w/ {Name}"
    - "{Name} | Podcast Name"
    - "{Name} - Topic"
    - "interviews {Name}"
    - "sits down with {Name}"
    - "{Host} & {Guest}"
    - "#{Number} {Name}"  (podcast episode formatı)
    - "{Name} on {Topic}"
    
    Args:
        title: YouTube video başlığı
    
    Returns:
        Tahmin edilen konuk adı veya None
    """
    raise NotImplementedError("TODO")


=== DOSYA 4: backend/app/content_finder/utils/score_calculator.py ===


def title_similarity(title_a: str, title_b: str) -> float:
    """
    İki başlık arasındaki Jaccard benzerliğini hesaplar.
    Kelime bazlı karşılaştırma yapar (lowercase, stop words çıkarılır).
    
    Args:
        title_a: İlk başlık
        title_b: İkinci başlık
    
    Returns:
        0.0 (hiç benzemez) ile 1.0 (aynı) arası float
    """
    raise NotImplementedError("TODO")


def detect_language(text: str) -> str:
    """
    Metnin dilini tespit eder.
    Basit heuristik: İngilizce karakter oranı ve yaygın kelime kontrolü.
    
    Args:
        text: Kontrol edilecek metin
    
    Returns:
        Dil kodu: "en", "tr", "unknown" vs.
    """
    raise NotImplementedError("TODO")


def format_view_count(count: int) -> str:
    """
    Görüntülenme sayısını okunabilir formata çevirir.
    Örnekler: 1234 -> "1.2K", 1500000 -> "1.5M", 2300000000 -> "2.3B"
    
    Args:
        count: Ham sayı
    
    Returns:
        Formatlanmış string
    """
    raise NotImplementedError("TODO")


def format_duration(seconds: int) -> str:
    """
    Saniyeyi okunabilir süre formatına çevirir.
    Örnekler: 3661 -> "1:01:01", 745 -> "12:25", 59 -> "0:59"
    
    Args:
        seconds: Saniye cinsinden süre
    
    Returns:
        Formatlanmış string
    """
    raise NotImplementedError("TODO")


=== DOSYA 5: backend/app/services/youtube_client.py ===

import os
from typing import Optional


class YouTubeClient:
    """
    YouTube Data API v3 client. Singleton pattern.
    API key ile çalışır, OAuth gerektirmez.
    
    Kota takibi yapar: her API çağrısı unit maliyetini düşer.
    Günlük kota: 10,000 unit (Google varsayılan).
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.api_key = os.getenv("YOUTUBE_API_KEY")
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self._daily_quota_used = 0
        self._daily_quota_limit = 10000
    
    async def search(
        self,
        q: str,
        max_results: int = 15,
        order: str = "relevance",
        published_after: Optional[str] = None,
        published_before: Optional[str] = None,
        video_duration: str = "long",
        relevance_language: str = "en",
        type: str = "video"
    ) -> dict:
        """
        search.list API çağrısı.
        API Cost: 100 unit
        
        Args:
            q: Arama sorgusu
            max_results: 1-50 arası
            order: relevance | viewCount | date | rating
            published_after: RFC 3339 format (2024-01-01T00:00:00Z)
            published_before: RFC 3339 format
            video_duration: long (>20dk) | medium (4-20dk) | short (<4dk) | any
            relevance_language: ISO 639-1 dil kodu
            type: video | channel | playlist
        
        Returns:
            YouTube API response dict
        """
        raise NotImplementedError("TODO")
    
    async def videos(
        self,
        video_ids: list[str],
        parts: list[str] = None
    ) -> dict:
        """
        videos.list API çağrısı.
        API Cost: 1 unit (50 video'ya kadar tek çağrı)
        
        Args:
            video_ids: Video ID listesi (max 50)
            parts: İstenen parçalar ["snippet", "statistics", "contentDetails"]
                   Varsayılan: ["snippet", "statistics", "contentDetails"]
        
        Returns:
            YouTube API response dict
        """
        raise NotImplementedError("TODO")
    
    async def channels(
        self,
        channel_ids: list[str] = None,
        for_username: str = None,
        parts: list[str] = None
    ) -> dict:
        """
        channels.list API çağrısı.
        API Cost: 1 unit
        
        Args:
            channel_ids: Kanal ID listesi
            for_username: Kullanıcı adı ile arama
            parts: ["snippet", "statistics", "contentDetails"]
        
        Returns:
            YouTube API response dict
        """
        raise NotImplementedError("TODO")
    
    async def playlist_items(
        self,
        playlist_id: str,
        max_results: int = 50,
        page_token: str = None
    ) -> dict:
        """
        playlistItems.list API çağrısı.
        API Cost: 1 unit
        
        Args:
            playlist_id: Playlist ID
            max_results: 1-50 arası
            page_token: Sayfalama token'ı
        
        Returns:
            YouTube API response dict
        """
        raise NotImplementedError("TODO")
    
    def _track_quota(self, units: int) -> None:
        """
        API kota kullanımını takip eder.
        
        Args:
            units: Harcanan unit sayısı
        """
        self._daily_quota_used += units
    
    def get_remaining_quota(self) -> int:
        """
        Kalan günlük kota miktarını döner.
        
        Returns:
            Kalan unit sayısı
        """
        return self._daily_quota_limit - self._daily_quota_used
    
    def reset_quota(self) -> None:
        """Günlük kota sayacını sıfırlar. Gece yarısı çağrılır."""
        self._daily_quota_used = 0


def get_youtube_client() -> YouTubeClient:
    """Singleton YouTube client döner."""
    return YouTubeClient()


=== DOSYA 6: backend/app/services/video_downloader.py ===

import os
from typing import Optional


class VideoDownloader:
    """
    yt-dlp wrapper. YouTube videolarını indirir.
    Content Finder -> Clip Extractor entegrasyonu için kullanılır.
    """
    
    def __init__(self):
        self.output_dir = os.getenv("UPLOAD_DIR", "uploads")
    
    async def download(
        self,
        youtube_url: str,
        output_dir: Optional[str] = None,
        max_quality: str = "1080"
    ) -> str:
        """
        YouTube videosunu indirir.
        
        Args:
            youtube_url: YouTube video URL'si
            output_dir: İndirme dizini (varsayılan: self.output_dir)
            max_quality: Maksimum video kalitesi ("720" | "1080" | "1440" | "2160")
        
        Returns:
            İndirilen dosyanın tam yolu (str)
        
        Raises:
            RuntimeError: yt-dlp başarısız olursa
            FileNotFoundError: İndirilen dosya bulunamazsa
        """
        raise NotImplementedError("TODO")
    
    async def get_info(self, youtube_url: str) -> dict:
        """
        Video bilgilerini alır, indirmez.
        yt-dlp --dump-json kullanır.
        
        Args:
            youtube_url: YouTube video URL'si
        
        Returns:
            Video metadata dict (title, duration, formats, vs.)
        """
        raise NotImplementedError("TODO")


=== DOSYA 7: backend/app/content_finder/prompts/query_generation.py ===

def build_query_generation_prompt(
    channel_context: str,
    recent_successes: str,
    weak_queries: str,
    trending_topics: str,
    query_count: int
) -> str:
    """
    F01 Query Generation için Gemini prompt'unu oluşturur.
    
    Args:
        channel_context: Channel DNA'dan oluşturulan bağlam metni
        recent_successes: Son başarılı kaynakların listesi
        weak_queries: Geçmişte zayıf sonuç veren sorgular
        trending_topics: Güncel trendler (varsa)
        query_count: Üretilecek sorgu sayısı
    
    Returns:
        Gemini'ye gönderilecek prompt string
    """
    raise NotImplementedError("TODO")


=== DOSYA 8: backend/app/content_finder/prompts/deep_analysis.py ===

def build_deep_analysis_prompt(
    channel_context: str,
    video_title: str,
    video_channel: str,
    video_duration_minutes: float,
    video_view_count: int,
    video_published_at: str,
    video_description: str,
    sampled_transcript: str
) -> str:
    """
    F05 Deep Analysis için Gemini prompt'unu oluşturur.
    
    Args:
        channel_context: Channel DNA bağlam metni
        video_title: Video başlığı
        video_channel: Kaynak kanal adı
        video_duration_minutes: Video süresi (dakika)
        video_view_count: Görüntülenme sayısı
        video_published_at: Yayın tarihi
        video_description: Video açıklaması (ilk 500 karakter)
        sampled_transcript: Örneklenmiş transkript
    
    Returns:
        Gemini'ye gönderilecek prompt string
    """
    raise NotImplementedError("TODO")


=== DOSYA 9: backend/app/content_finder/prompts/metadata_analysis.py ===

def build_metadata_analysis_prompt(
    channel_context: str,
    video_title: str,
    video_channel: str,
    video_duration_minutes: float,
    video_view_count: int,
    video_published_at: str,
    video_description: str,
    top_comments: str
) -> str:
    """
    Transkript olmadığında metadata + yorumlardan analiz için Gemini prompt'u.
    
    Args:
        channel_context: Channel DNA bağlam metni
        video_title: Video başlığı
        video_channel: Kaynak kanal adı
        video_duration_minutes: Video süresi (dakika)
        video_view_count: Görüntülenme sayısı
        video_published_at: Yayın tarihi
        video_description: Video açıklaması
        top_comments: En iyi yorumlar (metin olarak)
    
    Returns:
        Gemini'ye gönderilecek prompt string
    """
    raise NotImplementedError("TODO")


Tüm dosyaları oluştur. Bitince bana oluşturduğun dosya isimlerini ve her dosyadaki fonksiyon/class isimlerini listele.
```

Claude Code bitirince bana söyle, doğrulayıp ADIM 1C'ye geçeceğiz (fazlar ve stratejiler).

BEN DİYORUM : şimdi yaptı fakat yeni adıma geçmeden kısaca sorayım, yt-dlp gelecekse ilerki bölümlerde altyazı ve ya herhangi diğer işlemler için yt-dlp veya uygun yapı kullanmamız gerekirmi? çünkü çoklu kanal sisteminde eğer her şeyi youtube api yaparsa kanallara kota yetmez sorgular tabii ki youtbe api ile olucak. diğer soru tüm kodları sen mi yazıcaksın yoksa claude code opus 4.6 mı yazsın ? çünkü sanki tüm kodları sen yazıyorsun

OPUS DİYOR : 

Çok iyi sorular, ikisine de cevap vereyim:

## Soru 1: yt-dlp ve YouTube API Kota Meselesi

Haklısın. YouTube Captions API çok pahalı (200 unit/indirme). 15 video × 200 = 3,000 unit sadece transkript için gider.

**Çözüm:** `youtube-transcript-api` Python kütüphanesi kullanacağız. Bu kütüphane:
- YouTube API kotası **harcamaz** (resmi API değil, scraping)
- Ücretsiz, limitsiz
- Auto-captions ve manual captions alabilir
- yt-dlp'den daha hafif (sadece transkript için)

Yani kota tablosu şöyle olacak:

```
YouTube Data API (kotalı):
  - search.list → 100 unit (arama için şart, alternatif yok)
  - videos.list → 1 unit (video detayları için şart)

youtube-transcript-api (kotasız):
  - Transkript indirme → 0 unit ✓

yt-dlp (kotasız):
  - Video indirme → 0 unit (clipper'a gönderirken)
  - Video bilgi alma → 0 unit
```

**Güncellenecek:** `transcript_fetcher.py`'de YouTube Captions API yerine `youtube-transcript-api` kullanacağız. Bu değişikliği iskelet yapıya şimdi yansıtacağız.

---

## Soru 2: Kodu Kim Yazıyor?

Şu an **iskelet fazındayız** — bu fazda ben yapıyı veriyorum çünkü:
- Fonksiyon isimleri, parametreler, tipler = **mimari karar**, bunları benim belirlemem lazım
- İskelet tutarlı olmazsa sonra her şey dağılır
- İskelet = bina planı, bunu mimar çizer

**Ama implementasyon fazında (ADIM 2'den sonra)** ben kod yazmayacağım. Şöyle olacak:

```
Ben:    "calc_topic_match fonksiyonunu implement et. Mantığı şu: 
        do_list eşleşmesi +1, dont_list -1.5, no_go_zones 0 yap..."

Claude: [kodu kendi yazar]

Ben:    "Doğrula: return tipi float mı? edge case'ler var mı?"
```

Yani iskelet bittikten sonra ben sadece **ne yapılacağını** anlatacağım, Claude Code **nasıl yapılacağını** kendi yazacak. Şu anki detaylı kod yazma sadece iskelet fazı için.

---

## Devam: ADIM 1B-fix

Önce transcript_fetcher.py'yi düzeltelim. Claude Code'a ver:

```
backend/app/content_finder/utils/transcript_fetcher.py dosyasını güncelle.

YouTube Captions API yerine youtube-transcript-api kütüphanesini kullanacağız. Bu kütüphane YouTube API kotası harcamaz, ücretsiz çalışır.

Dosyayı şu şekilde değiştir:

from typing import Optional


async def fetch_youtube_captions(video_id: str) -> Optional[str]:
    """
    YouTube video'sunun transkriptini alır.
    youtube-transcript-api kütüphanesini kullanır (YouTube API kotası HARCAMAZ).
    
    Öncelik sırası:
    1. Manuel İngilizce altyazı (daha doğru)
    2. Otomatik oluşturulan İngilizce altyazı
    3. None (altyazı yoksa)
    
    Kütüphane: youtube-transcript-api (pip install youtube-transcript-api)
    
    Args:
        video_id: YouTube video ID'si (URL değil, sadece ID)
    
    Returns:
        Düz metin transkript (timestamp'siz, sadece metin) veya None
        
    Note:
        Bu fonksiyon YouTube Data API kullanmaz, kota harcamaz.
        Bazı videolarda altyazı devre dışı olabilir, bu durumda None döner.
    """
    raise NotImplementedError("TODO")


async def fetch_youtube_captions_with_timestamps(video_id: str) -> Optional[list[dict]]:
    """
    YouTube video'sunun transkriptini timestamp'lerle birlikte alır.
    
    Args:
        video_id: YouTube video ID'si
    
    Returns:
        [{"text": "hello", "start": 0.0, "duration": 2.5}, ...] veya None
        
    Note:
        Deep analysis'te approximate location tespiti için kullanılabilir.
    """
    raise NotImplementedError("TODO")

Ayrıca requirements.txt veya backend'deki bağımlılık dosyasına youtube-transcript-api ekle. Eğer requirements.txt varsa oraya "youtube-transcript-api" satırını ekle. Yoksa bana söyle.

Bitince bana ne yaptığını göster.
```

Bunu yaptıktan sonra bana söyle, ADIM 1C'ye geçeceğiz (fazlar ve stratejiler iskeletleri).