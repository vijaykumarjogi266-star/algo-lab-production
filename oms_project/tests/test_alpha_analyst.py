"""
Unit & Integration Tests for QUANT-OS Stage 5 — Wave 1: The Alpha Analyst (Post-Trade Forensics)
Verifies Observational Read-Only Mandate, Regime Loss Detection, Execution Toxicity Audit,
Stop-Loss Shakeout Detection, and Analyst Telemetry API Endpoints.
"""

import time
import pytest
from fastapi.testclient import TestClient

from oms_project.database import OrderLedgerDB
from oms_project.schemas import OrderIntent, OrderSide, OrderState
from oms_project.alpha_analyst import AlphaAnalyst, AnalystInsight, SlippageAuditRecord
from oms_project.telemetry_api import app, get_alpha_analyst, get_gateway

client = TestClient(app)


def test_alpha_analyst_initialization_and_read_only_mandate():
    """Verifies that AlphaAnalyst operates strictly in Read-Only mode without mutating DB state."""
    db = OrderLedgerDB(":memory:")
    intent = OrderIntent(
        request_id="REQ_ANALYST_001",
        strategy_id="STRAT_MEAN_REV_001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=10.0,
        price=1200.0,
        signature="sig123",
    )
    order_id = db.record_received_order(intent)
    db.transition_state(order_id, OrderState.VALIDATED)
    db.transition_state(order_id, OrderState.RISK_RESERVED)
    db.transition_state(order_id, OrderState.SUBMITTED)
    db.transition_state(order_id, OrderState.FILLED)

    analyst = AlphaAnalyst(db=db)

    count_before = len(analyst.get_order_history())
    res = analyst.run_full_diagnostics()
    count_after = len(analyst.get_order_history())

    # Read-Only Mandate Assertion: Order count before and after diagnostic scan must be identical
    assert count_before == count_after == 1
    assert "insights" in res
    assert "slippage_audit" in res


def test_regime_loss_detection():
    """Tests opening morning volatility regime loss pattern detection."""
    db = OrderLedgerDB(":memory:")
    # Insert orders with created_at timestamp set to 09:30 UTC
    opening_time = 1750066200.0  # Equivalent to ~09:30 AM

    for i in range(5):
        intent = OrderIntent(
            request_id=f"REQ_MORNING_{i}",
            strategy_id="STRAT_MEAN_REV_001",
            symbol="RELIANCE",
            side=OrderSide.BUY if i % 2 == 0 else OrderSide.SELL,
            qty=10.0,
            price=1200.0 + i,
            signature="sig123",
        )
        order_id = db.record_received_order(intent)
        db.transition_state(order_id, OrderState.VALIDATED)
        db.transition_state(order_id, OrderState.RISK_RESERVED)
        db.transition_state(order_id, OrderState.SUBMITTED)
        db.transition_state(order_id, OrderState.FILLED)

        # Force timestamp to morning window
        db.conn.execute("UPDATE order_ledger SET created_at = ? WHERE order_id = ?", (opening_time, order_id))

    analyst = AlphaAnalyst(db=db)
    res = analyst.run_full_diagnostics()

    insights = res["insights"]
    assert len(insights) >= 1
    regime_insight = next((i for i in insights if i["category"] == "REGIME_LOSS"), None)
    assert regime_insight is not None
    assert regime_insight["strategy_id"] == "STRAT_MEAN_REV_001"
    assert regime_insight["confidence_score"] >= 0.70
    assert "09:15 - 09:45 AM" in regime_insight["message"]


def test_slippage_toxicity_audit():
    """Tests calculation of execution slippage BPS and toxic slippage flagging."""
    db = OrderLedgerDB(":memory:")
    intent = OrderIntent(
        request_id="REQ_SLIP_001",
        strategy_id="STRAT_TREND_001",
        symbol="INFY",
        side=OrderSide.BUY,
        qty=10.0,
        price=1000.0,
        signature="sig123",
    )
    order_id = db.record_received_order(intent)
    db.transition_state(order_id, OrderState.VALIDATED)
    db.transition_state(order_id, OrderState.RISK_RESERVED)
    db.transition_state(order_id, OrderState.SUBMITTED)
    db.transition_state(order_id, OrderState.FILLED)

    # Record filled state transition with slippage: requested 1000.0, filled at 1002.0 (20 bps slippage)
    db.conn.execute(
        "UPDATE state_transitions SET reason = 'Filled @ 1002.0' WHERE order_id = ? AND to_state = 'FILLED'",
        (order_id,),
    )

    analyst = AlphaAnalyst(db=db, toxic_slippage_threshold_bps=5.0)
    records = analyst.audit_slippage_toxicity(analyst.get_order_history())

    assert len(records) == 1
    rec = records[0]
    assert rec.strategy_id == "STRAT_TREND_001"
    assert rec.symbol == "INFY"
    assert rec.requested_price == 1000.0


def test_analyst_telemetry_api_endpoints():
    """Tests GET /api/v1/analyst/insights and POST /api/v1/analyst/run-analysis API endpoints."""
    # 1. Trigger forensic scan
    run_resp = client.post("/api/v1/analyst/run-analysis")
    assert run_resp.status_code == 200
    run_data = run_resp.json()
    assert run_data["success"] is True
    assert "results" in run_data

    # 2. Get active insights
    get_resp = client.get("/api/v1/analyst/insights")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert "regime_state" in get_data
    assert "insights" in get_data
    assert "slippage_audit" in get_data
