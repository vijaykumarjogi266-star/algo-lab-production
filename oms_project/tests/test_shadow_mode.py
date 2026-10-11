"""
Unit & Integration Tests for Stage 6: Broker Read-Only Shadow Mode & Cross-Venue Reconciliation.

Validates:
1. Broker Read-Only State Ingestion:
   - Polls broker margins, cash balances, and positions without submitting orders.
   - Enforces read-only snapshot generation.
2. Cross-Venue Reconciliation:
   - Clean matching between internal OMS ledger and broker shadow snapshot.
   - Minor cash variance warning detection.
   - Position mismatch detection (flags extra/missing shares as MATERIAL_DRIFT).
   - Cash delta percentage threshold breach detection.
3. Fail-Closed Security Lockout:
   - Asserts LIVE_TRADING_ENABLED remains False.
   - Ensures no real order routing occurs.
"""

from datetime import datetime, timezone
import pytest

from oms_project.shadow_mode import (
    BrokerReadOnlyShadowEngine,
    BrokerShadowSnapshot,
    ReconciliationDriftReport,
    ShadowDriftSeverity,
)
from services.paper_engine.adapters.zerodha_basex import ZerodhaBaseXAdapter


def test_broker_shadow_snapshot_ingestion():
    adapter = ZerodhaBaseXAdapter(mock_mode=True)
    engine = BrokerReadOnlyShadowEngine(broker_name="zerodha", adapter=adapter)

    snap = engine.fetch_broker_shadow_state()
    assert snap.broker_name == "zerodha"
    assert snap.available_cash == 1_000_000.0
    assert snap.used_margin == 0.0
    assert snap.is_live_account is False
    assert snap.connection_health == "CONNECTED"


def test_reconciliation_clean_match():
    adapter = ZerodhaBaseXAdapter(mock_mode=True)
    engine = BrokerReadOnlyShadowEngine(broker_name="zerodha", adapter=adapter)

    # Internal state matches broker state exactly
    report = engine.reconcile_shadow_versus_internal(
        internal_cash=1_000_000.0,
        internal_positions={},
    )

    assert report.severity == ShadowDriftSeverity.CLEAN
    assert report.cash_delta == 0.0
    assert report.position_discrepancies == {}
    assert len(report.alerts) == 0


def test_reconciliation_minor_cash_variance():
    adapter = ZerodhaBaseXAdapter(mock_mode=True)
    engine = BrokerReadOnlyShadowEngine(broker_name="zerodha", adapter=adapter)

    # 10 INR minor rounding variance (< 2% tolerance)
    report = engine.reconcile_shadow_versus_internal(
        internal_cash=1_000_010.0,
        internal_positions={},
    )

    assert report.severity == ShadowDriftSeverity.WARNING
    assert report.cash_delta == 10.0
    assert any("MINOR_CASH_VARIANCE" in a for a in report.alerts)


def test_reconciliation_material_position_mismatch():
    adapter = ZerodhaBaseXAdapter(mock_mode=True)
    engine = BrokerReadOnlyShadowEngine(broker_name="zerodha", adapter=adapter)

    # Internal OMS thinks we have 100 INFY, but broker has 0
    report = engine.reconcile_shadow_versus_internal(
        internal_cash=1_000_000.0,
        internal_positions={"INFY": 100},
    )

    assert report.severity == ShadowDriftSeverity.MATERIAL_DRIFT
    assert report.position_discrepancies == {"INFY": 100}
    assert any("POSITION_MISMATCH" in a for a in report.alerts)


def test_reconciliation_large_cash_drift():
    adapter = ZerodhaBaseXAdapter(mock_mode=True)
    engine = BrokerReadOnlyShadowEngine(
        broker_name="zerodha",
        adapter=adapter,
        max_tolerable_cash_delta_pct=0.02, # 2% max
    )

    # Internal OMS cash is 900,000 vs broker 1,000,000 (10% variance > 2%)
    report = engine.reconcile_shadow_versus_internal(
        internal_cash=900_000.0,
        internal_positions={},
    )

    assert report.severity == ShadowDriftSeverity.MATERIAL_DRIFT
    assert report.cash_delta == -100_000.0
    assert any("CASH_DRIFT_EXCEEDED" in a for a in report.alerts)


def test_security_zero_live_order_routing():
    engine = BrokerReadOnlyShadowEngine()
    assert engine.assert_zero_live_order_routing() is True
