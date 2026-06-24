"""
eBay.de Verkaufte Artikel (Sold Items) Scraper.

Gerçek satış fiyatlarını çeker — bu istenilen fiyat değil, gerçekten satılmış fiyat.
Kondisyon analizi için: title, price, condition, seller_notes, images, specs döndürür.
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
    """Parse a single eBay item detail page."""
    # Title
    title_m = re.search(r'<title>(.*?)</title>', html)
    title = title_m.group(1).split("|")[0].strip() if title_m else ""
    title = title.replace(" .de", "").replace(".de", "").strip()
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
    if price and (price < 10 or price > 5000):
        price = None

    # Images — full size only (s-l1600), fallback to s-l500
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

    # Seller notes (expandable textual display)
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

    # Fallback: look for seller's condition description near Verkäuferhinweise
    if not seller_notes:
        hinweis_m = re.search(r'Hinweise des Verkäufers.*?<span[^>]*>(.*?)</span>', html, re.DOTALL)
        if hinweis_m:
            raw = re.sub(r'<[^>]+>', ' ', hinweis_m.group(1)).strip()
            raw = re.sub(r'\s+', ' ', raw)
            if len(raw) > 5:
                seller_notes = raw[:500]

    # Item specifics (Artikelmerkmale)
    specifics = {}
    if "Artikelmerkmale" in html:
        spec_section = html[html.find("Artikelmerkmale"):html.find("Artikelmerkmale") + 8000]
        labels = re.findall(r'ux-labels-values__labels.*?<span[^>]*ux-textspans[^>]*>(.*?)</span>', spec_section, re.DOTALL)
        values = re.findall(r'ux-labels-values__values.*?<span[^>]*ux-textspans[^>]*>(.*?)</span>', spec_section, re.DOTALL)
        for i in range(min(len(labels), len(values))):
            k = re.sub(r'<[^>]+>', '', labels[i]).strip()
            v = re.sub(r'<[^>]+>', '', values[i]).strip()
            if k and v and len(k) < 40 and k not in ("Artikelzustand",):
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


async def search_sold_items(query: str, max_items: int = 20, condition: str = "used") -> list[dict]:
    """
    eBay.de'den satılmış ürünleri çek.

    Args:
        query: Arama terimi (ör: "iphone 15 128gb")
        max_items: Maksimum kaç ilan detayı çekilsin
        condition: "used" (3000), "new" (1000), "all" (hepsi)

    Returns:
        List of item dicts with title, price, condition, seller_notes, images, specifics
    """
    condition_param = ""
    if condition == "used":
        condition_param = "&LH_ItemCondition=3000"
    elif condition == "new":
        condition_param = "&LH_ItemCondition=1000"

    search_url = (
        f"https://www.ebay.de/sch/i.html?_nkw={query.replace(' ', '+')}"
        f"&LH_Complete=1&LH_Sold=1&_sop=13{condition_param}&_ipg=60"
    )

    headers = random.choice(HEADER_SETS)

    async with httpx.AsyncClient(follow_redirects=True, timeout=25.0) as client:
        # Get cookies first
        await client.get("https://www.ebay.de", headers=headers)
        await asyncio.sleep(0.5)

        # Search page
        r = await client.get(search_url, headers=headers)
        if r.status_code != 200:
            print(f"[eBaySold] Search failed: HTTP {r.status_code}")
            return []

        # Extract item URLs
        item_urls = re.findall(r'(https://www\.ebay\.de/itm/\d+)', r.text)
        unique_urls = list(dict.fromkeys(item_urls))[:max_items]

        if not unique_urls:
            print(f"[eBaySold] No item URLs found for '{query}'")
            return []

        print(f"[eBaySold] Found {len(unique_urls)} items for '{query}', fetching details...")

        results = []
        for item_url in unique_urls:
            await asyncio.sleep(random.uniform(1.0, 2.0))

            try:
                r2 = await client.get(item_url, headers=headers)
                if r2.status_code != 200:
                    continue

                item = _parse_item_page(r2.text, item_url)
                if item and item["price_eur"]:
                    results.append(item)
            except Exception as e:
                print(f"[eBaySold] Error fetching {item_url}: {e}")
                continue

        print(f"[eBaySold] Successfully parsed {len(results)} items")
        return results
