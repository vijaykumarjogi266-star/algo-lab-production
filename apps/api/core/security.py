"""Institutional API Security, Authorization, and Auditability Middleware.

Workstream C Compliance:
- Role-based authorization: viewer, researcher, operator, risk_admin, system_admin.
- Constant-time verification (hmac.compare_digest) of hashed keys.
- Rate limiting with sliding window counter.
- Maximum request payload size limit (10MB) returning 413 Payload Too Large.
- Strict response security headers (CSP without unsafe-inline scripts, HSTS, X-Frame-Options: DENY, etc.).
- Audit logging for privileged / state-mutating actions.
"""

from __future__ import annotations
import collections
from datetime import datetime, timezone
import json
import logging
import time
from typing import Dict, List, Optional
import uuid

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from apps.api.core.config import settings
from apps.api.core.logging import get_logger
from apps.api.core.rbac import (
    ApiKeyMetadata,
    Role,
    extract_raw_api_key,
    init_default_keys,
    key_registry,
)

logger = get_logger("algo_lab.api.security")

# Initialize default keys from environment
init_default_keys(settings.INTERNAL_API_SECRET)

_auth_failures_total: int = 0


def increment_auth_failure() -> None:
    """Increments the global HTTP 401/403 authorization failure counter for Prometheus metrics."""
    global _auth_failures_total
    _auth_failures_total += 1


def get_auth_failures_total() -> int:
    """Returns current count of 401/403 authorization failures."""
    return _auth_failures_total

# Public read-only paths (monitoring, health probes, schema inspection)
PUBLIC_PATH_PREFIXES = (
    "/health",
    "/api/v1/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/system/info",
    "/api/v1/system/principles",
    "/api/dashboard",
    "/api/v1/dashboard",
    "/metrics",
    "/api/v1/metrics",
)

UNAUTHENTICATED_EXACT_PATHS = (
    "/",
    "/dashboard",
    "/experiments",
    "/backtests",
    "/risk",
)

# 10 Megabytes maximum request body size
MAX_BODY_BYTES = 10 * 1024 * 1024


def is_public_path(path: str) -> bool:
    """Returns True if the path is explicitly designated public/read-only health probe or UI view."""
    if path in UNAUTHENTICATED_EXACT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES)


class SlidingWindowRateLimiter:
    """In-memory sliding window rate limiter per client key/IP."""

    def __init__(self, limit: int = 120, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        self.requests: Dict[str, collections.deque] = collections.defaultdict(collections.deque)

    def is_allowed(self, client_id: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds
        reqs = self.requests[client_id]

        # Purge timestamps outside the sliding window
        while reqs and reqs[0] < window_start:
            reqs.popleft()

        if len(reqs) >= self.limit:
            return False

        reqs.append(now)
        return True


rate_limiter = SlidingWindowRateLimiter(limit=120, window_seconds=60)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Enforces institutional response security headers."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        # Content-Security-Policy (strictly no unsafe-inline scripts)
        csp = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )
        response.headers["Content-Security-Policy"] = csp
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=(), payment=()"

        # HSTS when served over HTTPS or behind TLS proxy
        if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

        return response


class InternalAuthMiddleware(BaseHTTPMiddleware):
    """
    HTTP Middleware enforcing role-based authentication, request size checks, rate limits,
    and structured audit logging.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        method = request.method
        client_ip = request.client.host if request.client else "127.0.0.1"

        # 1. Allow CORS preflight requests
        if method == "OPTIONS":
            return await call_next(request)

        # 2. Enforce request size limit
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                length_int = int(content_length)
                if length_int > MAX_BODY_BYTES:
                    logger.warning("Request body exceeded maximum limit", extra={"size": length_int, "path": path})
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Payload too large. Maximum body size is 10MB.", "code": "PAYLOAD_TOO_LARGE"},
                    )
            except ValueError:
                pass

        # 3. Rate limiting check (exempting health checks)
        if not path.startswith("/health"):
            client_identifier = request.headers.get("X-API-Key") or client_ip
            if not rate_limiter.is_allowed(client_identifier):
                logger.warning("Rate limit exceeded for client", extra={"client": client_identifier, "path": path})
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Rate limit exceeded. Please throttle requests.", "code": "RATE_LIMIT_EXCEEDED"},
                )

        # 4. Extract and verify authentication
        raw_key = extract_raw_api_key(request)
        actor: Optional[ApiKeyMetadata] = None

        if raw_key:
            actor = key_registry.authenticate(raw_key)

        request.state.actor = actor

        # 5. Allow explicitly public read-only health and info endpoints
        if is_public_path(path):
            return await call_next(request)

        # 6. Check GET permissions
        if method == "GET":
            # Private credential endpoints require at least OPERATOR or SYSTEM_ADMIN
            if path.startswith("/api/v1/paper-trading/credentials"):
                if not actor or not actor.role.can_access(Role.OPERATOR):
                    increment_auth_failure()
                    return JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED if not actor else status.HTTP_403_FORBIDDEN,
                        content={
                            "detail": "Operator or System Admin role required to access private credentials.",
                            "code": "UNAUTHORIZED_CONTROL_REQUEST" if not actor else "FORBIDDEN_INSUFFICIENT_ROLE",
                        },
                    )
            # All other GET requests permitted (e.g. research UI or data queries)
            return await call_next(request)

        # 7. State-mutating requests (POST, PUT, DELETE, PATCH) require valid actor
        if not actor:
            increment_auth_failure()
            logger.warning(
                "Rejected unauthenticated control endpoint request",
                extra={"path": path, "method": method, "client": client_ip},
            )
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "detail": "Authentication required for local control endpoint.",
                    "code": "UNAUTHORIZED_CONTROL_REQUEST",
                },
            )

        # 8. Dispatch privileged action and log structured audit record
        start_time = time.perf_counter()
        response = await call_next(request)
        latency_ms = (time.perf_counter() - start_time) * 1000

        # Audit privileged mutation
        logger.info(
            "Privileged mutation executed",
            extra={
                "audit": True,
                "actor_id": actor.key_id,
                "role": actor.role.value,
                "endpoint": path,
                "method": method,
                "status_code": response.status_code,
                "latency_ms": round(latency_ms, 2),
                "client_ip": client_ip,
                "correlation_id": request.headers.get("X-Request-ID", str(uuid.uuid4())),
            },
        )
        return response
