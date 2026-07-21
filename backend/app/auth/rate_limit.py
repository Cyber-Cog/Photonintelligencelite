"""Simple in-memory rate limiter for auth endpoints."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request

_lock = Lock()
_hits: dict[str, deque[float]] = defaultdict(deque)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def check_rate_limit(key: str, *, limit: int, window_sec: float) -> None:
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and now - q[0] > window_sec:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(429, "Too many attempts. Please wait a minute and try again.")
        q.append(now)


def rate_limit_auth(request: Request, action: str, *, limit: int = 10, window_sec: float = 60.0) -> None:
    check_rate_limit(f"{action}:{client_ip(request)}", limit=limit, window_sec=window_sec)
