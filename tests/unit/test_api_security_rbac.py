"""Comprehensive Unit Tests for Workstream C: API Security, Authorization (RBAC), and Auditability."""

import datetime
from datetime import timezone
import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app
from apps.api.core.config import settings
from apps.api.core.rbac import (
    ApiKeyRegistry,
    Role,
    hash_key,
    key_registry,
)
from apps.api.core.security import SlidingWindowRateLimiter


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.mark.asyncio
async def test_canonical_root_metadata(client: AsyncClient):
    """Root endpoint must expose canonical version, lifecycle state, and paper-only invariant."""
    res = await client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data["version"] == "0.3.0"
    assert data["lifecycle_state"] == "forward-paper-validation"
    assert data["paper_only"] is True
    assert data["safeguards"]["live_trading_allowed"] is False
    assert data["safeguards"]["real_broker_connected"] is False


@pytest.mark.asyncio
async def test_security_headers_present(client: AsyncClient):
    """Responses must include hardened security headers without unsafe-inline scripts."""
    res = await client.get("/health")
    assert res.status_code == 200
    headers = res.headers

    # CSP checks
    csp = headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]  # No unsafe-inline in script-src!
    assert "frame-ancestors 'none'" in csp
    assert "base-uri 'self'" in csp
    assert "form-action 'self'" in csp

    # Anti-framing & MIME sniffing
    assert headers.get("x-frame-options") == "DENY"
    assert headers.get("x-content-type-options") == "nosniff"
    assert "strict-origin-when-cross-origin" in headers.get("referrer-policy", "")


@pytest.mark.asyncio
async def test_request_id_and_latency_headers(client: AsyncClient):
    """Requests must preserve or generate X-Request-ID and compute X-Process-Time."""
    custom_req_id = "test-corr-id-12345"
    res = await client.get("/health", headers={"X-Request-ID": custom_req_id})
    assert res.status_code == 200
    assert res.headers.get("x-request-id") == custom_req_id
    assert "x-process-time" in res.headers


@pytest.mark.asyncio
async def test_payload_size_limit(client: AsyncClient):
    """Requests with Content-Length exceeding 10MB must be rejected with 413 Payload Too Large."""
    oversized_headers = {
        "content-length": str(15 * 1024 * 1024),  # 15 MB
        "X-Internal-Secret": settings.INTERNAL_API_SECRET,
    }
    res = await client.post("/api/v1/paper-trading/sessions", headers=oversized_headers, json={})
    assert res.status_code == 413
    assert res.json()["code"] == "PAYLOAD_TOO_LARGE"


def test_api_key_registry_hashing_and_constant_time():
    """Keys must be hashed at rest using SHA-256 and verified using constant-time comparison."""
    registry = ApiKeyRegistry()
    raw_secret = "super-secret-key-999"
    key_meta = registry.register_key(
        raw_key=raw_secret,
        key_id="key-001",
        role=Role.RESEARCHER,
        scopes=["read:data", "write:experiments"],
    )

    # Hash verification
    assert key_meta.hashed_key == hash_key(raw_secret)
    assert raw_secret not in key_meta.hashed_key

    # Successful authentication
    auth_result = registry.authenticate(raw_secret)
    assert auth_result is not None
    assert auth_result.key_id == "key-001"
    assert auth_result.role == Role.RESEARCHER
    assert auth_result.last_used_at is not None

    # Invalid secret fails
    assert registry.authenticate("wrong-secret") is None


def test_api_key_rotation_and_revocation():
    """Key rotation preserves metadata; revoked or expired keys fail authentication."""
    registry = ApiKeyRegistry()
    raw_key = "initial-secret-111"
    meta = registry.register_key(raw_key=raw_key, key_id="key-rot-1", role=Role.OPERATOR)

    assert registry.authenticate(raw_key) is not None

    # Rotate key
    new_raw = "rotated-secret-222"
    rotated = registry.rotate_key("key-rot-1", new_raw)
    assert rotated.hashed_key == hash_key(new_raw)

    # Old key fails, new key succeeds
    assert registry.authenticate(raw_key) is None
    assert registry.authenticate(new_raw) is not None

    # Revoke key
    assert registry.revoke_key("key-rot-1") is True
    assert registry.authenticate(new_raw) is None


def test_api_key_expiration():
    """Expired keys must fail closed upon authentication."""
    registry = ApiKeyRegistry()
    raw_key = "expired-secret"
    past_time = datetime.datetime.now(timezone.utc) - datetime.timedelta(hours=1)
    registry.register_key(raw_key=raw_key, key_id="key-exp-1", role=Role.VIEWER, expires_at=past_time)

    assert registry.authenticate(raw_key) is None


def test_role_hierarchy_permissions():
    """Higher roles must subsume lower roles in hierarchy."""
    assert Role.SYSTEM_ADMIN.can_access(Role.RISK_ADMIN)
    assert Role.SYSTEM_ADMIN.can_access(Role.OPERATOR)
    assert Role.SYSTEM_ADMIN.can_access(Role.RESEARCHER)
    assert Role.SYSTEM_ADMIN.can_access(Role.VIEWER)

    assert Role.RISK_ADMIN.can_access(Role.OPERATOR)
    assert Role.OPERATOR.can_access(Role.RESEARCHER)
    assert Role.RESEARCHER.can_access(Role.VIEWER)

    # Lower role cannot access higher role
    assert not Role.VIEWER.can_access(Role.RESEARCHER)
    assert not Role.RESEARCHER.can_access(Role.OPERATOR)
    assert not Role.OPERATOR.can_access(Role.RISK_ADMIN)


def test_sliding_window_rate_limiter():
    """Rate limiter enforces limit over the sliding window."""
    limiter = SlidingWindowRateLimiter(limit=3, window_seconds=10)
    client_ip = "192.168.1.100"

    assert limiter.is_allowed(client_ip) is True
    assert limiter.is_allowed(client_ip) is True
    assert limiter.is_allowed(client_ip) is True
    # 4th request within window rejected
    assert limiter.is_allowed(client_ip) is False


@pytest.mark.asyncio
async def test_prometheus_metrics_endpoint(client: AsyncClient):
    """Runtime observability /metrics endpoint must output Prometheus format metrics."""
    res = await client.get("/metrics")
    assert res.status_code == 200
    assert "text/plain" in res.headers["content-type"]
    text = res.text
    assert "algolab_circuit_breaker_active" in text
    assert "algolab_paper_only_invariant 1" in text
    assert "algolab_live_trading_enabled 0" in text
    assert "algolab_backup_restore_drill_status 1" in text
    assert "algolab_http_auth_failures_total" in text
    assert "algolab_build_info" in text


