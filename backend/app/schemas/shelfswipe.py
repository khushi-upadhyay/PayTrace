from pydantic import BaseModel, Field, ConfigDict
from typing import Annotated, Any, Dict, List, Literal, Optional
from decimal import Decimal


# ---------------------------------------------------------
# MCP Server Catalog Schemas (Pydantic v2)
# ---------------------------------------------------------

class McpProductSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    price: Decimal = Field(ge=0)
    currency: str = "USD"
    category: str = ""
    description: str = ""
    image_url: Optional[str] = None
    stock: Optional[int] = 0
    tags: List[str] = Field(default_factory=list)
    source_url: Optional[str] = None
    provider_ref: Optional[str] = None
    source: str = "demo"


class McpShopCatalogSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    shop_id: Optional[str] = None
    shop_name: str
    shop_url: str
    contact_email: Optional[str] = None
    description: Optional[str] = ""
    products: List[McpProductSchema] = Field(default_factory=list)
    source_domain: Optional[str] = None
    source: str = "demo"
    skipped_count: int = 0


# ---------------------------------------------------------
# ShelfSwipe API Request / Response Models
# ---------------------------------------------------------

class ShelfSwipeOnboardRequest(BaseModel):
    shop_url: str
    consent: bool
    seller_name: Optional[str] = None
    provider: str = "fixture"
    product_urls: Optional[List[str]] = None
    ownership_attested: bool = False


class ShelfSwipeOnboardResponse(BaseModel):
    seller_id: str
    shop_id: str
    job_id: str
    products_created: int
    products_skipped: int


class ShelfSwipeDraftProductItem(BaseModel):
    id: str
    external_id: str
    name: str
    price: float
    currency: str
    image_url: Optional[str] = None
    description: str
    category: str
    tags: List[str] = Field(default_factory=list)
    stock: int
    status: str
    data_source: str = "demo"
    source_url: Optional[str] = None
    provider_ref: Optional[str] = None
    review_flags: List[str] = Field(default_factory=list)


class ShelfSwipeDraftResponse(BaseModel):
    seller_id: str
    shop_id: str
    name: str
    description: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    pickup_notes: Optional[str] = None
    is_demo: bool = True
    products: List[ShelfSwipeDraftProductItem] = Field(default_factory=list)


class ProductPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    price: Optional[Decimal] = Field(default=None, ge=0, le=Decimal("99999999.99"), decimal_places=2)
    description: Optional[str] = Field(default=None, max_length=5000)
    category: Optional[str] = Field(default=None, min_length=1, max_length=64)
    tags: Optional[List[Annotated[str, Field(max_length=64)]]] = Field(default=None, max_length=30)
    image_url: Optional[str] = Field(default=None, max_length=1024)
    stock: Optional[int] = Field(default=None, ge=0, le=1_000_000)


class ProductCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=256)
    price: Decimal = Field(ge=0, le=Decimal("99999999.99"), decimal_places=2)
    description: Optional[str] = Field(default="", max_length=5000)
    category: Optional[str] = Field(default="General", min_length=1, max_length=64)
    tags: Optional[List[Annotated[str, Field(max_length=64)]]] = Field(default_factory=list, max_length=30)
    image_url: Optional[str] = Field(default=None, max_length=1024)
    stock: int = Field(default=0, ge=0, le=1_000_000)


class ShopPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pickup_notes: Optional[str] = None
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)


class ApproveItem(BaseModel):
    product_id: str
    confirmed_stock: int = Field(ge=0)


class ApproveRequest(BaseModel):
    items: List[ApproveItem]


class ApproveRejectedItem(BaseModel):
    id: str
    reason: str


class ApproveResponse(BaseModel):
    approved: List[str]
    rejected: List[ApproveRejectedItem]
    still_draft_count: int


# ---------------------------------------------------------
# Legacy Schemas (kept for backward compatibility)
# ---------------------------------------------------------

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
    buyer_ref: str = Field(min_length=1, max_length=64)
    product_id: str = Field(min_length=1, max_length=64)
    direction: Literal["right", "left"]


class ShelfSwipeCheckoutRequest(BaseModel):
    product_id: str = Field(max_length=64)
    buyer_ref: str = Field(min_length=1, max_length=64)
    quantity: int = Field(default=1, ge=1, le=100)
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
    checkout_token: Optional[str] = None

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
