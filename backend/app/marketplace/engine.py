from .models import Listing, SearchConfig, DealScore
from .adapters import KleinanzeigenHTTPXAdapter, BaseAdapter
from app.services.supabase_client import get_client


ADAPTERS: dict[str, type[BaseAdapter]] = {
    "kleinanzeigen": KleinanzeigenHTTPXAdapter,
}


class MarketplaceEngine:
    def __init__(self):
        self.supabase = get_client()

    def get_adapter(self, platform: str) -> BaseAdapter:
        adapter_cls = ADAPTERS.get(platform)
        if not adapter_cls:
            raise ValueError(f"Unknown platform: {platform}")
        return adapter_cls()

    async def run_search(self, config: SearchConfig) -> list[Listing]:
        adapter = self.get_adapter(config.platform)
        listings = await adapter.search(config)
        self._save_listings(listings, config.id)
        self._update_last_scraped(config.id)
        self._check_deals(listings, config.user_id)
        return listings

    def _save_listings(self, listings: list[Listing], search_id: str):
        for listing in listings:
            try:
                self.supabase.table("marketplace_listings").upsert(
                    {
                        "platform": listing.platform,
                        "external_id": listing.external_id,
                        "search_id": search_id,
                        "title": listing.title,
                        "price": listing.price,
                        "location": listing.location,
                        "url": listing.url,
                        "thumbnail_url": listing.thumbnail_url,
                        "seller_name": listing.seller_name,
                        "posted_at": listing.posted_at.isoformat() if listing.posted_at else None,
                    },
                    on_conflict="platform,external_id",
                ).execute()
            except Exception as e:
                print(f"[MarketplaceEngine] Error saving listing {listing.external_id}: {e}")

    def _update_last_scraped(self, search_id: str):
        try:
            from datetime import datetime, timezone
            self.supabase.table("marketplace_searches").update(
                {"last_scraped_at": datetime.now(timezone.utc).isoformat()}
            ).eq("id", search_id).execute()
        except Exception as e:
            print(f"[MarketplaceEngine] Error updating last_scraped: {e}")

    def _check_deals(self, listings: list[Listing], user_id: str):
        try:
            products_res = self.supabase.table("marketplace_products").select("*").eq("user_id", user_id).execute()
            products = products_res.data if products_res.data else []

            if not products:
                return

            for listing in listings:
                if listing.price is None:
                    continue

                for product in products:
                    if self._matches_product(listing, product):
                        max_buy = product.get("max_buy_price_good") or product.get("max_buy_price_mint")
                        if max_buy and listing.price <= max_buy:
                            sell_price = product.get("condition_good_price") or product.get("condition_mint_price") or 0
                            profit = sell_price - listing.price
                            score = min(100, max(0, (profit / sell_price) * 100)) if sell_price > 0 else 0

                            listing_res = self.supabase.table("marketplace_listings").select("id").eq(
                                "platform", listing.platform
                            ).eq("external_id", listing.external_id).execute()

                            if listing_res.data:
                                listing_db_id = listing_res.data[0]["id"]
                                existing = self.supabase.table("marketplace_deals").select("id").eq(
                                    "listing_id", listing_db_id
                                ).execute()

                                if not existing.data:
                                    self.supabase.table("marketplace_deals").insert({
                                        "listing_id": listing_db_id,
                                        "product_id": product["id"],
                                        "user_id": user_id,
                                        "score": round(score, 1),
                                        "estimated_profit": round(profit, 2),
                                        "status": "new",
                                    }).execute()
                                    print(f"[MarketplaceEngine] New deal found: {listing.title} ({profit:.0f}€ profit)")
                        break
        except Exception as e:
            print(f"[MarketplaceEngine] Error checking deals: {e}")

    def _matches_product(self, listing: Listing, product: dict) -> bool:
        title_lower = listing.title.lower()
        brand = (product.get("brand") or "").lower()
        model = (product.get("model") or "").lower()
        return brand in title_lower and model in title_lower
