import logging
from typing import Any, Optional

from fastapi import Request

_logger = logging.getLogger("paytrace.security")


def mask_email(email: str) -> str:
    local, _, domain = (email or "").partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def audit(event: str, request: Optional[Request] = None, **fields: Any) -> None:
    """Writes one structured security-event line. Never pass passwords, tokens or card data."""
    ip = request.client.host if request is not None and request.client else "-"
    details = " ".join(f"{k}={v}" for k, v in fields.items() if v is not None)
    _logger.info("SECURITY event=%s ip=%s %s", event, ip, details)
