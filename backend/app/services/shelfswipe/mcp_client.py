import os
import httpx
from typing import Any, Dict, List, Optional


DEFAULT_MCP_URL = "https://shelfswipe-mcp.vercel.app/api/mcp"


class McpClientError(Exception):
    """Raised when the ShelfSwipe MCP server call fails or returns an invalid payload."""
    pass


def get_mcp_url() -> str:
    """Reads the MCP server URL at call time from the environment."""
    return os.getenv("SHELFSWIPE_MCP_URL", DEFAULT_MCP_URL).strip() or DEFAULT_MCP_URL


def call_tool(tool: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
    """
    Executes a single tool call on the ShelfSwipe HTTP MCP server.
    Times out after 15 seconds.
    Wraps httpx errors and HTTP 4xx/5xx into McpClientError.
    Validates that 'result' exists in the JSON response.
    """
    url = get_mcp_url()
    payload = {
        "tool": tool,
        "arguments": arguments or {},
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(url, json=payload)
    except httpx.TimeoutException as exc:
        raise McpClientError(f"ShelfSwipe MCP tool '{tool}' timed out after 15s: {exc}") from exc
    except httpx.RequestError as exc:
        raise McpClientError(f"ShelfSwipe MCP network failure calling tool '{tool}': {exc}") from exc

    if response.status_code >= 400:
        error_msg = f"ShelfSwipe MCP HTTP error {response.status_code} on tool '{tool}'"
        try:
            err_data = response.json()
            if isinstance(err_data, dict) and "error" in err_data:
                error_msg += f": {err_data['error']}"
        except Exception:
            error_msg += f": {response.text[:200]}"
        raise McpClientError(error_msg)

    try:
        data = response.json()
    except Exception as exc:
        raise McpClientError(f"ShelfSwipe MCP returned non-JSON response for tool '{tool}': {exc}") from exc

    if not isinstance(data, dict):
        raise McpClientError(f"ShelfSwipe MCP returned unexpected JSON type for tool '{tool}': {type(data).__name__}")

    if "result" not in data:
        err_msg = data.get("error", "missing 'result' field in MCP response")
        raise McpClientError(f"ShelfSwipe MCP tool '{tool}' failed: {err_msg}")

    return data["result"]


def list_shops() -> List[Dict[str, Any]]:
    """Lists all available shops from the MCP fixtures."""
    result = call_tool("list_shops", {})
    if not isinstance(result, list):
        raise McpClientError(f"list_shops expected list, got {type(result).__name__}")
    return result


def fetch_catalog(shop_url: str) -> Dict[str, Any]:
    """Fetches the full catalog for a given shop URL."""
    result = call_tool("fetch_catalog", {"shop_url": shop_url})
    if not isinstance(result, dict):
        raise McpClientError(f"fetch_catalog expected dict, got {type(result).__name__}")
    return result


def search_shop(
    shop_url: str,
    query: Optional[str] = None,
    max_price: Optional[float] = None,
    category: Optional[str] = None,
) -> Any:
    """Searches products within a specific shop."""
    args: Dict[str, Any] = {"shop_url": shop_url}
    if query is not None:
        args["query"] = query
    if max_price is not None:
        args["max_price"] = max_price
    if category is not None:
        args["category"] = category
    return call_tool("search_shop", args)


def search_all_shops(
    query: Optional[str] = None,
    max_price: Optional[float] = None,
    category: Optional[str] = None,
    limit_per_shop: Optional[int] = None,
) -> Any:
    """Searches products across all shops."""
    args: Dict[str, Any] = {}
    if query is not None:
        args["query"] = query
    if max_price is not None:
        args["max_price"] = max_price
    if category is not None:
        args["category"] = category
    if limit_per_shop is not None:
        args["limit_per_shop"] = limit_per_shop
    return call_tool("search_all_shops", args)

