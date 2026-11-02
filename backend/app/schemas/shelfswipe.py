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
    session_id: Optional[str] = None
    simulate_scenario: Optional[str] = None # e.g. "timeout_before_response"

class ShelfCartItemSchema(BaseModel):
    product_id: str
    name: str
    price: float
    currency: str = "USD"
    quantity: int
    image_url: Optional[str] = None
    line_total: float

class ShelfCartResponse(BaseModel):
    buyer_ref: str
    items: List[ShelfCartItemSchema]
    total: float

class ShelfChatMessage(BaseModel):
    role: str # "user" or "assistant"
    content: str

class ShelfChatRequest(BaseModel):
    buyer_ref: str
    message: str
    session_id: Optional[str] = None
    messages: List[ShelfChatMessage] = []

class ShelfCheckoutResult(BaseModel):
    payment_id: str
    paypal_order_id: str
    approval_url: Optional[str] = None
    amount: float
    currency: str
    is_mock: bool

class ShelfChatResponse(BaseModel):
    response: str
    cart: List[ShelfCartItemSchema]
    cart_total: float
    actions_taken: List[str] = []
    checkout: Optional[ShelfCheckoutResult] = None

class ShelfCartCheckoutRequest(BaseModel):
    buyer_ref: str
    session_id: Optional[str] = None
    simulate_scenario: Optional[str] = None
