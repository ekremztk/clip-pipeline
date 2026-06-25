"""
Deal Hunter — Kleinanzeigen'den iPhone 14/14 Pro fırsatları otomatik bulur ve analiz eder.

Flow:
  1. Kleinanzeigen'den ilan listesi çek (fiyat filtreli)
  2. Daha önce görülmüş ilanları atla (external_id check)
  3. Her yeni ilan için detay sayfası çek (açıklama, fotoğraflar, satıcı bilgisi)
  4. Gemini Flash ile multimodal analiz (fotoğraf + text)
  5. eBay sold data ile satış fiyatı tahmini
  6. marketplace_deals tablosuna kaydet
"""

import re
import json
import random
import asyncio
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

USER_ID = "3ebacaef-8982-4e34-a13a-4b50cdf0cc40"

ANALYSIS_PROMPT = """You are an expert deal-hunting AI for used iPhones on Kleinanzeigen (Germany).
You analyze listings to determine if they are good buying opportunities.

LISTING DATA:
- Title: {title}
- Price: {price}€
- Description: {description}
- Location: {location}
- Seller: {seller_name}
- Seller since: {seller_since}
- Number of photos: {num_photos}

TASK: Analyze this listing thoroughly. Extract every possible signal from the data.

Return ONLY valid JSON with this exact structure:
{{
  "model": "iPhone 14" or "iPhone 14 Pro" or "iPhone 14 Pro Max" or "iPhone 14 Plus",
  "storage": "128GB" or "256GB" or "512GB" or null,
  "color": "color name or null",
  "battery_pct": number or null,
  "tier": "A" or "B" or "C" or "D" or "E",
  "tier_reason": "short explanation",
  "condition_notes": "physical condition summary from description/photos",
  "has_box": true/false/null,
  "has_charger": true/false/null,
  "has_receipt": true/false/null,
  "flags": ["flag1", "flag2"],
  "seller_analysis": {{
    "effort_level": "low" or "medium" or "high",
    "urgency": "none" or "low" or "medium" or "high",
    "trust_score": 1-10,
    "reasoning": "Why is this priced this way? What signals do you see about the seller?"
  }},
  "price_assessment": {{
    "is_underpriced": true/false,
    "why_cheap": "explanation of why seller is selling cheap",
    "risk_factors": ["risk1", "risk2"]
  }},
  "confidence": 0.0-1.0,
  "reject": false,
  "reject_reason": null
}}

If this is NOT an iPhone 14/14 Pro (e.g. accessory, case, repair, wrong model), set "reject": true and "reject_reason": "explanation".

TIER RULES:
- A: Like new, box, receipt, battery 90%+, no scratches
- B: Good condition, battery 85%+, no visible damage, may miss box/accessories
- C: Working, visible wear/scratches, battery 80%+
- D: Significant damage or battery below 80%, still functional
- E: iCloud locked, broken screen, water damage, scam, parts only

SELLER PSYCHOLOGY SIGNALS:
- Low effort (short/no description, few bad photos) = often doesn't know market value = OPPORTUNITY
- Urgency signals (ASAP, schnell, dringend, heute noch) = willing to accept lower price
- Abholung only = local seller, often more negotiable
- Very new account + too good price = potential scam
- Long-time seller with many ratings = trustworthy but knows value

FLAGS: no_box, no_charger, with_box, with_receipt, low_battery, screen_scratches,
cracked_back, cracked_screen, dent_or_bend, water_damage, face_id_broken,
icloud_locked, possible_scam, like_new, heavy_use, insufficient_info"""


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
        img_matches = re.findall(
            r'(https://img\.kleinanzeigen\.de/api/v1/prod-ads/images/[^"\']+)',
            html
        )
        seen = set()
        for img_url in img_matches:
            clean = img_url.split("?")[0]
            if clean not in seen:
                seen.add(clean)
                images.append(clean + "?rule=$_57.JPG")
        if not images:
            img_matches = re.findall(r'data-imgsrc="([^"]+)"', html)
            for img_url in img_matches:
                clean = img_url.split("?")[0]
                if clean not in seen:
                    seen.add(clean)
                    images.append(clean + "?rule=$_57.JPG")

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
) -> Optional[dict]:
    """Run Gemini Flash analysis on a single listing."""
    from app.services.gemini_client import get_gemini_client

    client = get_gemini_client()

    prompt = ANALYSIS_PROMPT.format(
        title=title,
        price=price,
        description=description or "(no description)",
        location=location or "unknown",
        seller_name=seller_name or "unknown",
        seller_since=seller_since or "unknown",
        num_photos=len(images),
    )

    if images:
        prompt += f"\n\nIMAGE URLs (for context — assess photo quality/effort from count and description):\n"
        for i, img in enumerate(images[:5], 1):
            prompt += f"  {i}. {img}\n"

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
    """Query marketplace_price_data for sell price estimates."""
    supabase = get_client()

    adjacent_tiers = {
        "A": ["A", "B"],
        "B": ["B", "A", "C"],
        "C": ["C", "B", "D"],
        "D": ["D", "C"],
        "E": ["E", "D"],
    }
    tiers_to_check = adjacent_tiers.get(tier, [tier])

    try:
        query = supabase.table("marketplace_price_data").select("sold_price, tier")
        query = query.eq("brand", "Apple")

        if "Pro Max" in model_parsed:
            query = query.ilike("model", "%14 Pro Max%")
        elif "Pro" in model_parsed:
            query = query.ilike("model", "%14 Pro%")
        else:
            query = query.ilike("model", "%14%")
            query = query.not_.ilike("model", "%Pro%")

        if storage:
            query = query.eq("storage", storage)

        query = query.in_("tier", tiers_to_check)
        query = query.order("sold_date", desc=True)
        query = query.limit(30)

        result = query.execute()
        data = result.data if result.data else []

        if len(data) < 3:
            return {"min_sell": None, "realistic_sell": None, "max_sell": None, "sample_size": len(data)}

        prices = sorted([float(d["sold_price"]) for d in data])
        n = len(prices)

        return {
            "min_sell": round(prices[int(n * 0.1)], 0),
            "realistic_sell": round(prices[n // 2], 0),
            "max_sell": round(prices[int(n * 0.85)], 0),
            "sample_size": n,
        }
    except Exception as e:
        print(f"[DealHunter] Price estimation error: {e}")
        return {"min_sell": None, "realistic_sell": None, "max_sell": None, "sample_size": 0}


async def run_deal_hunter():
    """Main deal hunter loop — scrape Klein, analyze, save."""
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
        )

        print(f"[DealHunter] Searching: {search_cfg['query']} ({search_cfg['min_price']}-{search_cfg['max_price']}€)")
        listings = await adapter.search(config)

        if not listings:
            print(f"[DealHunter] No listings found for '{search_cfg['query']}'")
            continue

        print(f"[DealHunter] Found {len(listings)} listings for '{search_cfg['query']}'")

        existing_res = supabase.table("marketplace_listings").select("external_id").eq(
            "platform", "kleinanzeigen"
        ).execute()
        existing_ids = {r["external_id"] for r in (existing_res.data or [])}

        new_listings = [l for l in listings if l.external_id not in existing_ids]
        print(f"[DealHunter] {len(new_listings)} new listings (skipping {len(listings) - len(new_listings)} seen)")

        if not new_listings:
            continue

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
                )

                if not analysis:
                    continue

                if analysis.get("reject"):
                    print(f"[DealHunter] REJECT: {listing.title} — {analysis.get('reject_reason', '?')}")
                    continue

                model_parsed = analysis.get("model", "iPhone 14")
                storage_parsed = analysis.get("storage")
                tier = analysis.get("tier", "C")

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
                            "has_box": analysis.get("has_box"),
                            "has_charger": analysis.get("has_charger"),
                            "has_receipt": analysis.get("has_receipt"),
                            "flags": analysis.get("flags", []),
                            "price_assessment": analysis.get("price_assessment", {}),
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
