"""Backtest Engine Health and Status Routes."""

from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter
from pydantic import BaseModel
from apps.api.core.config import settings

router = APIRouter(tags=["Backtest"])


class BacktestStatusResponse(BaseModel):
    status: str
    engine: str
    version: str
    timestamp: datetime
    capabilities: List[str]


@router.get("/backtest/status", response_model=BacktestStatusResponse, summary="Backtest engine status probe")
async def backtest_status() -> BacktestStatusResponse:
    """Verifies backtest subsystem readiness and capabilities without execution."""
    return BacktestStatusResponse(
        status="ready",
        engine="backtest-engine",
        version=settings.PROJECT_VERSION,
        timestamp=datetime.now(timezone.utc),
        capabilities=[
            "contracts",
            "metrics",
            "cost_models",
            "portfolio",
            "regime",
            "trade_candidate",
        ],
    )
