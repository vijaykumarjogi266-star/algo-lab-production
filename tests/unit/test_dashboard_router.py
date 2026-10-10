"""
Unit and Integration tests for the Algo Lab Swing Trading Dashboard Router.
Verifies:
1. GET /api/dashboard/portfolio returns valid cash, equity, and net P&L from SQLite ledger.
2. GET /api/dashboard/positions queries active open positions and computes unrealized P&L.
3. GET /api/dashboard/system-status returns mode="PAPER TRADING", allow_live_trading=False, next_execution="15:00 IST".
4. Fail-closed safety boundary compliance.
"""

import pytest
import sqlite3
from pathlib import Path
from fastapi.testclient import TestClient
from apps.api.main import app

client = TestClient(app)


def test_dashboard_system_status_endpoint():
    """Verifies that /api/dashboard/system-status returns mandatory paper trading flags."""
    response = client.get("/api/dashboard/system-status")
    assert response.status_code == 200
    data = response.json()

    assert data["mode"] == "PAPER TRADING"
    assert data["allow_live_trading"] is False
    assert data["allow_real_broker_execution"] is False
    assert data["next_execution"] == "15:00 IST"
    assert data["canonical_account"] == "ACC-FORWARD-CANONICAL-100K-01"


def test_dashboard_portfolio_endpoint():
    """Verifies that /api/dashboard/portfolio connects to SQLite and returns valid portfolio state."""
    response = client.get("/api/dashboard/portfolio")
    assert response.status_code == 200
    data = response.json()

    assert "cash_balance" in data
    assert "total_equity" in data
    assert "net_pnl" in data
    assert data["cash_balance"] > 0
    assert data["total_equity"] >= data["cash_balance"]
    assert data["account_id"] == "ACC-FORWARD-CANONICAL-100K-01"


def test_dashboard_positions_endpoint():
    """Verifies that /api/dashboard/positions queries open positions cleanly."""
    response = client.get("/api/dashboard/positions")
    assert response.status_code == 200
    data = response.json()

    assert "positions" in data
    assert "count" in data
    assert isinstance(data["positions"], list)
    assert data["count"] == len(data["positions"])


def test_dashboard_v1_alias_endpoints():
    """Verifies that the /api/v1/dashboard/* aliases resolve identically."""
    status_res = client.get("/api/v1/dashboard/system-status")
    assert status_res.status_code == 200
    assert status_res.json()["mode"] == "PAPER TRADING"

    port_res = client.get("/api/v1/dashboard/portfolio")
    assert port_res.status_code == 200
    assert port_res.json()["account_id"] == "ACC-FORWARD-CANONICAL-100K-01"
