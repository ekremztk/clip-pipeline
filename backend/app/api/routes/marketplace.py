from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel
from typing import Optional
from app.middleware.auth import get_current_user
from app.services.supabase_client import get_client

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


class CreateSearchRequest(BaseModel):
    platform: str = "kleinanzeigen"
    query: str
    category_id: Optional[str] = None
    location: Optional[str] = None
    radius_km: int = 30
    min_price: Optional[float] = None
    max_price: Optional[float] = None


class UpdateDealRequest(BaseModel):
    status: Optional[str] = None
    buy_price: Optional[float] = None
    sell_price: Optional[float] = None
    notes: Optional[str] = None


@router.get("/searches")
async def list_searches(current_user: dict = Depends(get_current_user)):
    try:
        supabase = get_client()
        res = supabase.table("marketplace_searches").select("*").eq(
            "user_id", current_user["id"]
        ).order("created_at", desc=True).execute()
        return {"searches": res.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/searches")
async def create_search(
    request: CreateSearchRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_client()
        res = supabase.table("marketplace_searches").insert({
            "user_id": current_user["id"],
            "platform": request.platform,
            "query": request.query,
            "category_id": request.category_id,
            "location": request.location,
            "radius_km": request.radius_km,
            "min_price": request.min_price,
            "max_price": request.max_price,
            "is_active": True,
        }).execute()

        if res.data:
            background_tasks.add_task(_run_single_search, res.data[0]["id"])

        return {"search": res.data[0] if res.data else None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/searches/{search_id}")
async def delete_search(search_id: str, current_user: dict = Depends(get_current_user)):
    try:
        supabase = get_client()
        supabase.table("marketplace_searches").delete().eq(
            "id", search_id
        ).eq("user_id", current_user["id"]).execute()
        return {"deleted": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/deals")
async def list_deals(
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_client()
        query = supabase.table("marketplace_deals").select(
            "*, listing:marketplace_listings(title, price, location, url, thumbnail_url, platform)"
        ).eq("user_id", current_user["id"]).order("created_at", desc=True)

        if status and status != "all":
            query = query.eq("status", status)

        res = query.execute()
        return {"deals": res.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deals/hunt")
async def trigger_deal_hunt(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """Manually trigger a deal hunt run."""
    background_tasks.add_task(_run_deal_hunt)
    return {"started": True}


@router.post("/deals/{deal_id}/action")
async def deal_action(
    deal_id: str,
    request: UpdateDealRequest,
    current_user: dict = Depends(get_current_user),
):
    """Update deal status (interested, skipped, contacted, bought)."""
    try:
        supabase = get_client()
        update_data = {k: v for k, v in request.model_dump().items() if v is not None}
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        res = supabase.table("marketplace_deals").update(update_data).eq(
            "id", deal_id
        ).eq("user_id", current_user["id"]).execute()

        return {"deal": res.data[0] if res.data else None}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/deals/{deal_id}")
async def get_deal(deal_id: str, current_user: dict = Depends(get_current_user)):
    try:
        supabase = get_client()
        res = supabase.table("marketplace_deals").select(
            "*, listing:marketplace_listings(*), product:marketplace_products(*)"
        ).eq("id", deal_id).eq("user_id", current_user["id"]).execute()

        if not res.data:
            raise HTTPException(status_code=404, detail="Deal not found")
        return {"deal": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/deals/{deal_id}")
async def update_deal(
    deal_id: str,
    request: UpdateDealRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_client()
        update_data = {k: v for k, v in request.model_dump().items() if v is not None}
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        res = supabase.table("marketplace_deals").update(update_data).eq(
            "id", deal_id
        ).eq("user_id", current_user["id"]).execute()

        return {"deal": res.data[0] if res.data else None}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_stats(current_user: dict = Depends(get_current_user)):
    try:
        supabase = get_client()
        user_id = current_user["id"]

        deals = supabase.table("marketplace_deals").select("id", count="exact", head=True).eq("user_id", user_id).execute()
        active_searches = supabase.table("marketplace_searches").select("id", count="exact", head=True).eq("user_id", user_id).eq("is_active", True).execute()
        sales = supabase.table("marketplace_sales").select("net_profit").eq("user_id", user_id).execute()

        total_profit = sum(float(s.get("net_profit", 0)) for s in (sales.data or []))

        return {
            "total_deals": deals.count or 0,
            "active_searches": active_searches.count or 0,
            "total_sales": len(sales.data or []),
            "total_profit": round(total_profit, 2),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _run_single_search(search_id: str):
    import asyncio
    from app.marketplace.engine import MarketplaceEngine
    from app.marketplace.models import SearchConfig

    supabase = get_client()
    res = supabase.table("marketplace_searches").select("*").eq("id", search_id).execute()
    if not res.data:
        return

    row = res.data[0]
    config = SearchConfig(
        id=row["id"],
        user_id=row["user_id"],
        platform=row["platform"],
        query=row["query"],
        category_id=row.get("category_id"),
        location=row.get("location"),
        radius_km=row.get("radius_km", 30),
        min_price=row.get("min_price"),
        max_price=row.get("max_price"),
    )

    engine = MarketplaceEngine()
    asyncio.run(engine.run_search(config))


# === PRICE DATA ENDPOINTS ===

class ValuateRequest(BaseModel):
    query: str
    brand: str
    series: str
    pages: int = 3


@router.post("/valuate")
async def valuate_product(
    request: ValuateRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    background_tasks.add_task(
        _run_valuation, request.query, request.brand, request.series, request.pages
    )
    return {"started": True, "query": request.query, "brand": request.brand, "series": request.series}


@router.get("/price-data")
async def list_price_data(
    brand: Optional[str] = None,
    model: Optional[str] = None,
    storage: Optional[str] = None,
    tier: Optional[str] = None,
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_client()
        query = supabase.table("marketplace_price_data").select("*")
        if brand:
            query = query.eq("brand", brand)
        if model:
            query = query.eq("model", model)
        if storage:
            query = query.eq("storage", storage)
        if tier:
            query = query.eq("tier", tier)
        query = query.order("sold_date", desc=True).limit(limit)
        result = query.execute()
        return {"data": result.data or [], "count": len(result.data or [])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/price-analysis")
async def get_price_analysis(
    brand: str,
    model: str,
    storage: Optional[str] = None,
    tier: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    try:
        from app.marketplace.price_analyzer import analyze_price_distribution
        result = await analyze_price_distribution(brand, model, storage, tier)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _run_valuation(query: str, brand: str, series: str, pages: int):
    import asyncio
    from app.marketplace.price_collector import collect_sold_items
    from app.marketplace.ai_parser import parse_and_save

    async def run():
        items = await collect_sold_items(query, pages=pages)
        if items:
            await parse_and_save(items, brand, series)

    asyncio.run(run())


def _run_deal_hunt():
    import asyncio
    from app.marketplace.deal_hunter import run_deal_hunter
    asyncio.run(run_deal_hunter())
