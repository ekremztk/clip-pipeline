from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class Listing(BaseModel):
    external_id: str
    platform: str
    title: str
    price: Optional[float] = None
    location: Optional[str] = None
    url: str
    thumbnail_url: Optional[str] = None
    seller_name: Optional[str] = None
    posted_at: Optional[datetime] = None


class SearchConfig(BaseModel):
    id: str
    user_id: str
    platform: str
    query: str
    category_id: Optional[str] = None
    location: Optional[str] = None
    radius_km: int = 30
    min_price: Optional[float] = None
    max_price: Optional[float] = None


class DealScore(BaseModel):
    listing_id: str
    product_id: Optional[str] = None
    score: float
    estimated_profit: Optional[float] = None
