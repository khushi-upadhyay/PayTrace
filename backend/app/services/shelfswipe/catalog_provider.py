from typing import Protocol, Optional, List
from app.schemas.shelfswipe import McpShopCatalogSchema


class CatalogProvider(Protocol):
    """Protocol for ShelfSwipe catalog providers."""

    def fetch_catalog(
        self,
        shop_url: str,
        product_urls: Optional[List[str]] = None,
    ) -> McpShopCatalogSchema:
        """
        Fetches and normalizes catalog for the given shop and optional product URLs.
        Must return an instance of McpShopCatalogSchema.
        """
        ...

