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
        # Basic credit card pattern masking (13-19 digits)
        masked = re.sub(r"\b(?:\d[ -]*?){13,19}\b", "[REDACTED_CARD]", data)
        return masked
    return data
