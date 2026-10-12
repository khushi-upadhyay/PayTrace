import re
from typing import Any, Dict

SENSITIVE_KEYS = {
    "password", "secret", "client_secret", "access_token", "refresh_token",
    "authorization", "card_number", "cvv", "security_code", "api_key"
}

def redact_sensitive_data(data: Any) -> Any:
    """Recursively redacts sensitive keys and values from dictionaries/lists."""
    if isinstance(data, dict):
        redacted = {}
        for key, value in data.items():
            if any(sens in key.lower() for sens in SENSITIVE_KEYS):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_sensitive_data(value)
        return redacted
    elif isinstance(data, list):
        return [redact_sensitive_data(item) for item in data]
    elif isinstance(data, str):
        # Basic credit card pattern masking (13-19 digits)
        masked = re.sub(r"\b(?:\d[ -]*?){13,19}\b", "[REDACTED_CARD]", data)
        return masked
    return data
