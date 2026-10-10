"""Global pytest configuration for Algo Lab test suite."""

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.core.config import settings


@pytest.fixture
async def async_client():
    """Returns an AsyncClient configured with internal auth headers for testing."""
    transport = ASGITransport(app=app)
    headers = {"X-Internal-Secret": settings.INTERNAL_API_SECRET}
    async with AsyncClient(transport=transport, base_url="http://testserver", headers=headers) as client:
        yield client
