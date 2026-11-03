import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from app.schemas.shelfswipe import McpShopCatalogSchema, McpProductSchema
from app.services.shelfswipe.channel3_client import Channel3Client, Channel3ClientError

logger = logging.getLogger("paytrace.shelfswipe.channel3_provider")


class Channel3NoProductsError(Exception):
    """Raised when Channel3 lookup or store search resolves 0 usable products."""
    pass


class Channel3CatalogProvider:
    """
    Catalog provider implementing both:
    1. Store-wide search via search_catalog with catalog.filters.website_ids and cursor pagination (capped at 30).
    2. Explicit product enrichment via lookup_catalog for direct product URLs.
    Normalizes cent-to-dollar pricing and extracts merchant metadata.
    """

    def __init__(self, client: Optional[Channel3Client] = None):
        self.client = client or Channel3Client()

    def _extract_domain(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            netloc = parsed.netloc or parsed.path
            domain = netloc.split(":")[0].lower()
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except Exception:
            return ""

    def fetch_catalog(
        self,
        shop_url: str,
        product_urls: Optional[List[str]] = None,
    ) -> McpShopCatalogSchema:
        if product_urls and len(product_urls) > 0:
            return self._fetch_by_lookup(shop_url=shop_url, product_urls=product_urls)
        return self._fetch_by_store_search(shop_url=shop_url)

    def _fetch_by_lookup(
        self,
        shop_url: str,
        product_urls: List[str],
    ) -> McpShopCatalogSchema:
        target_urls = list(product_urls)
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
                f"Channel3 lookup returned 0 products for provided URLs. Messages: {msg_str or 'none'}. "
                "Suggest checking product links, using a demo shop, or manual entry."
            )

        shop_domain = self._extract_domain(shop_url)
        discovered_shop_name = ""
        normalized_products: List[McpProductSchema] = []
        skipped_count = 0

        for p in products_data:
            p_id = p.get("id") or ""
            title = p.get("title") or "Unnamed Product"
            desc_obj = p.get("description", {})
            description = desc_obj.get("plain", "") if isinstance(desc_obj, dict) else str(desc_obj)

            variants = p.get("variants", [])
            selected_variant = None
            for v in variants:
                v_seller = v.get("seller")
                v_dom = v_seller.get("domain") if isinstance(v_seller, dict) else v.get("domain")
                if v_dom:
                    clean_v_dom = str(v_dom).lower()
                    if clean_v_dom.startswith("www."):
                        clean_v_dom = clean_v_dom[4:]
                    if shop_domain and (shop_domain in clean_v_dom or clean_v_dom in shop_domain):
                        selected_variant = v
                        if isinstance(v_seller, dict) and v_seller.get("name") and not discovered_shop_name:
                            discovered_shop_name = v_seller.get("name")
                        break

            if not selected_variant and variants:
                selected_variant = variants[0]
                v_seller = selected_variant.get("seller")
                if isinstance(v_seller, dict) and v_seller.get("name") and not discovered_shop_name:
                    discovered_shop_name = v_seller.get("name")

            if not selected_variant and not variants:
                skipped_count += 1
                continue

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
            raise Channel3NoProductsError(
                "Channel3 lookup returned zero valid products for provided URLs. "
                "Suggest checking product links, using a demo shop, or manual entry."
            )

        final_shop_name = discovered_shop_name or (shop_domain.capitalize() if shop_domain else "Channel3 Merchant")

        return McpShopCatalogSchema(
            shop_id=f"channel3-{shop_domain or 'merchant'}",
            shop_name=final_shop_name,
            shop_url=shop_url,
            contact_email=None,
            description=f"Catalog imported from {final_shop_name} via Channel3.",
            products=normalized_products,
            source_domain=shop_domain or None,
            source="channel3",
            skipped_count=skipped_count,
        )

    def _fetch_by_store_search(self, shop_url: str) -> McpShopCatalogSchema:
        shop_domain = self._extract_domain(shop_url)
        if not shop_domain:
            raise Channel3NoProductsError(
                f"Invalid shop URL '{shop_url}': unable to determine domain for Channel3 store search. "
                "Suggest checking shop URL, using a demo shop, or manual entry."
            )

        discovered_shop_name = ""
        normalized_products: List[McpProductSchema] = []
        skipped_count = 0
        seen_product_ids = set()
        max_cap = 30

        queries_to_try = ["products", "shop"]
        initial_result = None
        successful_query = "products"

        for q in queries_to_try:
            search_args = {
                "meta": None,
                "catalog": {
                    "query": q,
                    "filters": {
                        "website_ids": [shop_domain]
                    },
                    "pagination": {
                        "limit": 20
                    }
                }
            }
            try:
                res = self.client.call_tool("search_catalog", search_args)
            except Exception as exc:
                logger.error(f"Channel3 search_catalog failed for domain '{shop_domain}': {exc}")
                raise

            prods = res.get("products", []) if isinstance(res, dict) else []
            if prods:
                initial_result = res
                successful_query = q
                break
            initial_result = res

        if not initial_result:
            initial_result = {}

        current_res = initial_result
        while True:
            products_data = current_res.get("products", []) if isinstance(current_res, dict) else []
            for p in products_data:
                if len(normalized_products) >= max_cap:
                    break
                p_id = p.get("id") or ""
                if p_id and p_id in seen_product_ids:
                    continue

                variants = p.get("variants", [])
                selected_variant = None
                for v in variants:
                    v_seller = v.get("seller")
                    v_dom = v_seller.get("domain") if isinstance(v_seller, dict) else v.get("domain")
                    if v_dom:
                        clean_v_dom = str(v_dom).lower()
                        if clean_v_dom.startswith("www."):
                            clean_v_dom = clean_v_dom[4:]
                        if clean_v_dom == shop_domain or shop_domain in clean_v_dom or clean_v_dom in shop_domain:
                            selected_variant = v
                            if isinstance(v_seller, dict) and v_seller.get("name") and not discovered_shop_name:
                                discovered_shop_name = v_seller.get("name")
                            break

                if not selected_variant:
                    skipped_count += 1
                    continue

                seen_product_ids.add(p_id)

                title = p.get("title") or "Unnamed Product"
                desc_obj = p.get("description", {})
                description = desc_obj.get("plain", "") if isinstance(desc_obj, dict) else str(desc_obj)

                price_decimal = Decimal("0.00")
                currency = "USD"
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

                image_url = None
                media_list = selected_variant.get("media") or p.get("media") or []
                for m in media_list:
                    if isinstance(m, dict) and m.get("url") and m.get("type", "image") == "image":
                        image_url = m.get("url")
                        break

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

            if len(normalized_products) >= max_cap:
                break

            pagination_info = current_res.get("pagination", {}) if isinstance(current_res, dict) else {}
            has_next = pagination_info.get("has_next_page", False)
            cursor = pagination_info.get("cursor")
            if not (has_next and cursor):
                break

            next_args = {
                "meta": None,
                "catalog": {
                    "query": successful_query,
                    "filters": {
                        "website_ids": [shop_domain]
                    },
                    "pagination": {
                        "limit": 20,
                        "cursor": cursor
                    }
                }
            }
            try:
                current_res = self.client.call_tool("search_catalog", next_args)
            except Exception as exc:
                logger.warning(f"Channel3 search_catalog pagination error: {exc}")
                break

        if not normalized_products:
            raise Channel3NoProductsError(
                f"Channel3 store search returned 0 matching products for domain '{shop_domain}'. "
                "The shop was not found in the catalog. Suggest product links, a demo shop, or manual entry."
            )

        final_shop_name = discovered_shop_name or shop_domain.capitalize()

        return McpShopCatalogSchema(
            shop_id=f"channel3-{shop_domain}",
            shop_name=final_shop_name,
            shop_url=shop_url,
            contact_email=None,
            description=f"Catalog imported from {final_shop_name} via Channel3 store search.",
            products=normalized_products[:max_cap],
            source_domain=shop_domain,
            source="channel3",
            skipped_count=skipped_count,
        )
