"""A small in-process sliding-window rate limiter.

Deliberately not `slowapi`: that pulls in a dependency and a decorator style
that makes the limits hard to see. This is a plain ASGI middleware with an
explicit window, so the behaviour is readable in one screen.

It is per-process. Behind more than one worker you want Redis or the platform's
own limiter -- the docs say so, and the middleware is written so swapping the
store is a one-class change.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .config import settings


class SlidingWindowLimiter:
    """Track request timestamps per key and answer "is this one allowed?"."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, now: float | None = None) -> tuple[bool, int]:
        """Record a hit and return (allowed, remaining)."""
        moment = time.monotonic() if now is None else now
        bucket = self._hits[key]

        cutoff = moment - self.window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

        if len(bucket) >= self.limit:
            return False, 0

        bucket.append(moment)
        return True, self.limit - len(bucket)

    def reset(self, key: str | None = None) -> None:
        """Clear one key, or everything (used by tests)."""
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)


def _client_key(request: Request) -> str:
    """Identify a client.

    Uses the left-most X-Forwarded-For entry when present, because behind a
    proxy every request otherwise looks like it came from the proxy. That header
    is spoofable, which is exactly why the limiter is a backstop and not the
    only defence -- auth endpoints also have their own tighter limit.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply a general limit to everything and a tighter one to auth routes."""

    def __init__(self, app) -> None:  # noqa: ANN001
        super().__init__(app)
        self.general = SlidingWindowLimiter(
            settings.rate_limit_requests, settings.rate_limit_window_seconds
        )
        self.auth = SlidingWindowLimiter(
            settings.auth_rate_limit_requests, settings.rate_limit_window_seconds
        )

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        path = request.url.path

        # Health checks and static assets should never be rate limited: a
        # platform probe hitting the limit would take the app down.
        if path.startswith("/static") or path in ("/healthz", "/api/health"):
            return await call_next(request)

        key = _client_key(request)
        limiter = self.auth if path.startswith("/api/auth") else self.general
        allowed, remaining = limiter.check(key)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests. Please slow down and try again shortly.",
                    "retry_after_seconds": limiter.window,
                },
                headers={"Retry-After": str(limiter.window)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limiter.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
