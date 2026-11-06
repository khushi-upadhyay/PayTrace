import json
import logging
import os
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger("paytrace.shelfswipe.channel3")

DEFAULT_CHANNEL3_UCP_URL = "https://ucp.trychannel3.com/mcp"
DEFAULT_TIMEOUT_SECONDS = 15.0


class Channel3ClientError(Exception):
    """Base exception for Channel3 MCP client errors."""
    pass


class Channel3RateLimitError(Channel3ClientError):
    """Raised when Channel3 API responds with HTTP 429 Too Many Requests."""
    pass


class Channel3TimeoutError(Channel3ClientError):
    """Raised when Channel3 API requests time out."""
    pass


class Channel3Client:
    """
    Client for Channel3 Streamable HTTP MCP server (JSON-RPC 2.0).
    Uses standard httpx without an MCP SDK.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self.base_url = (base_url or os.getenv("CHANNEL3_UCP_URL", DEFAULT_CHANNEL3_UCP_URL)).strip()
        self.api_key = (api_key or os.getenv("CHANNEL3_API_KEY", "")).strip()
        self.timeout = timeout
        self.transport = transport
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
                raise Channel3ClientError(
                    f"No valid JSON found in SSE stream from Channel3: {response.text[:200]}"
                )
            return data_blocks[-1]
        else:
            try:
                return response.json()
            except json.JSONDecodeError as exc:
                raise Channel3ClientError(f"Failed to decode Channel3 response as JSON: {exc}")

    def send_rpc(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        is_notification: bool = False,
    ) -> Dict[str, Any]:
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

        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                resp = client.post(self.base_url, headers=headers, json=payload)
                if resp.headers.get("Mcp-Session-Id"):
                    self.session_id = resp.headers.get("Mcp-Session-Id")

                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    detail = f"Rate limit exceeded (HTTP 429)." + (f" Retry after {retry_after}s." if retry_after else "")
                    raise Channel3RateLimitError(detail)

                if resp.status_code >= 400:
                    raise Channel3ClientError(
                        f"Channel3 HTTP {resp.status_code}: {resp.text[:300]}"
                    )

                if is_notification:
                    return {}

                parsed = self._parse_response_content(resp)
                if "error" in parsed:
                    err_detail = parsed["error"]
                    code = err_detail.get("code") if isinstance(err_detail, dict) else ""
                    msg = err_detail.get("message") if isinstance(err_detail, dict) else str(err_detail)
                    raise Channel3ClientError(f"Channel3 JSON-RPC error [{code}]: {msg}")

                return parsed

        except httpx.TimeoutException as exc:
            raise Channel3TimeoutError(f"Channel3 request timed out after {self.timeout}s: {exc}")
        except httpx.RequestError as exc:
            raise Channel3ClientError(f"Network error connecting to Channel3: {exc}")

    def initialize(self) -> Dict[str, Any]:
        params = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "paytrace-shelfswipe", "version": "1.0.0"},
        }
        init_res = self.send_rpc("initialize", params)
        try:
            self.send_rpc("notifications/initialized", {}, is_notification=True)
        except Exception as e:
            logger.debug(f"notifications/initialized notification ignored: {e}")
        return init_res

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        # Ensure session is initialized
        if not self.session_id:
            try:
                self.initialize()
            except Exception as exc:
                logger.warning(f"Initialize attempt prior to tool call failed: {exc}")

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

