from typing import Optional, List
from app.schemas.shelfswipe import McpShopCatalogSchema
from app.services.shelfswipe import mcp_client


class FixtureCatalogProvider:
    """Provider for fixture-based demo catalogs via ShelfSwipe MCP server."""

    def fetch_catalog(
        self,
        shop_url: str,
        product_urls: Optional[List[str]] = None,
    ) -> McpShopCatalogSchema:
        raw_catalog = mcp_client.fetch_catalog(shop_url)
        catalog = McpShopCatalogSchema.model_validate(raw_catalog)
        catalog.source = "demo"
        for p in catalog.products:
            p.source = "demo"
        return catalog

