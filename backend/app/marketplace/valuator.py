"""
Market Valuator — Ürünlerin gerçek piyasa değerini belirler.

Kaynaklar:
1. Geizhals.de → Yeni fiyat tavanı (en düşük mağaza fiyatı)
2. Kleinanzeigen aktif ilanlar → 2. el piyasa dağılımı
3. Gemini Flash → Kondisyon analizi (başlık + açıklama parse)

Çıktı: marketplace_products tablosuna condition_mint/good/fair fiyatları yazar.
"""

import re
import random
import asyncio
from typing import Optional
import httpx
from app.config import settings

HEADERS_LIST = [
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
    },
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.7",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
    },
]


async def get_geizhals_new_price(product_query: str) -> Optional[float]:
    """Geizhals.de'den yeni ürün en düşük fiyatını çek."""
    url = f"https://geizhals.de/?fs={product_query.replace(' ', '+')}&hloc=at&hloc=de&in="
    headers = random.choice(HEADERS_LIST)

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            r = await client.get(url, headers=headers)
            if r.status_code != 200:
                print(f"[Valuator] Geizhals HTTP {r.status_code}")
                return None

            prices = re.findall(r'€\s*(\d{3,4}),(\d{2})', r.text)
            if not prices:
                prices = re.findall(r'(\d{3,4}),(\d{2})\s*€', r.text)
            if not prices:
                return None

            float_prices = [float(f"{p[0]}.{p[1]}") for p in prices]
            float_prices.sort()
            return float_prices[0]
    except Exception as e:
        print(f"[Valuator] Geizhals error: {e}")
        return None


async def get_kleinanzeigen_prices(product_query: str, location: str = "") -> list[dict]:
    """Kleinanzeigen'den aktif ilan fiyatlarını çek."""
    params = [f"keywords={product_query.replace(' ', '+')}", "sortingField=SORTING_DATE", "adType=OFFER"]
    if location:
        params.append(f"locationStr={location}")
    url = f"https://www.kleinanzeigen.de/s-suchanfrage.html?{'&'.join(params)}"
    headers = random.choice(HEADERS_LIST)

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            r = await client.get(url, headers=headers)
            if r.status_code != 200:
                return []

            articles = re.findall(r'<article[^>]*data-adid="(\d+)"[^>]*>(.*?)</article>', r.text, re.DOTALL)
            results = []

            for ad_id, content in articles:
                title_match = re.search(r'<a\s+class="ellipsis"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', content, re.DOTALL)
                if not title_match:
                    continue
                title = re.sub(r'<[^>]+>', '', title_match.group(2)).strip()

                price_match = re.search(r'aditem-main--middle--price-shipping--price[^>]*>(.*?)</p>', content, re.DOTALL)
                if not price_match:
                    price_match = re.search(r'aditem-main--middle--price[^>]*>(.*?)</p>', content, re.DOTALL)
                price_text = re.sub(r'<[^>]+>', '', price_match.group(1)).strip() if price_match else ""

                is_vb = "VB" in price_text
                price_clean = price_text.replace("VB", "").replace("€", "").replace(".", "").replace(",", ".").strip()
                price_num = re.search(r"[\d.]+", price_clean)
                price = float(price_num.group()) if price_num else None

                if price and price > 30:
                    results.append({
                        "title": title,
                        "price": price,
                        "is_vb": is_vb,
                        "ad_id": ad_id,
                    })

            return results
    except Exception as e:
        print(f"[Valuator] Kleinanzeigen error: {e}")
        return []


def iqr_filter(prices: list[float]) -> list[float]:
    """IQR ile outlier'ları filtrele (dolandırıcı / abartılı fiyatları çıkar)."""
    if len(prices) < 4:
        return prices

    sorted_prices = sorted(prices)
    n = len(sorted_prices)
    q1 = sorted_prices[n // 4]
    q3 = sorted_prices[3 * n // 4]
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    return [p for p in sorted_prices if lower <= p <= upper]


async def analyze_with_gemini(product_name: str, listings: list[dict], new_price: Optional[float]) -> dict:
    """Gemini Flash ile ilan başlıklarını analiz et, kondisyon bazlı fiyat belirle."""
    from google import genai

    client = genai.Client(
        vertexai=True,
        project=settings.GCP_PROJECT,
        location=settings.GCP_LOCATION,
    )

    listings_text = "\n".join([
        f"- {l['title']} → {l['price']}€ {'(VB)' if l['is_vb'] else ''}"
        for l in listings[:30]
    ])

    prompt = f"""Sen bir 2. el elektronik ürün piyasa analistisin. Almanya pazarı.

Ürün: {product_name}
Yeni fiyat (Geizhals): {f'{new_price}€' if new_price else 'bilinmiyor'}

Aşağıdaki Kleinanzeigen ilanlarını analiz et. Her ilanın başlığından ürün durumunu anla:
- Tier A (Kusursuz/Kutulu): "wie neu", "OVP", "mit Rechnung", "keine Kratzer", "neuwertig"
- Tier B (İyi/Kutusuz): Sadece cihaz, aksesuar eksik, kullanılmış ama sorunsuz
- Tier C (Çizikli/Hasarlı): "Gebrauchsspuren", "leichte Kratzer", "Display Kratzer"
- Tier D (Kusurlu/Şüpheli): Aşırı ucuz, "defekt", "iCloud", "gesperrt", "FaceID defekt"

İlanlar:
{listings_text}

Şimdi analiz yap ve JSON döndür:
{{
  "tier_a_prices": [fiyat listesi],
  "tier_b_prices": [fiyat listesi],
  "tier_c_prices": [fiyat listesi],
  "tier_d_prices": [fiyat listesi - bunlar ignore edilecek],
  "avg_tier_a": ortalama_fiyat,
  "avg_tier_b": ortalama_fiyat,
  "avg_tier_c": ortalama_fiyat,
  "pazarlik_marji_pct": yüzde (VB ilanlarında ortalama ne kadar indirim yapılır),
  "tahmini_satis_suresi_gun": ortalama kaç günde satılır,
  "notlar": "kısa piyasa notu"
}}

SADECE JSON döndür, başka açıklama yazma."""

    try:
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL_FLASH,
            contents=prompt,
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)

        import json
        return json.loads(text)
    except Exception as e:
        print(f"[Valuator] Gemini analysis error: {e}")
        return {}


async def valuate_product(product_name: str, search_query: str, location: str = "") -> dict:
    """
    Tam fiyat değerleme pipeline'ı.

    Returns:
        {
            "new_price": float,
            "condition_mint_price": float (satış fiyatı, Tier A)
            "condition_good_price": float (satış fiyatı, Tier B)
            "condition_fair_price": float (satış fiyatı, Tier C)
            "max_buy_price_mint": float (max alım, Tier A — %20 kar marjı)
            "max_buy_price_good": float (max alım, Tier B — %20 kar marjı)
            "pazarlik_marji_pct": int
            "tahmini_satis_suresi_gun": int
            "sample_size": int
            "notlar": str
        }
    """
    new_price, listings = await asyncio.gather(
        get_geizhals_new_price(search_query),
        get_kleinanzeigen_prices(search_query, location),
    )

    print(f"[Valuator] {product_name}: Geizhals={new_price}€, Kleinanzeigen={len(listings)} listings")

    if not listings:
        return {"error": "No listings found"}

    analysis = await analyze_with_gemini(product_name, listings, new_price)

    if not analysis or "avg_tier_a" not in analysis:
        all_prices = iqr_filter([l["price"] for l in listings])
        if not all_prices:
            return {"error": "Could not determine prices"}
        avg = sum(all_prices) / len(all_prices)
        analysis = {
            "avg_tier_a": avg * 1.1,
            "avg_tier_b": avg,
            "avg_tier_c": avg * 0.85,
            "pazarlik_marji_pct": 10,
            "tahmini_satis_suresi_gun": 5,
            "notlar": "Fallback calculation (AI unavailable)",
        }

    mint_sell = analysis.get("avg_tier_a", 0)
    good_sell = analysis.get("avg_tier_b", 0)
    fair_sell = analysis.get("avg_tier_c", 0)
    pazarlik = analysis.get("pazarlik_marji_pct", 10)

    return {
        "new_price": new_price,
        "condition_mint_price": round(mint_sell, 0),
        "condition_good_price": round(good_sell, 0),
        "condition_fair_price": round(fair_sell, 0),
        "max_buy_price_mint": round(mint_sell * 0.80, 0),
        "max_buy_price_good": round(good_sell * 0.80, 0),
        "pazarlik_marji_pct": pazarlik,
        "tahmini_satis_suresi_gun": analysis.get("tahmini_satis_suresi_gun", 5),
        "sample_size": len(listings),
        "notlar": analysis.get("notlar", ""),
    }
