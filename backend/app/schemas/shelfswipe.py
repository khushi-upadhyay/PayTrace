from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime

class SellerOnboardRequest(BaseModel):
    shop_url: str
    shop_name: str = "Local Artisan Boutique"
    consent: bool = True

class ShelfProductSchema(BaseModel):
    id: str
    seller_id: str
    name: str
    price: float
    currency: str = "USD"
    image_url: Optional[str] = None
    description: str
    category: str
    stock: int
    status: str
    source: str = "demo"
    why_matches: Optional[str] = None

class ShelfProductDeckResponse(BaseModel):
    deck: List[ShelfProductSchema]
    total_matches: int
    query: str
    refinements_applied: List[str] = []

class SwipeRecordRequest(BaseModel):
    buyer_ref: str
    product_id: str
    direction: str # "right" or "left"

class ShelfSwipeCheckoutRequest(BaseModel):
    product_id: str
    buyer_ref: str
    quantity: int = 1
    simulate_scenario: Optional[str] = None # e.g. "timeout_before_response"
