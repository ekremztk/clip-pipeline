"""
Deal Hunter — Kleinanzeigen'den iPhone 14/14 Pro fırsatları otomatik bulur ve analiz eder.

Flow:
  1. Kleinanzeigen'den ilan listesi çek (fiyat filtreli)
  2. PLZ mesafe filtresi (50km) ile uzak ilanları at
  3. Daha önce görülmüş ilanları atla (external_id check)
  4. Her yeni ilan için detay sayfası çek (açıklama, fotoğraflar, satıcı bilgisi)
  5. ÖNCE eBay satış verisini çek → AI'a gerçek piyasa fiyatlarıyla birlikte gönder
  6. Gemini Flash ile analiz (eBay datası + ilan bilgisi)
  7. marketplace_deals tablosuna kaydet
"""

import re
import json
import random
import asyncio
from math import radians, sin, cos, sqrt, atan2
from typing import Optional

import httpx
from app.config import settings
from app.services.supabase_client import get_client
from .adapters.kleinanzeigen_httpx import (
    KleinanzeigenHTTPXAdapter,
    HEADER_SETS,
    _parse_price,
)
from .models import SearchConfig

DEAL_SEARCHES = [
    {"query": "iPhone 14", "min_price": 150, "max_price": 300},
    {"query": "iPhone 14 Pro", "min_price": 200, "max_price": 350},
]

LOCATION_PLZ = "79336"
LOCATION_RADIUS_KM = 50
HERBOLZHEIM_LAT = 48.2195
HERBOLZHEIM_LON = 7.7747

# Known PLZ → (lat, lon) for 2-digit prefix regions near Freiburg
# Used for fast pre-filtering before haversine check
NEARBY_PLZ_PREFIXES = {"77", "78", "79", "76", "68"}

USER_ID = "3ebacaef-8982-4e34-a13a-4b50cdf0cc40"

ANALYSIS_PROMPT = """Sen Kleinanzeigen'den (Almanya) ikinci el iPhone fırsatları bulan uzman bir AI analistsin.
Tüm analizlerini TÜRKÇE yaz.

İLAN BİLGİLERİ:
- Başlık: {title}
- Fiyat: {price}€
- Açıklama: {description}
- Konum: {location}
- Satıcı: {seller_name}
- Üyelik: {seller_since}
- Fotoğraf sayısı: {num_photos}

GERÇEK PİYASA VERİSİ (eBay.de'de SATILMIŞ ürünler — bu verilere GÜVENİLİR):
{ebay_data}

ÖNEMLİ: Fiyat değerlendirmesi yaparken SADECE yukarıdaki eBay satış verisini kullan.
Kafandan fiyat uydurmak YASAK. eBay verisi yoksa "veri yetersiz" de.

GÖREV: Bu ilanı detaylıca analiz et. Her sinyali değerlendir.

SADECE geçerli JSON döndür, bu yapıda:
{{
  "model": "iPhone 14" veya "iPhone 14 Pro" veya "iPhone 14 Pro Max",
  "storage": "128GB" veya "256GB" veya "512GB" veya null,
  "color": "renk adı veya null",
  "battery_pct": sayı veya null,
  "tier": "S+" veya "S-" veya "B" veya "C" veya "D" veya "E",
  "tier_reason": "kısa açıklama (Türkçe)",
  "condition_notes": "fiziksel durum özeti (Türkçe)",
  "description_tr": "ilan açıklamasının Türkçe çevirisi (özet değil, tam çeviri)",
  "has_box": true/false/null,
  "has_charger": true/false/null,
  "has_receipt": true/false/null,
  "flags": ["flag1", "flag2"],
  "seller_analysis": {{
    "effort_level": "düşük" veya "orta" veya "yüksek",
    "urgency": "yok" veya "düşük" veya "orta" veya "yüksek",
    "trust_score": 1-10,
    "reasoning": "Türkçe: Bu fiyat neden bu seviyede? Satıcı hakkında ne sinyaller var?"
  }},
  "price_assessment": {{
    "is_underpriced": true/false,
    "why_cheap": "Türkçe: Neden ucuza satıyor?",
    "risk_factors": ["risk1 (Türkçe)", "risk2 (Türkçe)"],
    "negotiation_tip": "Türkçe: Pazarlık tavsiyesi — ne kadar indirim istenebilir, nasıl yaklaşılmalı"
  }},
  "verdict": "Türkçe: 2-3 cümle net karar — bu alınır mı alınmaz mı, neden? eBay verisine göre kar mı zarar mı?",
  "suggested_offer": sayı veya null,
  "confidence": 0.0-1.0,
  "reject": false,
  "reject_reason": null
}}

REJECT KURALLARI — şunları REDDET (reject: true):
- iPhone 14 Plus (sadece iPhone 14 ve iPhone 14 Pro arıyoruz)
- Aksesuar, kılıf, tamir ilanı, yanlış model
- Parça satışı (defolu, ekranı kırık satış amaçlı değilse)
- "SUCHE" / "Kaufe" ilanları (alım ilanı, satış değil)
- Takas ilanları (sadece takas, satış fiyatı yok)

TIER KURALLARI (eBay tier sistemiyle aynı):
- S+: Mükemmel durumda, kutulu, faturalı, batarya %90+, çizik yok
- S-: İyi durumda ama küçük eksikler (kutu yok, hafif kullanım izi)
- B: Orta durumda, batarya %85+, görünür kullanım izleri ama sorunsuz
- C: Çalışıyor ama belirgin yıpranma, batarya %80+
- D: Hasarlı veya batarya %80 altı, hala fonksiyonel
- E: iCloud kilitli, ekran kırık, su hasarı, dolandırıcılık, parça

SATICI PSİKOLOJİ SİNYALLERİ:
- Düşük emek (kısa/yok açıklama, az kötü fotoğraf) = piyasa bilmiyor = FIRSAT
- Aciliyet sinyalleri (ASAP, schnell, dringend, heute noch) = düşük fiyat kabul eder
- Sadece Abholung = lokal satıcı, pazarlığa daha açık
- Çok yeni hesap + çok iyi fiyat = potansiyel dolandırıcılık
- Eski üye + çok satış = güvenilir ama fiyat bilir

PAZARLIK TAVSİYESİ:
- suggested_offer: eBay verisine göre gerçekçi bir teklif rakamı ver
- Düşük emekli satıcıya %15-25 indirim dene
- Acil satışa %10-20 indirim dene
- Yüksek emekli + uzun süredir aktif = max %5-10

FLAGS: no_box, no_charger, with_box, with_receipt, low_battery, screen_scratches,
cracked_back, cracked_screen, dent_or_bend, water_damage, face_id_broken,
icloud_locked, possible_scam, like_new, heavy_use, insufficient_info"""


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


# German PLZ center coordinates (first 2 digits → approx center)
PLZ_COORDS: dict[str, tuple[float, float]] = {
    "01": (51.05, 13.74), "02": (51.15, 14.97), "03": (51.75, 12.24), "04": (51.34, 12.38),
    "06": (51.48, 11.97), "07": (50.93, 11.59), "08": (50.72, 12.49), "09": (50.83, 12.92),
    "10": (52.52, 13.41), "12": (52.48, 13.43), "13": (52.57, 13.38), "14": (52.39, 13.07),
    "15": (52.34, 14.04), "16": (52.76, 13.29), "17": (53.63, 11.41), "18": (54.09, 12.14),
    "19": (53.63, 11.41), "20": (53.55, 9.99), "21": (53.47, 9.77), "22": (53.57, 10.02),
    "23": (53.87, 10.69), "24": (54.32, 10.14), "25": (53.87, 9.48), "26": (53.14, 8.22),
    "27": (53.08, 8.80), "28": (53.08, 8.80), "29": (52.97, 10.57), "30": (52.37, 9.74),
    "31": (52.15, 9.95), "32": (52.02, 8.53), "33": (51.93, 8.53), "34": (51.32, 9.50),
    "35": (50.58, 8.67), "36": (50.67, 9.94), "37": (51.53, 9.94), "38": (52.27, 10.52),
    "39": (52.13, 11.63), "40": (51.23, 6.78), "41": (51.19, 6.44), "42": (51.26, 7.15),
    "44": (51.51, 7.47), "45": (51.45, 7.01), "46": (51.66, 6.63), "47": (51.43, 6.76),
    "48": (51.96, 7.63), "49": (52.28, 8.05), "50": (50.94, 6.96), "51": (50.93, 7.10),
    "52": (50.78, 6.08), "53": (50.73, 7.10), "54": (49.75, 6.64), "55": (49.99, 8.27),
    "56": (50.36, 7.60), "57": (50.87, 8.02), "58": (51.37, 7.46), "59": (51.67, 7.82),
    "60": (50.11, 8.68), "61": (50.22, 8.62), "63": (50.00, 8.98), "64": (49.87, 8.65),
    "65": (50.08, 8.24), "66": (49.24, 7.00), "67": (49.44, 8.44), "68": (49.49, 8.47),
    "69": (49.41, 8.69), "70": (48.78, 9.18), "71": (48.69, 9.13), "72": (48.52, 9.06),
    "73": (48.81, 9.48), "74": (49.14, 9.22), "75": (48.89, 8.70), "76": (49.01, 8.40),
    "77": (48.47, 7.94), "78": (47.83, 8.83), "79": (47.99, 7.85), "80": (48.14, 11.58),
    "81": (48.11, 11.60), "82": (48.08, 11.49), "83": (47.85, 12.13), "84": (48.46, 12.18),
    "85": (48.35, 11.79), "86": (48.37, 10.90), "87": (47.73, 10.32), "88": (47.72, 9.59),
    "89": (48.40, 9.99), "90": (49.45, 11.08), "91": (49.47, 10.99), "92": (49.23, 12.10),
    "93": (49.02, 12.10), "94": (48.57, 13.43), "95": (50.09, 11.97), "96": (50.09, 11.05),
    "97": (49.79, 9.94), "98": (50.68, 10.93), "99": (50.98, 11.03),
}


def _is_within_radius(location_text: str, max_km: float = 50.0) -> bool:
    """Check if a listing location is within max_km of Herbolzheim."""
    if not location_text:
        return False
    plz_match = re.search(r'\b(\d{5})\b', location_text)
    if not plz_match:
        return False
    plz = plz_match.group(1)
    prefix = plz[:2]
    coords = PLZ_COORDS.get(prefix)
    if not coords:
        return False
    dist = _haversine(HERBOLZHEIM_LAT, HERBOLZHEIM_LON, coords[0], coords[1])
    return dist <= max_km


def get_ebay_price_context(model_keyword: str) -> str:
    """Fetch eBay sold data from DB and format as text for AI prompt."""
    supabase = get_client()
    try:
        query = supabase.table("marketplace_price_data").select("model, storage, tier, sold_price")
        query = query.eq("brand", "Apple")

        if "Pro" in model_keyword:
            query = query.ilike("model", "%14 Pro%")
            query = query.not_.ilike("model", "%Pro Max%")
        else:
            query = query.ilike("model", "%14%")
            query = query.not_.ilike("model", "%Pro%")
            query = query.not_.ilike("model", "%Plus%")

        query = query.order("sold_date", desc=True).limit(80)
        result = query.execute()
        data = result.data if result.data else []

        if not data:
            return "eBay satış verisi bulunamadı."

        # Group by storage + tier
        groups: dict[str, list[float]] = {}
        for row in data:
            key = f"{row.get('storage', '?')} / Tier {row.get('tier', '?')}"
            groups.setdefault(key, []).append(float(row["sold_price"]))

        lines = []
        for key, prices in sorted(groups.items()):
            prices.sort()
            n = len(prices)
            avg = sum(prices) / n
            min_p = prices[0]
            max_p = prices[-1]
            lines.append(f"  {key}: {n} satış, min {min_p:.0f}€, ort {avg:.0f}€, max {max_p:.0f}€")

        return "\n".join(lines)
    except Exception as e:
        print(f"[DealHunter] eBay context fetch error: {e}")
        return "eBay verisi çekilemedi."


async def fetch_listing_detail(url: str, client: httpx.AsyncClient, headers: dict) -> Optional[dict]:
    """Fetch full listing detail page from Kleinanzeigen."""
    try:
        r = await client.get(url, headers=headers)
        if r.status_code != 200:
            print(f"[DealHunter] Detail page HTTP {r.status_code}: {url}")
            return None

        html = r.text

        description = ""
        desc_match = re.search(
            r'id="viewad-description-text"[^>]*>(.*?)</p>',
            html, re.DOTALL
        )
        if desc_match:
            description = re.sub(r'<[^>]+>', ' ', desc_match.group(1)).strip()
            description = re.sub(r'\s+', ' ', description)

        images = []
        seen = set()

        gallery_match = re.search(
            r'id="viewad-image".*?(?=id="viewad-(?!image)|class="similarads|id="vap-belen|$)',
            html, re.DOTALL
        )
        gallery_html = gallery_match.group(0) if gallery_match else ""

        if gallery_html:
            img_matches = re.findall(
                r'(https://img\.kleinanzeigen\.de/api/v1/prod-ads/images/[^"\'>\s]+)',
                gallery_html
            )
            for img_url in img_matches:
                clean = img_url.split("?")[0]
                if clean not in seen:
                    seen.add(clean)
                    images.append(clean + "?rule=$_57.JPG")

        if not images:
            img_matches = re.findall(
                r'data-imgsrc="(https://img\.kleinanzeigen\.de/api/v1/prod-ads/images/[^"]+)"',
                html
            )
            for img_url in img_matches:
                clean = img_url.split("?")[0]
                if clean not in seen:
                    seen.add(clean)
                    images.append(clean + "?rule=$_57.JPG")

        if len(images) > 1:
            ad_id_match = re.search(r'/prod-ads/images/([^/]+)/', images[0])
            if ad_id_match:
                ad_id = ad_id_match.group(1)
                images = [img for img in images if ad_id in img]

        seller_name = ""
        seller_match = re.search(
            r'userprofile-vip[^>]*>.*?<span[^>]*>(.*?)</span>',
            html, re.DOTALL
        )
        if seller_match:
            seller_name = re.sub(r'<[^>]+>', '', seller_match.group(1)).strip()
        if not seller_name:
            seller_match2 = re.search(r'"sellerName"\s*:\s*"([^"]+)"', html)
            if seller_match2:
                seller_name = seller_match2.group(1)

        seller_since = ""
        since_match = re.search(r'Aktiv seit\s*([\d.]+)', html)
        if since_match:
            seller_since = since_match.group(1)

        return {
            "description": description[:2000],
            "images": images[:10],
            "seller_name": seller_name,
            "seller_since": seller_since,
        }
    except Exception as e:
        print(f"[DealHunter] Error fetching detail: {e}")
        return None


async def analyze_listing(
    title: str,
    price: float,
    description: str,
    location: str,
    seller_name: str,
    seller_since: str,
    images: list[str],
    ebay_context: str,
) -> Optional[dict]:
    """Run Gemini Flash analysis on a single listing with real eBay price data."""
    from app.services.gemini_client import get_gemini_client

    client = get_gemini_client()

    prompt = ANALYSIS_PROMPT.format(
        title=title,
        price=price,
        description=description or "(açıklama yok)",
        location=location or "bilinmiyor",
        seller_name=seller_name or "bilinmiyor",
        seller_since=seller_since or "bilinmiyor",
        num_photos=len(images),
        ebay_data=ebay_context,
    )

    if images:
        prompt += f"\n\nFOTOĞRAF SAYISI: {len(images)} adet (kalite/emek değerlendirmesi için)\n"

    try:
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL_FLASH,
            contents=prompt,
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)

        return json.loads(text)
    except Exception as e:
        print(f"[DealHunter] AI analysis error: {e}")
        return None


def estimate_sell_prices(model_parsed: str, storage: Optional[str], tier: str) -> dict:
    """Query marketplace_price_data for sell price estimates with distribution bands."""
    supabase = get_client()

    # Map our tiers to DB tiers (DB uses S+, S-, B, C, D, E)
    adjacent_tiers = {
        "S+": ["S+", "S-"],
        "S-": ["S-", "S+", "B"],
        "B": ["B", "S-", "C"],
        "C": ["C", "B", "D"],
        "D": ["D", "C", "E"],
        "E": ["E", "D"],
    }
    tiers_to_check = adjacent_tiers.get(tier, [tier, "S-", "S+"])

    try:
        query = supabase.table("marketplace_price_data").select("sold_price, tier, sold_date")
        query = query.eq("brand", "Apple")

        if "Pro Max" in model_parsed:
            query = query.ilike("model", "%14 Pro Max%")
        elif "Pro" in model_parsed:
            query = query.ilike("model", "%14 Pro%")
            query = query.not_.ilike("model", "%Pro Max%")
        else:
            query = query.ilike("model", "%14%")
            query = query.not_.ilike("model", "%Pro%")
            query = query.not_.ilike("model", "%Plus%")

        if storage:
            query = query.eq("storage", storage)

        query = query.in_("tier", tiers_to_check)
        query = query.order("sold_date", desc=True)
        query = query.limit(50)

        result = query.execute()
        data = result.data if result.data else []

        if len(data) < 3:
            # Fallback: try without storage filter
            query2 = supabase.table("marketplace_price_data").select("sold_price, tier, sold_date")
            query2 = query2.eq("brand", "Apple")
            if "Pro Max" in model_parsed:
                query2 = query2.ilike("model", "%14 Pro Max%")
            elif "Pro" in model_parsed:
                query2 = query2.ilike("model", "%14 Pro%")
                query2 = query2.not_.ilike("model", "%Pro Max%")
            else:
                query2 = query2.ilike("model", "%14%")
                query2 = query2.not_.ilike("model", "%Pro%")
                query2 = query2.not_.ilike("model", "%Plus%")
            query2 = query2.in_("tier", tiers_to_check)
            query2 = query2.order("sold_date", desc=True).limit(50)
            result2 = query2.execute()
            data = result2.data if result2.data else []

        if len(data) < 3:
            return {
                "min_sell": None, "realistic_sell": None, "max_sell": None,
                "sample_size": len(data), "bands": None,
            }

        prices = sorted([float(d["sold_price"]) for d in data])
        n = len(prices)

        p10 = round(prices[int(n * 0.10)], 0)
        p25 = round(prices[int(n * 0.25)], 0)
        p50 = round(prices[n // 2], 0)
        p75 = round(prices[int(n * 0.75)], 0)
        p90 = round(prices[int(n * 0.90)], 0)

        band_low = sum(1 for p in prices if p <= p25) / n * 100
        band_mid = sum(1 for p in prices if p25 < p <= p75) / n * 100
        band_high = sum(1 for p in prices if p > p75) / n * 100

        return {
            "min_sell": p10,
            "realistic_sell": p50,
            "max_sell": p90,
            "sample_size": n,
            "bands": {
                "low_range": f"{p10:.0f}-{p25:.0f}€",
                "low_pct": round(band_low),
                "mid_range": f"{p25:.0f}-{p75:.0f}€",
                "mid_pct": round(band_mid),
                "high_range": f"{p75:.0f}-{p90:.0f}€",
                "high_pct": round(band_high),
                "p25": p25,
                "p50": p50,
                "p75": p75,
            },
        }
    except Exception as e:
        print(f"[DealHunter] Price estimation error: {e}")
        return {"min_sell": None, "realistic_sell": None, "max_sell": None, "sample_size": 0, "bands": None}


async def run_deal_hunter():
    """Main deal hunter loop — scrape Klein, filter by distance, analyze with eBay data, save."""
    supabase = get_client()
    adapter = KleinanzeigenHTTPXAdapter()
    headers = random.choice(HEADER_SETS).copy()
    total_new = 0

    for search_cfg in DEAL_SEARCHES:
        config = SearchConfig(
            id="deal-hunter",
            user_id=USER_ID,
            platform="kleinanzeigen",
            query=search_cfg["query"],
            min_price=search_cfg["min_price"],
            max_price=search_cfg["max_price"],
            location=LOCATION_PLZ,
            radius_km=LOCATION_RADIUS_KM,
        )

        print(f"[DealHunter] Searching: {search_cfg['query']} ({search_cfg['min_price']}-{search_cfg['max_price']}€)")
        listings = await adapter.search(config)

        if not listings:
            print(f"[DealHunter] No listings found for '{search_cfg['query']}'")
            continue

        # Distance filter — Klein doesn't filter server-side
        nearby_listings = [l for l in listings if _is_within_radius(l.location or "", LOCATION_RADIUS_KM)]
        print(f"[DealHunter] Found {len(listings)} total, {len(nearby_listings)} within {LOCATION_RADIUS_KM}km of Herbolzheim")

        if not nearby_listings:
            continue

        existing_res = supabase.table("marketplace_listings").select("external_id").eq(
            "platform", "kleinanzeigen"
        ).execute()
        existing_ids = {r["external_id"] for r in (existing_res.data or [])}

        new_listings = [l for l in nearby_listings if l.external_id not in existing_ids]
        print(f"[DealHunter] {len(new_listings)} new listings (skipping {len(nearby_listings) - len(new_listings)} seen)")

        if not new_listings:
            continue

        # Pre-fetch eBay context once per search query (not per listing)
        ebay_context = get_ebay_price_context(search_cfg["query"])

        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
            for listing in new_listings:
                await asyncio.sleep(random.uniform(2.0, 4.0))

                detail = await fetch_listing_detail(listing.url, client, headers)
                if not detail:
                    continue

                analysis = await analyze_listing(
                    title=listing.title,
                    price=listing.price or 0,
                    description=detail["description"],
                    location=listing.location or "",
                    seller_name=detail["seller_name"],
                    seller_since=detail["seller_since"],
                    images=detail["images"],
                    ebay_context=ebay_context,
                )

                if not analysis:
                    continue

                if analysis.get("reject"):
                    print(f"[DealHunter] REJECT: {listing.title} — {analysis.get('reject_reason', '?')}")
                    continue

                model_parsed = analysis.get("model", "iPhone 14")
                storage_parsed = analysis.get("storage")
                tier = analysis.get("tier", "S-")

                sell_estimate = estimate_sell_prices(model_parsed, storage_parsed, tier)

                realistic_sell = sell_estimate.get("realistic_sell")
                profit = (realistic_sell - listing.price) if realistic_sell and listing.price else None
                score = min(100, max(0, (profit / listing.price) * 100)) if profit and listing.price else 0

                try:
                    supabase.table("marketplace_listings").upsert({
                        "platform": "kleinanzeigen",
                        "external_id": listing.external_id,
                        "search_id": None,
                        "title": listing.title,
                        "price": listing.price,
                        "location": listing.location,
                        "url": listing.url,
                        "thumbnail_url": listing.thumbnail_url,
                        "seller_name": detail["seller_name"],
                        "posted_at": listing.posted_at.isoformat() if listing.posted_at else None,
                    }, on_conflict="platform,external_id").execute()

                    listing_res = supabase.table("marketplace_listings").select("id").eq(
                        "platform", "kleinanzeigen"
                    ).eq("external_id", listing.external_id).execute()
                    listing_db_id = listing_res.data[0]["id"] if listing_res.data else None

                    supabase.table("marketplace_deals").insert({
                        "listing_id": listing_db_id,
                        "user_id": USER_ID,
                        "score": round(score, 1),
                        "estimated_profit": round(profit, 2) if profit else None,
                        "status": "new",
                        "buy_price": listing.price,
                        "sell_price": realistic_sell,
                        "ai_analysis": {
                            "condition_notes": analysis.get("condition_notes", ""),
                            "description_tr": analysis.get("description_tr", ""),
                            "verdict": analysis.get("verdict", ""),
                            "suggested_offer": analysis.get("suggested_offer"),
                            "has_box": analysis.get("has_box"),
                            "has_charger": analysis.get("has_charger"),
                            "has_receipt": analysis.get("has_receipt"),
                            "flags": analysis.get("flags", []),
                            "price_assessment": analysis.get("price_assessment", {}),
                            "price_bands": sell_estimate.get("bands"),
                        },
                        "seller_analysis": analysis.get("seller_analysis", {}),
                        "estimated_min_sell": sell_estimate.get("min_sell"),
                        "estimated_realistic_sell": sell_estimate.get("realistic_sell"),
                        "estimated_max_sell": sell_estimate.get("max_sell"),
                        "tier": tier,
                        "model_parsed": model_parsed,
                        "storage_parsed": storage_parsed,
                        "battery_pct": analysis.get("battery_pct"),
                        "images": detail["images"],
                        "description": detail["description"],
                        "confidence": analysis.get("confidence", 0.5),
                        "klein_url": listing.url,
                        "seller_name": detail["seller_name"],
                        "listing_location": listing.location,
                    }).execute()

                    total_new += 1
                    profit_str = f"+{profit:.0f}€" if profit else "?"
                    print(f"[DealHunter] SAVED: {listing.title} | {listing.price}€ | Tier {tier} | {profit_str}")

                except Exception as e:
                    print(f"[DealHunter] DB save error: {e}")

                await asyncio.sleep(random.uniform(1.0, 2.0))

        await asyncio.sleep(random.uniform(3.0, 6.0))

    print(f"[DealHunter] Done — {total_new} new deals saved")
    return total_new
