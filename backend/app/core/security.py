import re
from typing import Any, Dict

SENSITIVE_KEYS = {
    "password", "secret", "client_secret", "access_token", "refresh_token",
    "authorization", "card_number", "cvv", "security_code", "api_key", "credential",
    "cvc",
}
NORMALIZED_SENSITIVE_KEYS = {re.sub(r"[^a-z0-9]", "", key.lower()) for key in SENSITIVE_KEYS}

def redact_sensitive_data(data: Any) -> Any:
    """Recursively redacts sensitive keys and values from dictionaries/lists."""
    if isinstance(data, dict):
        redacted = {}
        for key, value in data.items():
            normalized_key = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if normalized_key == "pan" or any(sens in normalized_key for sens in NORMALIZED_SENSITIVE_KEYS):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_sensitive_data(value)

        # Apply a second server-side guard to rrweb serialized form controls,
        # even if a future browser recorder configuration stops masking values.
        tag_name = str(data.get("tagName", "")).lower()
        attributes = redacted.get("attributes")
        if tag_name in {"input", "textarea", "select"} and isinstance(attributes, dict) and "value" in attributes:
            attributes["value"] = "[REDACTED]"
        if data.get("isInput") is True:
            for field in ("value", "text"):
                if field in redacted:
                    redacted[field] = "[REDACTED]"
        return redacted
    elif isinstance(data, list):
        return [redact_sensitive_data(item) for item in data]
    elif isinstance(data, str):
        data = data.replace("\x00", "")  # NUL bytes are rejected by Postgres text/JSON columns
        # Credit card pattern masking: either an unbroken 13-19 digit run, or
        # groups of 4 digits joined by a single consistent space/dash (standard
        # card formatting). Deliberately narrower than "any digits with dashes
        # mixed in" so it doesn't also catch UUIDs, order IDs, etc.
        # (?<!\.) skips the fractional part of decimals (e.g. SVG coordinates such as 423.16666666666663).
        masked = re.sub(r"(?<!\.)\b\d{13,19}\b|\b\d{4}([ -])\d{4}\1\d{4}\1\d{1,7}\b", "[REDACTED_CARD]", data)
        return masked
    return data


# --- Password hashing & session tokens -------------------------------------
import base64
import hashlib
import hmac
import os
from datetime import timedelta

import jwt
from typing import Optional

from app.core.config import settings
from app.core.time import utc_now

_PBKDF2_ITERATIONS = 390_000


def hash_password(password: str) -> str:
    """Salted PBKDF2-SHA256 hash, stored as `pbkdf2_sha256$<iterations>$<salt>$<hash>`."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_b64, hash_b64 = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iterations))
        return hmac.compare_digest(digest, base64.b64decode(hash_b64))
    except Exception:
        return False


def create_checkout_token(order_id: str) -> str:
    """Unguessable per-order capability token, returned only to the buyer who created the order."""
    return hmac.new(settings.AUTH_SECRET_KEY.encode(), f"checkout:{order_id}".encode(), hashlib.sha256).hexdigest()


def verify_checkout_token(order_id: str, token: Optional[str]) -> bool:
    return bool(token) and hmac.compare_digest(create_checkout_token(order_id), token)


def create_access_token(user_id: str) -> str:
    now = utc_now()
    payload = {"sub": user_id, "iat": now, "exp": now + timedelta(minutes=settings.AUTH_TOKEN_TTL_MINUTES)}
    return jwt.encode(payload, settings.AUTH_SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> Optional[str]:
    """Returns the user id from a valid token, or None if invalid/expired."""
    try:
        return jwt.decode(token, settings.AUTH_SECRET_KEY, algorithms=["HS256"]).get("sub")
    except jwt.PyJWTError:
        return None
