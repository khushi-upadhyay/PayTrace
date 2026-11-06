import asyncio
import time
from typing import Any, Awaitable, Callable, Dict, Tuple

from fastapi import HTTPException, status


class IdempotencyStore:
    """Replays the result of a request that reuses an Idempotency-Key.

    In-memory and per process (like the rate limiter): good for retries and double submits,
    not a substitute for a shared store if you run several workers.
    """

    def __init__(self, ttl_seconds: int = 86400) -> None:
        self._ttl = ttl_seconds
        self._entries: Dict[str, Tuple[float, str, "asyncio.Future[Any]"]] = {}

    def _purge(self) -> None:
        cutoff = time.monotonic() - self._ttl
        for key in [k for k, (ts, _, _) in self._entries.items() if ts < cutoff]:
            del self._entries[key]

    async def run(self, key: str, fingerprint: str, factory: Callable[[], Awaitable[Any]]) -> Any:
        self._purge()
        entry = self._entries.get(key)
        if entry:
            _, stored_fingerprint, task = entry
            if stored_fingerprint != fingerprint:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Idempotency-Key was already used with a different request",
                )
            return await asyncio.shield(task)
        task = asyncio.ensure_future(factory())
        self._entries[key] = (time.monotonic(), fingerprint, task)
        try:
            return await asyncio.shield(task)
        except BaseException:
            # A failed attempt must not block a retry with the same key.
            if self._entries.get(key, (0, "", None))[2] is task and task.done():
                del self._entries[key]
            raise

    def reset(self) -> None:
        self._entries.clear()


idempotency_store = IdempotencyStore()
