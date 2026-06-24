"""
Price Analyzer — Toplanan verilerin dağılım analizini yapar ve alım-satım kararı üretir.

Filtreleme: brand + model + storage + tier
Çıktı: sweet_spot_buy, max_buy, realistic_sell, optimistic_sell, verdict (ENTER/SKIP/RISKY)
"""

import json
import re
from typing import Optional
from app.config import settings
from app.services.supabase_client import get_client


async def analyze_price_distribution(
    brand: str,
    model: str,
    storage: Optional[str] = None,
    tier: Optional[str] = None,
) -> dict:
    """
    Belirli bir ürün kombinasyonu için fiyat dağılım analizi yap.

    Args:
        brand: "Apple", "Samsung", etc.
        model: "15 Pro", "S24 Ultra", etc.
        storage: "128GB", "256GB" (optional — None = hepsi)
        tier: "A", "B", "C" (optional — None = hepsi)

    Returns:
        {
            "query": {...},
            "sample_size": int,
            "prices": [...],
            "distribution": {...},
            "sweet_spot_buy": float,
            "max_buy": float,
            "realistic_sell": float,
            "optimistic_sell": float,
            "days_to_sell_estimate": int,
            "verdict": "ENTER" | "SKIP" | "RISKY",
            "reasoning": str,
        }
    """
    supabase = get_client()

    query = supabase.table("marketplace_price_data").select("sold_price, sold_date, tier, flags, battery_pct")
    query = query.eq("brand", brand)
    query = query.eq("model", model)
    if storage:
        query = query.eq("storage", storage)
    if tier:
        query = query.eq("tier", tier)

    query = query.order("sold_date", desc=True)
    result = query.execute()

    data = result.data if result.data else []
    if len(data) < 10:
        return {
            "query": {"brand": brand, "model": model, "storage": storage, "tier": tier},
            "sample_size": len(data),
            "error": f"Yetersiz veri: {len(data)} kayıt (minimum 10 gerekli)",
            "verdict": "INSUFFICIENT_DATA",
        }

    prices = sorted([float(d["sold_price"]) for d in data])

    if len(prices) >= 50:
        return await _ai_distribution_analysis(brand, model, storage, tier, prices)
    else:
        return _basic_distribution_analysis(brand, model, storage, tier, prices)


def _basic_distribution_analysis(
    brand: str, model: str, storage: Optional[str], tier: Optional[str], prices: list[float]
) -> dict:
    """Yeterli veri yoksa (10-49 arası) basit istatistiksel analiz."""
    n = len(prices)
    avg = sum(prices) / n
    median = prices[n // 2]
    p25 = prices[n // 4]
    p75 = prices[3 * n // 4]

    sweet_spot = p25 * 0.90
    max_buy = p25
    realistic_sell = median
    optimistic_sell = p75

    margin = realistic_sell - max_buy
    margin_pct = (margin / max_buy * 100) if max_buy > 0 else 0

    if margin_pct >= 20:
        verdict = "ENTER"
    elif margin_pct >= 10:
        verdict = "RISKY"
    else:
        verdict = "SKIP"

    return {
        "query": {"brand": brand, "model": model, "storage": storage, "tier": tier},
        "sample_size": n,
        "prices": prices,
        "stats": {
            "min": prices[0],
            "max": prices[-1],
            "avg": round(avg, 0),
            "median": median,
            "p25": p25,
            "p75": p75,
        },
        "sweet_spot_buy": round(sweet_spot, 0),
        "max_buy": round(max_buy, 0),
        "realistic_sell": round(realistic_sell, 0),
        "optimistic_sell": round(optimistic_sell, 0),
        "margin_eur": round(margin, 0),
        "margin_pct": round(margin_pct, 1),
        "verdict": verdict,
        "reasoning": f"Basit analiz ({n} veri). Median {median:.0f}€, P25 {p25:.0f}€. Marj: {margin:.0f}€ ({margin_pct:.0f}%).",
        "method": "basic_stats",
    }


async def _ai_distribution_analysis(
    brand: str, model: str, storage: Optional[str], tier: Optional[str], prices: list[float]
) -> dict:
    """50+ veri noktası varsa AI ile derinlemesine dağılım analizi."""
    from google import genai

    client = genai.Client(
        vertexai=True,
        project=settings.GCP_PROJECT,
        location=settings.GCP_LOCATION,
    )

    storage_str = f" {storage}" if storage else ""
    tier_str = f" Tier {tier}" if tier else ""

    prompt = f"""Sen bir piyasa analisti ve alım-satım danışmanısın. Almanya 2. el elektronik pazarı.

ÜRÜN: {brand} {model}{storage_str}{tier_str}
VERİ: Son satılmış {len(prices)} ürünün fiyatları (EUR, sıralı):
{prices}

ANALİZ YAP:

1. Fiyat dağılım bantları oluştur (doğal kırılım noktalarına göre, sabit 5 bant değil):
   Her bant için: alt-üst sınır, kaç ürün (%'si), ve o bandın anlamı

2. Ana kütle nerede yoğunlaşıyor? (ürünlerin çoğunluğu hangi fiyat aralığında satılmış)

3. Alım-satım kararı:
   - sweet_spot_buy: Bu fiyatın altında al = neredeyse kesin kar (%20+ marj garanti)
   - max_buy: Bunun üstüne çıkma, risk başlar
   - realistic_sell: Gerçekçi satış fiyatı (ana kütlenin ortası, 1-5 günde satılır)
   - optimistic_sell: İdeal koşulda satış (üst %25 bandı, sabırlı olursan)
   - days_to_sell_estimate: Ortalama kaç günde satılır

4. KARAR (sadece biri):
   - ENTER: Marj %20+, ana kütle yeterince yüksek, güvenli giriş
   - SKIP: Marj dar (<15%), dağılım sıkışık, risk/ödül kötü
   - RISKY: Marj var ama veri azlığı, volatilite, veya uzun satış süresi

5. Kısa açıklama (reasoning): Neden bu karar? 1-2 cümle.

JSON döndür:
{{
  "distribution_bands": [
    {{"range": "X-Y€", "count": N, "pct": Z, "meaning": "..."}},
    ...
  ],
  "sweet_spot_buy": SAYI,
  "max_buy": SAYI,
  "realistic_sell": SAYI,
  "optimistic_sell": SAYI,
  "days_to_sell_estimate": SAYI,
  "verdict": "ENTER|SKIP|RISKY",
  "reasoning": "..."
}}

SADECE JSON döndür."""

    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt,
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)

        analysis = json.loads(text)

        return {
            "query": {"brand": brand, "model": model, "storage": storage, "tier": tier},
            "sample_size": len(prices),
            "prices": prices,
            "distribution_bands": analysis.get("distribution_bands", []),
            "sweet_spot_buy": analysis.get("sweet_spot_buy"),
            "max_buy": analysis.get("max_buy"),
            "realistic_sell": analysis.get("realistic_sell"),
            "optimistic_sell": analysis.get("optimistic_sell"),
            "days_to_sell_estimate": analysis.get("days_to_sell_estimate"),
            "verdict": analysis.get("verdict", "RISKY"),
            "reasoning": analysis.get("reasoning", ""),
            "method": "ai_analysis",
        }
    except Exception as e:
        print(f"[PriceAnalyzer] AI analysis error: {e}")
        return _basic_distribution_analysis(brand, model, storage, tier, prices)
