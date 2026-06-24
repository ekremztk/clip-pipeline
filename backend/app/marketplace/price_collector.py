"""
Price Collector — eBay.de satılmış ürünleri sayfalama ile toplar.

Geniş arama yapar (ör: "iphone 15"), tüm varyasyonları çeker,
dedup yapar, detay sayfalarını getirir.
"""

import re
import random
import asyncio
from typing import Optional
import httpx

HEADER_SETS = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9",
        "Sec-Ch-Ua": '"Google Chrome";v="125", "Chromium";v="125"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Upgrade-Insecure-Requests": "1",
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.7",
        "Sec-Ch-Ua": '"Google Chrome";v="125", "Chromium";v="125"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Upgrade-Insecure-Requests": "1",
    },
]


def _parse_item_page(html: str, url: str) -> Optional[dict]:
    """Parse a single eBay item detail page into structured data."""
    # Title
    title_m = re.search(r'<title>(.*?)</title>', html)
    title = title_m.group(1).split("|")[0].strip() if title_m else ""
    title = re.sub(r'\s*\.de$', '', title).strip()
    if not title:
        return None

    # Price — handle German format (1.234,56 or 234,56)
    price_m = re.search(r'EUR\s*([\d.,]+)', html)
    price_str = price_m.group(1) if price_m else ""
    price = None
    if price_str:
        if "," in price_str:
            parts = price_str.split(",")
            integer_part = parts[0].replace(".", "")
            decimal_part = parts[1] if len(parts) > 1 else "00"
            price = float(f"{integer_part}.{decimal_part}")
        else:
            price = float(price_str.replace(".", ""))
    if not price or price < 10 or price > 5000:
        return None

    # Images — full size (s-l1600), fallback s-l500
    images = list(dict.fromkeys(
        re.findall(r'(https://i\.ebayimg\.com/images/g/[A-Za-z0-9_-]+/s-l1600\.\w+)', html)
    ))[:8]
    if not images:
        images = list(dict.fromkeys(
            re.findall(r'(https://i\.ebayimg\.com/images/g/[A-Za-z0-9_-]+/s-l500\.\w+)', html)
        ))[:8]

    # Condition (Artikelzustand)
    condition = ""
    if "Artikelzustand" in html:
        spec_area = html[html.find("Artikelzustand"):html.find("Artikelzustand") + 2000]
        cond_m = re.search(r'ux-textspans[^>]*>(Gebraucht|Neu|Sehr gut|Gut|Akzeptabel)', spec_area)
        if cond_m:
            condition = cond_m.group(1)
    if not condition:
        for kw in ["Gebraucht", "Neu", "Sehr gut", "Gut", "Akzeptabel"]:
            if f">{kw}<" in html:
                condition = kw
                break

    # Seller notes
    seller_notes = ""
    notes_m = re.search(
        r'ux-expandable-textual-display[^>]*>.*?<span[^>]*class="ux-textspans[^"]*"[^>]*>(.*?)</span>',
        html, re.DOTALL
    )
    if notes_m:
        raw = re.sub(r'<[^>]+>', ' ', notes_m.group(1)).strip()
        raw = re.sub(r'\s+', ' ', raw)
        if len(raw) > 10 and "Artikelzustand" not in raw:
            seller_notes = raw[:500]
    if not seller_notes:
        hinweis_m = re.search(r'Hinweise des Verkäufers.*?<span[^>]*>(.*?)</span>', html, re.DOTALL)
        if hinweis_m:
            raw = re.sub(r'<[^>]+>', ' ', hinweis_m.group(1)).strip()
            raw = re.sub(r'\s+', ' ', raw)
            if len(raw) > 5:
                seller_notes = raw[:500]

    # Item specifics
    specifics = {}
    if "Artikelmerkmale" in html:
        spec_section = html[html.find("Artikelmerkmale"):html.find("Artikelmerkmale") + 8000]
        labels = re.findall(r'ux-labels-values__labels.*?<span[^>]*ux-textspans[^>]*>(.*?)</span>', spec_section, re.DOTALL)
        values = re.findall(r'ux-labels-values__values.*?<span[^>]*ux-textspans[^>]*>(.*?)</span>', spec_section, re.DOTALL)
        for i in range(min(len(labels), len(values))):
            k = re.sub(r'<[^>]+>', '', labels[i]).strip()
            v = re.sub(r'<[^>]+>', '', values[i]).strip()
            if k and v and len(k) < 40 and k != "Artikelzustand":
                specifics[k] = v

    # Sold date
    sold_date = ""
    date_m = re.search(r'(\d{1,2})\.\s*(Jan|Feb|Mär|Apr|Mai|Jun|Jul|Aug|Sep|Okt|Nov|Dez)\.?\s*(\d{4})', html)
    if date_m:
        sold_date = f"{date_m.group(1)}. {date_m.group(2)}. {date_m.group(3)}"

    return {
        "title": title,
        "price_eur": price,
        "condition": condition,
        "seller_notes": seller_notes,
        "images": images,
        "specifics": specifics,
        "sold_date": sold_date,
        "url": url,
    }


async def collect_sold_items(query: str, pages: int = 3, condition: str = "used") -> list[dict]:
    """
    eBay.de'den satılmış ürünleri sayfalama ile topla.

    Args:
        query: Geniş arama terimi (ör: "iphone 15", "samsung galaxy s24")
        pages: Kaç sayfa çekilsin (her sayfa 60 sonuç)
        condition: "used", "new", "all"

    Returns:
        List of parsed item dicts
    """
    condition_param = ""
    if condition == "used":
        condition_param = "&LH_ItemCondition=3000"
    elif condition == "new":
        condition_param = "&LH_ItemCondition=1000"

    headers = random.choice(HEADER_SETS)

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        # Get cookies
        await client.get("https://www.ebay.de", headers=headers)
        await asyncio.sleep(0.5)

        # Collect item URLs from multiple pages
        all_item_urls: list[str] = []

        for page_num in range(1, pages + 1):
            page_param = f"&_pgn={page_num}" if page_num > 1 else ""

            search_url = (
                f"https://www.ebay.de/sch/i.html?_nkw={query.replace(' ', '+')}"
                f"&LH_Complete=1&LH_Sold=1&_sop=13{condition_param}&_ipg=60{page_param}"
            )

            try:
                r = await client.get(search_url, headers=headers)
                if r.status_code != 200:
                    print(f"[PriceCollector] Page {page_num} failed: HTTP {r.status_code}")
                    break

                page_urls = re.findall(r'(https://www\.ebay\.de/itm/\d+)', r.text)
                new_urls = [u for u in page_urls if u not in all_item_urls]
                all_item_urls.extend(new_urls)
                print(f"[PriceCollector] Page {page_num}: {len(new_urls)} new URLs (total: {len(all_item_urls)})")

                if len(new_urls) < 10:
                    break

                await asyncio.sleep(random.uniform(2.0, 4.0))
            except Exception as e:
                print(f"[PriceCollector] Page {page_num} error: {e}")
                break

        # Dedup
        unique_urls = list(dict.fromkeys(all_item_urls))
        print(f"[PriceCollector] Total unique URLs: {len(unique_urls)}")

        # Fetch item details with rate limiting
        results: list[dict] = []
        consecutive_fails = 0

        for i, item_url in enumerate(unique_urls):
            # Rotate headers every 25 requests
            if i > 0 and i % 25 == 0:
                headers = random.choice(HEADER_SETS)
                pause = random.uniform(6.0, 10.0)
                print(f"[PriceCollector] Rotating headers, pausing {pause:.1f}s...")
                await asyncio.sleep(pause)
            else:
                await asyncio.sleep(random.uniform(1.5, 3.0))

            try:
                r2 = await client.get(item_url, headers=headers)

                if r2.status_code == 429:
                    print(f"[PriceCollector] Rate limited at item {i+1}, pausing 15s...")
                    await asyncio.sleep(15.0)
                    headers = random.choice(HEADER_SETS)
                    r2 = await client.get(item_url, headers=headers)

                if r2.status_code != 200:
                    consecutive_fails += 1
                    if consecutive_fails >= 5:
                        print(f"[PriceCollector] 5 consecutive failures, stopping.")
                        break
                    continue

                consecutive_fails = 0
                item = _parse_item_page(r2.text, item_url)
                if item:
                    results.append(item)

                if (i + 1) % 20 == 0:
                    print(f"[PriceCollector] Fetched {i + 1}/{len(unique_urls)} items ({len(results)} parsed)")
            except Exception as e:
                print(f"[PriceCollector] Error fetching item {i + 1}: {e}")
                consecutive_fails += 1
                if consecutive_fails >= 5:
                    print(f"[PriceCollector] 5 consecutive failures, stopping.")
                    break
                continue

        print(f"[PriceCollector] Done: {len(results)} items parsed from {len(unique_urls)} URLs")
        return results
