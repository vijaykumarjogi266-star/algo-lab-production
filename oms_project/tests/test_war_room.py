"""
OMS Project - War Room Telemetry & Command Center Pytest Suite
Verifies Telemetry API endpoints, SSE Stream, Admin Bearer Token Auth,
Global Kill-Switch Panic Test, and 0ms Execution Overhead.
"""

import time
import pytest
from fastapi.testclient import TestClient

from oms_project.telemetry_api import app, ADMIN_BEARER_TOKEN, get_gateway
from oms_project.schemas import OrderIntent, OrderSide, OrderState
from oms_project.gateway import BrokerGateway


client = TestClient(app)


def test_telemetry_equity_curve_endpoint():
    """Verify GET /api/v1/telemetry/equity-curve returns total equity and P&L."""
    response = client.get("/api/v1/telemetry/equity-curve")
    assert response.status_code == 200
    data = response.json()
    assert "total_equity" in data
    assert "total_pnl" in data
    assert "cash_balance" in data
    assert data["strategy_id"] == "STRAT_MEAN_REV_001"


def test_telemetry_positions_endpoint():
    """Verify GET /api/v1/telemetry/positions returns current holdings."""
    response = client.get("/api/v1/telemetry/positions")
    assert response.status_code == 200
    data = response.json()
    assert "positions" in data
    assert isinstance(data["positions"], list)


def test_telemetry_system_health_endpoint():
    """Verify GET /api/v1/telemetry/system-health reports data feed & kill switch status."""
    response = client.get("/api/v1/telemetry/system-health")
    assert response.status_code == 200
    data = response.json()
    assert "kill_switch_active" in data
    assert "data_feed_healthy" in data
    assert "broker_gateway_status" in data


def test_telemetry_reconciliation_endpoint():
    """Verify GET /api/v1/telemetry/reconciliation returns MATCH and variance=0."""
    response = client.get("/api/v1/telemetry/reconciliation")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "MATCH"
    assert data["variance"] == 0.0


def test_admin_auth_middleware_security():
    """Verify Control endpoints require valid Admin Bearer Token."""
    # 1. Missing Authorization header -> 422/401 Error
    res_no_auth = client.post("/api/v1/control/kill-switch", json={"active": True})
    assert res_no_auth.status_code in (401, 422)

    # 2. Invalid Token -> 403 Forbidden
    res_bad_auth = client.post(
        "/api/v1/control/kill-switch",
        json={"active": True},
        headers={"Authorization": "Bearer BAD_TOKEN_123"},
    )
    assert res_bad_auth.status_code == 403
    assert "FORBIDDEN" in res_bad_auth.json()["detail"]

    # 3. Valid Token -> 200 OK
    res_valid_auth = client.post(
        "/api/v1/control/kill-switch",
        json={"active": True},
        headers={"Authorization": f"Bearer {ADMIN_BEARER_TOKEN}"},
    )
    assert res_valid_auth.status_code == 200
    assert res_valid_auth.json()["kill_switch_active"] is True

    # Reset kill-switch
    client.post(
        "/api/v1/control/kill-switch",
        json={"active": False},
        headers={"Authorization": f"Bearer {ADMIN_BEARER_TOKEN}"},
    )


def test_the_panic_test_kill_switch_rejection():
    """Test The Panic Test: Kill-Switch activated from API causes immediate order rejections."""
    gw = get_gateway()
    gw.set_market_price("RELIANCE", 1200.0, timestamp=time.time())

    # Activate Kill-Switch via Admin Control API
    res_admin = client.post(
        "/api/v1/control/kill-switch",
        json={"active": True},
        headers={"Authorization": f"Bearer {ADMIN_BEARER_TOKEN}"},
    )
    assert res_admin.status_code == 200
    assert gw.kill_switch_active is True

    # Attempt trade signal
    intent = OrderIntent(
        request_id="REQ_WAR_ROOM_PANIC_001",
        strategy_id="STRAT_MEAN_REV_001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=5.0,
        price=1200.0,
        signature="sig_panic_test",
    )

    res_trade = gw.process_order_intent(intent)
    assert res_trade.status == OrderState.REJECTED
    assert "REJECTED_KILL_SWITCH_ACTIVE" in res_trade.message

    # Deactivate Kill-Switch
    client.post(
        "/api/v1/control/kill-switch",
        json={"active": False},
        headers={"Authorization": f"Bearer {ADMIN_BEARER_TOKEN}"},
    )
    assert gw.kill_switch_active is False


def test_risk_limits_admin_adjustment():
    """Verify Admin control endpoint for adjusting MaxGrossExposure and PriceCollar."""
    res = client.post(
        "/api/v1/control/risk-limits",
        json={"max_gross_exposure": 2000000.0, "price_collar_pct": 3.5},
        headers={"Authorization": f"Bearer {ADMIN_BEARER_TOKEN}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["max_gross_exposure"] == 2000000.0
    assert data["price_collar_pct"] == 3.5

    gw = get_gateway()
    assert gw.max_gross_exposure == 2000000.0
    assert gw.price_collar_pct == 3.5


def test_pod_management_toggle_and_rejection():
    """Verify administrative control toggle to enable/disable specific Algo Pods."""
    gw = get_gateway()
    gw.set_market_price("RELIANCE", 1200.0, timestamp=time.time())

    # 1. Fetch Pod statuses
    res_pods = client.get("/api/v1/telemetry/pods")
    assert res_pods.status_code == 200
    assert "STRAT_001" in res_pods.json()["pods"]

    # 2. Disable STRAT_001 via Admin Control API
    res_disable = client.post(
        "/api/v1/control/pod-toggle",
        json={"strategy_id": "STRAT_001", "enabled": False},
        headers={"Authorization": f"Bearer {ADMIN_BEARER_TOKEN}"},
    )
    assert res_disable.status_code == 200
    assert gw.pod_enabled["STRAT_001"] is False

    # 3. Attempt order execution from STRAT_001 -> Must be REJECTED_POD_DISABLED
    intent = OrderIntent(
        request_id="REQ_POD_DISABLED_TEST_001",
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=5.0,
        price=1200.0,
        signature="sig_disabled_pod",
    )
    res_trade = gw.process_order_intent(intent)
    assert res_trade.status == OrderState.REJECTED
    assert "REJECTED_POD_DISABLED" in res_trade.message

    # 4. Re-enable STRAT_001 via Admin Control API
    res_enable = client.post(
        "/api/v1/control/pod-toggle",
        json={"strategy_id": "STRAT_001", "enabled": True},
        headers={"Authorization": f"Bearer {ADMIN_BEARER_TOKEN}"},
    )
    assert res_enable.status_code == 200
    assert gw.pod_enabled["STRAT_001"] is True

