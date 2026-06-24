import re
import random
from datetime import datetime, timezone
from typing import Optional

import httpx
from ..models import Listing, SearchConfig
from .base import BaseAdapter

HEADER_SETS = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Ch-Ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Connection": "keep-alive",
        "Cache-Control": "max-age=0",
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "de,en-US;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Sec-Ch-Ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Connection": "keep-alive",
        "Cache-Control": "max-age=0",
    },
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "de,en-US;q=0.7,en;q=0.3",
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Connection": "keep-alive",
        "DNT": "1",
    },
    {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Ch-Ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Linux"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Connection": "keep-alive",
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    },
]


def _parse_price(text: str) -> Optional[float]:
    if not text:
        return None
    text = text.strip()
    if "Zu verschenken" in text:
        return 0.0
    if "VB" in text:
        text = text.replace("VB", "")
    text = text.replace("€", "").strip()
    cleaned = text.replace(".", "").replace(",", ".")
    match = re.search(r"[\d.]+", cleaned)
    return float(match.group()) if match else None


def _build_url(config: SearchConfig) -> str:
    base = "https://www.kleinanzeigen.de/s-suchanfrage.html"
    params = [f"keywords={config.query}"]
    if config.location:
        params.append(f"locationStr={config.location}")
    if config.radius_km:
        params.append(f"radius={config.radius_km}")
    if config.min_price is not None:
        params.append(f"minPrice={int(config.min_price)}")
    if config.max_price is not None:
        params.append(f"maxPrice={int(config.max_price)}")
    if config.category_id:
        params.append(f"categoryId={config.category_id}")
    params.append("sortingField=SORTING_DATE")
    params.append("adType=OFFER")
    return f"{base}?{'&'.join(params)}"


def _parse_listings_from_html(html: str) -> list[Listing]:
    listings: list[Listing] = []

    article_pattern = re.compile(
        r'<article[^>]*data-adid="(\d+)"[^>]*>(.*?)</article>',
        re.DOTALL
    )

    for match in article_pattern.finditer(html):
        ad_id = match.group(1)
        article_html = match.group(2)

        try:
            title_match = re.search(
                r'<a\s+class="ellipsis"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
                article_html, re.DOTALL
            )
            if not title_match:
                continue

            href = title_match.group(1).strip()
            title = re.sub(r'<[^>]+>', '', title_match.group(2)).strip()

            price_match = re.search(
                r'aditem-main--middle--price-shipping--price[^>]*>(.*?)</p>',
                article_html, re.DOTALL
            )
            if not price_match:
                price_match = re.search(
                    r'aditem-main--middle--price[^>]*>(.*?)</p>',
                    article_html, re.DOTALL
                )
            price_text = re.sub(r'<[^>]+>', '', price_match.group(1)).strip() if price_match else ""

            location_match = re.search(
                r'aditem-main--top--left[^>]*>(.*?)</div>',
                article_html, re.DOTALL
            )
            location_text = ""
            if location_match:
                raw = re.sub(r'<[^>]+>', '', location_match.group(1)).strip()
                location_text = re.sub(r'\s+', ' ', raw).strip()

            img_match = re.search(r'<img[^>]*src="([^"]+)"', article_html)
            thumbnail = img_match.group(1) if img_match else None

            full_url = f"https://www.kleinanzeigen.de{href}" if href.startswith("/") else href

            listings.append(Listing(
                external_id=ad_id,
                platform="kleinanzeigen",
                title=title,
                price=_parse_price(price_text),
                location=location_text if location_text else None,
                url=full_url,
                thumbnail_url=thumbnail,
                posted_at=datetime.now(timezone.utc),
            ))
        except Exception as e:
            print(f"[KleinanzeigenHTTPX] Error parsing article {ad_id}: {e}")
            continue

    return listings


class KleinanzeigenHTTPXAdapter(BaseAdapter):
    def platform_name(self) -> str:
        return "kleinanzeigen"

    async def search(self, config: SearchConfig) -> list[Listing]:
        url = _build_url(config)
        headers = random.choice(HEADER_SETS).copy()

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=20.0,
            ) as client:
                response = await client.get(url, headers=headers)

                if response.status_code != 200:
                    print(f"[KleinanzeigenHTTPX] HTTP {response.status_code} for '{config.query}'")
                    if response.status_code == 403 or "IP-Bereich" in response.text:
                        print("[KleinanzeigenHTTPX] BLOCKED — falling back to Playwright")
                        return await self._fallback_playwright(config)
                    return []

                if "IP-Bereich" in response.text or "captcha" in response.text.lower():
                    print("[KleinanzeigenHTTPX] Block detected in response body — falling back to Playwright")
                    return await self._fallback_playwright(config)

                listings = _parse_listings_from_html(response.text)
                print(f"[KleinanzeigenHTTPX] Found {len(listings)} listings for '{config.query}'")
                return listings

        except Exception as e:
            print(f"[KleinanzeigenHTTPX] Request error for '{config.query}': {e}")
            return await self._fallback_playwright(config)

    async def _fallback_playwright(self, config: SearchConfig) -> list[Listing]:
        try:
            from .kleinanzeigen import KleinanzeigenAdapter
            pw_adapter = KleinanzeigenAdapter()
            return await pw_adapter.search(config)
        except Exception as e:
            print(f"[KleinanzeigenHTTPX] Playwright fallback also failed: {e}")
            return []
