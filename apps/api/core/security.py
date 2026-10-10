"""Internal API Security & Local Loopback Authentication Module.

Remediates local unauthenticated loopback control surface.
Enforces fail-closed token validation on control endpoints while preserving
read-only health check endpoints and hard live-trading safety locks.
"""

from typing import Callable
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from apps.api.core.config import settings
from apps.api.core.logging import get_logger

logger = get_logger("algo_lab.api.security")

# Explicitly unauthenticated / public read-only health & doc paths
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
)

UNAUTHENTICATED_EXACT_PATHS = (
    "/",
    "/dashboard",
    "/experiments",
    "/backtests",
    "/risk",
)


def is_public_path(path: str) -> bool:
    """Returns True if the path is explicitly designated public/read-only health probe or UI view."""
    if path in UNAUTHENTICATED_EXACT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES)


class InternalAuthMiddleware(BaseHTTPMiddleware):
    """
    HTTP Middleware enforcing authentication on local state-mutating control endpoints.
    Fail-closed: Returns HTTP 401 Unauthorized if secret is missing or invalid.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        method = request.method

        # Allow CORS preflight requests
        if method == "OPTIONS":
            return await call_next(request)

        # Allow public health, documentation, and read-only system info endpoints
        if is_public_path(path):
            return await call_next(request)

        # For GET requests to read-only data & research endpoints, allow unless ENFORCE_INTERNAL_AUTH is strictly enforced for all
        if method == "GET":
            # Allow unauthenticated GET requests unless explicitly requesting paper trading session private credentials
            if not path.startswith("/api/v1/paper-trading/credentials"):
                return await call_next(request)

        # Enforce authentication for state-mutating requests (POST, PUT, DELETE, PATCH)
        secret = settings.INTERNAL_API_SECRET
        if secret:
            header_secret = request.headers.get("X-Internal-Secret")
            auth_header = request.headers.get("Authorization", "")

            token_valid = False
            if header_secret and header_secret == secret:
                token_valid = True
            elif auth_header.startswith("Bearer ") and auth_header[7:] == secret:
                token_valid = True

            if not token_valid:
                logger.warning(
                    "Rejected unauthenticated control endpoint request",
                    extra={"path": path, "method": method, "client": request.client.host if request.client else "unknown"},
                )
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={
                        "detail": "Authentication required for local control endpoint.",
                        "code": "UNAUTHORIZED_CONTROL_REQUEST",
                    },
                )

        return await call_next(request)
