import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from app.schemas.shelfswipe import McpShopCatalogSchema, McpProductSchema
from app.services.shelfswipe.channel3_client import Channel3Client, Channel3ClientError

logger = logging.getLogger("paytrace.shelfswipe.channel3_provider")


class Channel3NoProductsError(Exception):
    """Raised when Channel3 lookup resolves 0 usable products."""
    pass


class Channel3CatalogProvider:
    """
    Catalog provider implementing the lookup_catalog enrichment path for Channel3.
    Resolves product-page URLs to rich catalog objects with cent-to-dollar normalization.
    """

    def __init__(self, client: Optional[Channel3Client] = None):
        self.client = client or Channel3Client()

    def _extract_domain(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            netloc = parsed.netloc or parsed.path
            return netloc.split(":")[0].lower()
        except Exception:
            return ""

    def fetch_catalog(
        self,
        shop_url: str,
        product_urls: Optional[List[str]] = None,
    ) -> McpShopCatalogSchema:
        target_urls = list(product_urls or [])
        if not target_urls:
            # If no product URLs were explicitly supplied, try using shop_url if it points to a product page
            target_urls = [shop_url]

        lookup_args = {
            "meta": None,
            "catalog": {
                "urls": target_urls
            }
        }

        try:
            result = self.client.call_tool("lookup_catalog", lookup_args)
        except Exception as exc:
            logger.error(f"Channel3 lookup_catalog failed: {exc}")
            raise

        products_data = result.get("products", []) if isinstance(result, dict) else []
        if not products_data:
            messages = result.get("messages", []) if isinstance(result, dict) else []
            msg_str = "; ".join([m.get("content", "") for m in messages if isinstance(m, dict)])
            raise Channel3NoProductsError(
                f"Channel3 lookup returned 0 products for provided URLs. Messages: {msg_str or 'none'}"
            )

        shop_domain = self._extract_domain(shop_url)
        discovered_shop_name = ""
        normalized_products: List[McpProductSchema] = []

        for p in products_data:
            p_id = p.get("id") or ""
            title = p.get("title") or "Unnamed Product"
            desc_obj = p.get("description", {})
            description = desc_obj.get("plain", "") if isinstance(desc_obj, dict) else str(desc_obj)

            variants = p.get("variants", [])
            # Select best matching variant (matching shop_domain if possible, else first variant)
            selected_variant = None
            for v in variants:
                v_seller = v.get("seller")
                v_dom = v_seller.get("domain") if isinstance(v_seller, dict) else v.get("domain")
                if shop_domain and v_dom and shop_domain in v_dom:
                    selected_variant = v
                    if isinstance(v_seller, dict) and v_seller.get("name"):
                        discovered_shop_name = v_seller.get("name")
                    break

            if not selected_variant and variants:
                selected_variant = variants[0]
                v_seller = selected_variant.get("seller")
                if isinstance(v_seller, dict) and v_seller.get("name") and not discovered_shop_name:
                    discovered_shop_name = v_seller.get("name")

            # Calculate price: Channel3 returns prices in cents! (e.g. 5600 cents = 56.00 USD)
            price_decimal = Decimal("0.00")
            currency = "USD"
            source_url = None
            provider_ref = p_id

            if selected_variant:
                provider_ref = selected_variant.get("id") or p_id
                source_url = selected_variant.get("url")
                v_price = selected_variant.get("price")
                if isinstance(v_price, dict):
                    amount_cents = v_price.get("amount")
                    if amount_cents is not None:
                        price_decimal = Decimal(str(amount_cents)) / Decimal("100")
                    if v_price.get("currency"):
                        currency = str(v_price.get("currency")).upper()
            else:
                price_range = p.get("price_range", {})
                min_p = price_range.get("min") if isinstance(price_range, dict) else None
                if isinstance(min_p, dict) and min_p.get("amount") is not None:
                    price_decimal = Decimal(str(min_p.get("amount"))) / Decimal("100")
                    if min_p.get("currency"):
                        currency = str(min_p.get("currency")).upper()

            # Image URL from variant media or product media
            image_url = None
            media_list = []
            if selected_variant and selected_variant.get("media"):
                media_list = selected_variant.get("media")
            elif p.get("media"):
                media_list = p.get("media")

            for m in media_list:
                if isinstance(m, dict) and m.get("url") and m.get("type", "image") == "image":
                    image_url = m.get("url")
                    break

            # Tags & category
            tags = []
            if p.get("options"):
                for opt in p.get("options"):
                    if isinstance(opt, dict) and opt.get("name"):
                        tags.append(str(opt.get("name")).lower())

            prod_schema = McpProductSchema(
                id=p_id,
                name=title,
                price=price_decimal,
                currency=currency,
                category=p.get("category") or "General",
                description=description,
                image_url=image_url,
                stock=0,
                tags=tags,
                source_url=source_url,
                provider_ref=provider_ref,
                source="channel3",
            )
            normalized_products.append(prod_schema)

        if not normalized_products:
            raise Channel3NoProductsError("Zero valid products could be extracted from Channel3 lookup.")

        final_shop_name = discovered_shop_name or (shop_domain.capitalize() if shop_domain else "Channel3 Merchant")

        catalog = McpShopCatalogSchema(
            shop_id=f"channel3-{shop_domain or 'merchant'}",
            shop_name=final_shop_name,
            shop_url=shop_url,
            contact_email=None,
            description=f"Catalog imported from {final_shop_name} via Channel3.",
            products=normalized_products,
            source_domain=shop_domain or None,
            source="channel3",
        )
        return catalog

