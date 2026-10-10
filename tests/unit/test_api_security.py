"""Unit tests for Internal API Authentication & Security Remediation (Stage 27 V1.1)."""

import pytest
from httpx import ASGITransport, AsyncClient
from apps.api.main import app
from apps.api.core.config import settings


@pytest.fixture
async def unauth_client():
    """Client without internal authentication headers."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
async def auth_header_client():
    """Client configured with X-Internal-Secret header."""
    transport = ASGITransport(app=app)
    headers = {"X-Internal-Secret": settings.INTERNAL_API_SECRET}
    async with AsyncClient(transport=transport, base_url="http://testserver", headers=headers) as client:
        yield client


@pytest.fixture
async def auth_bearer_client():
    """Client configured with Bearer token header."""
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {settings.INTERNAL_API_SECRET}"}
    async with AsyncClient(transport=transport, base_url="http://testserver", headers=headers) as client:
        yield client


@pytest.mark.asyncio
async def test_health_endpoints_remain_public(unauth_client: AsyncClient):
    """Health probes must remain accessible without authentication for monitoring."""
    resp_liveness = await unauth_client.get("/health")
    assert resp_liveness.status_code == 200
    assert resp_liveness.json()["status"] == "healthy"

    resp_readiness = await unauth_client.get("/health/ready")
    assert resp_readiness.status_code == 200

    resp_system_info = await unauth_client.get("/api/v1/system/info")
    assert resp_system_info.status_code == 200


@pytest.mark.asyncio
async def test_unauthenticated_control_request_rejected(unauth_client: AsyncClient):
    """Control state-mutating requests without credentials must fail closed with 401 Unauthorized."""
    payload = {
        "name": "Unauth Session",
        "strategy_id": "Canonical_SMA",
        "universe": ["NIFTY50"],
    }
    response = await unauth_client.post("/api/v1/paper-trading/sessions", json=payload)
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED_CONTROL_REQUEST"


@pytest.mark.asyncio
async def test_invalid_credentials_rejected(unauth_client: AsyncClient):
    """Control requests with invalid secret header must fail closed with 401 Unauthorized."""
    headers = {"X-Internal-Secret": "invalid_secret_token_123"}
    response = await unauth_client.post(
        "/api/v1/paper-trading/sessions",
        json={"name": "Invalid Auth Test", "strategy_id": "SMA", "universe": ["NIFTY50"]},
        headers=headers,
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_authenticated_control_request_accepted(auth_header_client: AsyncClient):
    """Control requests with valid X-Internal-Secret header must be permitted."""
    payload = {
        "name": "Auth Session Test",
        "strategy_id": "Canonical_SMA",
        "strategy_version": "1.0.0",
        "universe": ["NIFTY50"],
        "initial_capital": 100000.0,
    }
    response = await auth_header_client.post("/api/v1/paper-trading/sessions", json=payload)
    # Status should be 201 Created (or 400 for bad params), but NOT 401 Unauthorized
    assert response.status_code in (201, 400)
    assert response.status_code != 401


@pytest.mark.asyncio
async def test_authenticated_bearer_request_accepted(auth_bearer_client: AsyncClient):
    """Control requests with valid Authorization Bearer header must be permitted."""
    payload = {
        "name": "Bearer Auth Test",
        "strategy_id": "Canonical_SMA",
        "strategy_version": "1.0.0",
        "universe": ["NIFTY50"],
        "initial_capital": 100000.0,
    }
    response = await auth_bearer_client.post("/api/v1/paper-trading/sessions", json=payload)
    assert response.status_code in (201, 400)
    assert response.status_code != 401


@pytest.mark.asyncio
async def test_secret_token_leakage_prevention(unauth_client: AsyncClient):
    """Error responses must never leak the secret token."""
    response = await unauth_client.post("/api/v1/paper-trading/sessions", json={})
    assert response.status_code == 401
    body_text = str(response.json())
    assert settings.INTERNAL_API_SECRET not in body_text
