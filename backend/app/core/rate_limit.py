import threading
import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict

from fastapi import HTTPException, Request, status

from app.core.audit import audit
from app.core.config import settings


class RateLimiter:
    """In-memory sliding-window limiter. Per process: run a shared store (e.g. Redis) if you scale to several workers."""

    def __init__(self) -> None:
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                retry_after = max(1, int(window_seconds - (now - hits[0])))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please slow down and try again shortly.",
                    headers={"Retry-After": str(retry_after)},
                )
            hits.append(now)
            if len(self._hits) > 10_000:
                self._prune(now, window_seconds)

    def _prune(self, now: float, window_seconds: int) -> None:
        for k in [k for k, v in self._hits.items() if not v or v[-1] <= now - window_seconds]:
            del self._hits[k]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def rate_limit(scope: str, limit: int, window_seconds: int = 60) -> Callable[[Request], None]:
    """FastAPI dependency limiting `limit` calls per `window_seconds` per client IP for this scope."""

    def dependency(request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        try:
            limiter.check(f"{scope}:{client}", limit, window_seconds)
        except HTTPException:
            audit("rate_limited", request, scope=scope, path=request.url.path)
            raise

    return dependency
