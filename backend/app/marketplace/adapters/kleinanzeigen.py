import re
import random
from datetime import datetime, timezone
from ..models import Listing, SearchConfig
from .base import BaseAdapter

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


def _parse_price(text: str) -> float | None:
    if not text:
        return None
    text = text.strip().replace("VB", "").replace("€", "").strip()
    if not text or text == "Zu verschenken":
        return 0.0
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


class KleinanzeigenAdapter(BaseAdapter):
    def platform_name(self) -> str:
        return "kleinanzeigen"

    async def search(self, config: SearchConfig) -> list[Listing]:
        from playwright.async_api import async_playwright

        url = _build_url(config)
        listings: list[Listing] = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1920, "height": 1080},
                locale="de-DE",
            )
            page = await context.new_page()

            try:
                await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                await page.wait_for_selector("article.aditem", timeout=10000)

                articles = await page.query_selector_all("article.aditem")

                for article in articles:
                    try:
                        ad_id = await article.get_attribute("data-adid")
                        if not ad_id:
                            continue

                        link_el = await article.query_selector("a.ellipsis")
                        title = ""
                        href = ""
                        if link_el:
                            title = (await link_el.text_content() or "").strip()
                            href = await link_el.get_attribute("href") or ""

                        price_el = await article.query_selector(".aditem-main--middle--price-shipping--price")
                        price_text = await price_el.text_content() if price_el else ""

                        location_el = await article.query_selector(".aditem-main--top--left")
                        location_text = (await location_el.text_content() if location_el else "").strip()

                        img_el = await article.query_selector("img")
                        thumbnail = await img_el.get_attribute("src") if img_el else None

                        full_url = f"https://www.kleinanzeigen.de{href}" if href.startswith("/") else href

                        listings.append(Listing(
                            external_id=ad_id,
                            platform="kleinanzeigen",
                            title=title,
                            price=_parse_price(price_text or ""),
                            location=location_text if location_text else None,
                            url=full_url,
                            thumbnail_url=thumbnail,
                            posted_at=datetime.now(timezone.utc),
                        ))
                    except Exception as e:
                        print(f"[Kleinanzeigen] Error parsing article: {e}")
                        continue

            except Exception as e:
                print(f"[Kleinanzeigen] Search error for '{config.query}': {e}")
            finally:
                await browser.close()

        print(f"[Kleinanzeigen] Found {len(listings)} listings for '{config.query}'")
        return listings
