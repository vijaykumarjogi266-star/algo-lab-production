"""Unit tests for Backtest API Status Endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient
from apps.api.main import app
from apps.api.core.config import settings


@pytest.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_backtest_status_endpoint(async_client: AsyncClient):
    response = await async_client.get(f"{settings.API_V1_PREFIX}/backtest/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["engine"] == "backtest-engine"
    assert data["version"] == settings.PROJECT_VERSION
    assert "capabilities" in data
    assert "contracts" in data["capabilities"]
    assert "metrics" in data["capabilities"]
    assert "cost_models" in data["capabilities"]
    assert "portfolio" in data["capabilities"]
