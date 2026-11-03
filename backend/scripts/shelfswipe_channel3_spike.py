"""
Standalone spike script for Channel3 Streamable HTTP MCP (JSON-RPC 2.0).
Tests tools/list, search_catalog with catalog.filters.website_ids, pagination cursors,
saves real response fixtures, and evaluates the Day 2 store-filtering Gate.
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import httpx

UCP_URL = os.getenv("CHANNEL3_UCP_URL", "https://ucp.trychannel3.com/mcp").strip()
API_KEY = os.getenv("CHANNEL3_API_KEY", "").strip()

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "channel3"


class Channel3SpikeClient:
    def __init__(self, base_url: str = UCP_URL, api_key: str = API_KEY):
        self.base_url = base_url
        self.api_key = api_key
        self.session_id: Optional[str] = None
        self._request_id = 1

    def _next_id(self) -> int:
        req_id = self._request_id
        self._request_id += 1
        return req_id

    def _parse_response_content(self, response: httpx.Response) -> Dict[str, Any]:
        content_type = response.headers.get("content-type", "").lower()
        if "text/event-stream" in content_type:
            data_blocks = []
            for line in response.text.splitlines():
                line = line.strip()
                if line.startswith("data:"):
                    raw_data = line[5:].strip()
                    if raw_data and raw_data != "[DONE]":
                        try:
                            data_blocks.append(json.loads(raw_data))
                        except json.JSONDecodeError:
                            pass
            if not data_blocks:
                raise RuntimeError(f"No valid JSON found in SSE stream: {response.text[:200]}")
            return data_blocks[-1]
        else:
            return response.json()

    def send_rpc(self, method: str, params: Optional[Dict[str, Any]] = None, is_notification: bool = False) -> Dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if not is_notification:
            payload["id"] = self._next_id()
        if params is not None:
            payload["params"] = params

        max_retries = 3
        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=35.0) as client:
                    resp = client.post(self.base_url, headers=headers, json=payload)
                    if resp.headers.get("Mcp-Session-Id"):
                        self.session_id = resp.headers.get("Mcp-Session-Id")

                    if resp.status_code >= 400:
                        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:400]}")

                    if is_notification:
                        return {}

                    parsed = self._parse_response_content(resp)
                    if "error" in parsed:
                        raise RuntimeError(f"JSON-RPC error in {method}: {parsed['error']}")
                    return parsed
            except Exception as exc:
                if attempt < max_retries - 1:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise exc

    def initialize(self) -> Dict[str, Any]:
        params = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "paytrace-shelfswipe-spike", "version": "1.0.0"},
        }
        init_res = self.send_rpc("initialize", params)
        try:
            self.send_rpc("notifications/initialized", {}, is_notification=True)
        except Exception as e:
            print(f"[warning] notifications/initialized failed: {e}")
        return init_res

    def list_tools(self) -> List[Dict[str, Any]]:
        res = self.send_rpc("tools/list", {})
        result = res.get("result", {})
        return result.get("tools", [])

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        params = {
            "name": name,
            "arguments": arguments,
        }
        res = self.send_rpc("tools/call", params)
        result = res.get("result", {})
        if "structuredContent" in result and result["structuredContent"]:
            return result["structuredContent"]

        content = result.get("content", [])
        if content and isinstance(content, list):
            first = content[0]
            if isinstance(first, dict) and "text" in first:
                try:
                    return json.loads(first["text"])
                except json.JSONDecodeError:
                    return {"text": first["text"]}

        return result


def save_fixture(name: str, data: Any):
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    file_path = FIXTURES_DIR / f"{name}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved fixture: {file_path.relative_to(Path.cwd())}")


def main():
    print(f"=== Channel3 MCP Spike (Documented Store Filter: website_ids) ===")
    print(f"Target URL: {UCP_URL}")
    print(f"API Key: {'[SET]' if API_KEY else '[ANONYMOUS]'}")

    client = Channel3SpikeClient()

    # Step 1: Initialize
    print("\n--- 1. Initializing connection ---")
    try:
        init_res = client.initialize()
        print(f"Initialized successfully. Protocol: {init_res.get('result', {}).get('protocolVersion')}")
        if client.session_id:
            print(f"Session ID received: {client.session_id}")
    except Exception as e:
        print(f"Failed to initialize: {e}")
        sys.exit(1)

    # Step 2: Tools List
    print("\n--- 2. Listing tools ---")
    tools = client.list_tools()
    save_fixture("tools_list", tools)

    # Step 3: Generic search_catalog
    print("\n--- 3. Generic search_catalog ('handmade ceramic mug') ---")
    search_args = {
        "meta": None,
        "catalog": {
            "query": "handmade ceramic mug",
            "pagination": {"limit": 10},
        }
    }
    search_res = client.call_tool("search_catalog", search_args)
    save_fixture("search_generic", search_res)

    products = search_res.get("products", [])
    sample_product_urls = []
    for p in products:
        for v in p.get("variants", []):
            link = v.get("url") or v.get("link")
            if link and len(sample_product_urls) < 5:
                sample_product_urls.append(link)

    # Step 4: Testing target domains with website_ids filter
    test_domains = ["abchome.com", "anthropologie.com", "bloomingdales.com", "aprikamatcha.com"]
    print(f"\n--- 4. Testing store-filtered search with website_ids across: {test_domains} ---")

    domain_reports = []
    page2_saved = False

    for domain in test_domains:
        print(f"\n>> Testing domain: {domain}")
        successful_query = ""
        first_page_res: Dict[str, Any] = {}

        # 1. Try "products", then "shop" if 0 products
        for q in ["products", "shop"]:
            args = {
                "meta": None,
                "catalog": {
                    "query": q,
                    "filters": {
                        "website_ids": [domain]
                    },
                    "pagination": {
                        "limit": 20
                    }
                }
            }
            print(f"  Attempting search with query='{q}', filters.website_ids=['{domain}']...")
            time.sleep(1.0)
            res = client.call_tool("search_catalog", args)
            messages = res.get("messages", [])
            print(f"  messages[]: {messages}")

            # Check if messages report unknown or rejected filter
            for msg in messages:
                content = str(msg.get("content", "")).lower()
                code = str(msg.get("code", "")).lower()
                if "unknown" in content or "reject" in content or "invalid filter" in content or "unknown" in code:
                    print(f"CRITICAL: Server reported rejected/unknown filter: {msg}")
                    sys.exit(1)

            prods = res.get("products", [])
            if prods:
                successful_query = q
                first_page_res = res
                print(f"  Query '{q}' succeeded with {len(prods)} products.")
                break
            else:
                print(f"  Query '{q}' returned 0 products.")
                first_page_res = res

        if not successful_query:
            successful_query = "products"  # fallback label

        # Save first page fixture
        clean_name = domain.replace("/", "_").replace(":", "_").replace(".", "_")
        save_fixture(f"search_store_{clean_name}", first_page_res)

        first_prods = first_page_res.get("products", [])
        pagination_info = first_page_res.get("pagination", {})
        has_next_page = pagination_info.get("has_next_page", False)
        cursor = pagination_info.get("cursor")

        # 2. Inspect first page fields
        matching_prods_count = 0
        matching_distinct_product_ids = set()
        price_shape_ok = True
        sample_price = None
        has_image = 0
        has_desc = 0

        for p in first_prods:
            p_id = p.get("id")
            desc = p.get("description", {})
            if isinstance(desc, dict) and desc.get("plain"):
                has_desc += 1
            elif isinstance(desc, str) and desc.strip():
                has_desc += 1

            if p.get("media"):
                has_image += 1

            matched_this_prod = False
            for v in p.get("variants", []):
                seller = v.get("seller", {})
                v_dom = seller.get("domain") if isinstance(seller, dict) else v.get("domain")
                if v_dom == domain:
                    matched_this_prod = True
                    price = v.get("price")
                    if isinstance(price, dict):
                        sample_price = price
                        if price.get("amount") is None or not price.get("currency"):
                            price_shape_ok = False
                    else:
                        price_shape_ok = False

            if matched_this_prod:
                matching_prods_count += 1
                matching_distinct_product_ids.add(p_id)

        precision = (matching_prods_count / len(first_prods)) if first_prods else 0.0
        every_matches = (matching_prods_count == len(first_prods)) and len(first_prods) > 0

        # 3. Follow pagination cursors up to 3 pages
        pages_followed = 1
        current_cursor = cursor
        current_has_next = has_next_page

        while current_has_next and current_cursor and pages_followed < 3:
            time.sleep(1.0)
            page_num = pages_followed + 1
            print(f"  Following pagination to page {page_num} with cursor: {current_cursor[:30]}...")
            next_args = {
                "meta": None,
                "catalog": {
                    "query": successful_query,
                    "filters": {
                        "website_ids": [domain]
                    },
                    "pagination": {
                        "limit": 20,
                        "cursor": current_cursor
                    }
                }
            }
            try:
                next_res = client.call_tool("search_catalog", next_args)
                next_prods = next_res.get("products", [])
                print(f"  Page {page_num} returned {len(next_prods)} products.")

                if not page2_saved and len(next_prods) > 0:
                    save_fixture(f"search_store_{clean_name}_page2", next_res)
                    page2_saved = True

                for p in next_prods:
                    for v in p.get("variants", []):
                        seller = v.get("seller", {})
                        v_dom = seller.get("domain") if isinstance(seller, dict) else v.get("domain")
                        if v_dom == domain:
                            matching_distinct_product_ids.add(p.get("id"))

                next_pagination = next_res.get("pagination", {})
                current_has_next = next_pagination.get("has_next_page", False)
                current_cursor = next_pagination.get("cursor")
                pages_followed += 1
            except Exception as e:
                print(f"  Pagination error on page {page_num}: {e}")
                break

        domain_reports.append({
            "domain": domain,
            "query_used": successful_query,
            "products_returned": len(first_prods),
            "matching_products": matching_prods_count,
            "precision": precision,
            "every_matches": every_matches,
            "has_next_page": has_next_page,
            "pages_followed": pages_followed,
            "total_distinct_matching": len(matching_distinct_product_ids),
            "sample_price": sample_price,
            "price_shape_ok": price_shape_ok,
            "has_image_count": has_image,
            "has_desc_count": has_desc,
        })

    # Step 5: lookup_catalog with sample URLs
    print(f"\n--- 5. Testing lookup_catalog with {len(sample_product_urls[:3])} URLs ---")
    lookup_args = {
        "meta": None,
        "catalog": {"urls": sample_product_urls[:3]}
    }
    lookup_res = client.call_tool("lookup_catalog", lookup_args)
    save_fixture("lookup_found", lookup_res)

    nf_args = {
        "meta": None,
        "catalog": {"urls": ["https://example.com/products/missing-item-999"]}
    }
    nf_res = client.call_tool("lookup_catalog", nf_args)
    save_fixture("lookup_not_found", nf_res)

    # Step 6: Detailed Spike Report & Gate
    print("\n==========================================================================================")
    print("                          CHANNEL3 SPIKE DETAILED REPORT                                  ")
    print("==========================================================================================")
    print(f"{'Domain':<20} | {'Query':<8} | {'Returned':<8} | {'Matching':<8} | {'Precision':<10} | {'Pages':<6} | {'Total Distinct':<14}")
    print("-" * 90)
    gate_passing_domains = []
    for r in domain_reports:
        print(f"{r['domain']:<20} | {r['query_used']:<8} | {r['products_returned']:<8} | {r['matching_products']:<8} | {r['precision']:<10.1%} | {r['pages_followed']:<6} | {r['total_distinct_matching']:<14}")
        if r['total_distinct_matching'] >= 5 and r['precision'] >= 0.80 and r['price_shape_ok']:
            gate_passing_domains.append(r['domain'])

    print("\nPrice Shape & Data Fields:")
    for r in domain_reports:
        print(f"  {r['domain']}: Sample Price: {r['sample_price']}, Images: {r['has_image_count']}/{r['products_returned']}, Descs: {r['has_desc_count']}/{r['products_returned']}")

    print("\n--- GATE EVALUATION ---")
    print("Gate Rule: PASS only if, for at least 2 domains, at least 5 distinct products each have a matching-domain variant with price & currency AND at least 80% of returned products match the domain.")
    print(f"Domains meeting criteria: {gate_passing_domains}")
    if len(gate_passing_domains) >= 2:
        gate_decision = "PASS"
        print(f"GATE DECISION: PASS (>= 2 domains passed: {gate_passing_domains})")
    else:
        gate_decision = "FAIL"
        print(f"GATE DECISION: FAIL (only {len(gate_passing_domains)} domain(s) passed)")
    print("==========================================================================================\n")


if __name__ == "__main__":
    main()
