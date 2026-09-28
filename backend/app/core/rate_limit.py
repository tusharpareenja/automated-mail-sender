import time
from collections import defaultdict

from app.core.exceptions import RateLimitError

_hits: dict[str, list[float]] = defaultdict(list)


def enforce_rate_limit(key: str, limit: int, window_seconds: int) -> None:
    now = time.time()
    bucket = [stamp for stamp in _hits[key] if now - stamp < window_seconds]
    if len(bucket) >= limit:
        _hits[key] = bucket
        raise RateLimitError("Too many attempts. Wait a minute and try again.")
    bucket.append(now)
    _hits[key] = bucket
