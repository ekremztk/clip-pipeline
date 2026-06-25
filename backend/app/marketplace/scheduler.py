import asyncio
from app.services.supabase_client import get_client
from .models import SearchConfig
from .engine import MarketplaceEngine


async def run_marketplace_scheduler():
    """Poll active searches and run scraper for each."""
    engine = MarketplaceEngine()
    supabase = get_client()

    try:
        res = supabase.table("marketplace_searches").select("*").eq("is_active", True).execute()
        searches = res.data if res.data else []
    except Exception as e:
        print(f"[MarketplaceScheduler] Error fetching searches: {e}")
        return

    if not searches:
        return

    print(f"[MarketplaceScheduler] Running {len(searches)} active searches")

    for search_row in searches:
        config = SearchConfig(
            id=search_row["id"],
            user_id=search_row["user_id"],
            platform=search_row["platform"],
            query=search_row["query"],
            category_id=search_row.get("category_id"),
            location=search_row.get("location"),
            radius_km=search_row.get("radius_km", 30),
            min_price=search_row.get("min_price"),
            max_price=search_row.get("max_price"),
        )

        try:
            await engine.run_search(config)
        except Exception as e:
            print(f"[MarketplaceScheduler] Error running search '{config.query}': {e}")

        await asyncio.sleep(180)


async def run_deal_hunter_scheduler():
    """Run deal hunter for iPhone 14/14 Pro every 10 minutes."""
    from .deal_hunter import run_deal_hunter
    try:
        await run_deal_hunter()
    except Exception as e:
        print(f"[DealHunterScheduler] Error: {e}")
