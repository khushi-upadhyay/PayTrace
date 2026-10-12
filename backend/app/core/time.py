from datetime import datetime, timezone

def utc_now() -> datetime:
    """Returns current UTC time without timezone offset for clean database storage."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
