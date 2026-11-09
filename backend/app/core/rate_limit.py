"""Per-principal rate limiting for the endpoints that spend money on outside
services (Groq/NVIDIA tokens, Gnani audio seconds).

A sliding one-minute window per (principal, bucket), in process memory.
Deliberately simple: correct for a single backend process, which is how this
project runs. With several workers it would need a shared store (Redis) —
noted in docs/ARCHITECTURE.md under scaling, not hidden.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException

_lock = threading.Lock()
_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def check(principal_key: str, bucket: str, per_minute: int) -> None:
    """Raises 429 when `principal_key` has already made `per_minute` calls to
    `bucket` in the last 60 seconds. A limit of 0 or less disables the check."""
    if per_minute <= 0:
        return
    now = time.monotonic()
    key = (principal_key, bucket)
    with _lock:
        window = _hits[key]
        while window and now - window[0] > 60.0:
            window.popleft()
        if len(window) >= per_minute:
            retry_in = int(60.0 - (now - window[0])) + 1
            raise HTTPException(
                status_code=429,
                detail=f"Too many {bucket} requests — limit is {per_minute} per minute. Try again in {retry_in}s.",
            )
        window.append(now)


def reset() -> None:
    with _lock:
        _hits.clear()
