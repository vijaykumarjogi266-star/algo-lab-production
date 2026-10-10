"""
Unit & Integration Tests for the Single-Slice Gated Paper-Trading Path.
Conforms to Quality-First Plan:
- Phase 3: One Complete Paper-Trading Path (Page 9)
- Section 12: Test Strategy, Integration Layer (Page 17)
- Priorities 14.1: Gated Vertical Slice (Page 21)
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
import json
import os
import tempfile
import pytest

from services.market_data.adapters.market_event_schemas import (
    MarketTickEvent,
    MarketDataProvenance,
    DataSource,
    CollectionMode,
    FeedHealth,
    ExecutionMode,
    AccountingValidationStatus,
)
from services.market_data.adapters.market_pipeline import (
    MarketDataPipelineEngine,
    FoundationExecutionGate,
    CanonicalMarketDataBar,
)
from services.backtest_engine.statutory_cost_model import (
    IndianStatutoryCostModel,
    OrderLeg,
    ProductType,
)


def test_single_slice_foundation_gate_blocks_execution_by_default():
    """
    Plan Phase 3 & Section 2.3:
    Default fail-closed gate blocks strategy signals and orders when
    accounting validation or fresh streaming is unverified.
    """
    signals = []
    orders = []

    def mock_signal(bar: CanonicalMarketDataBar):
        signals.append(bar.symbol)
        return 1  # BUY

    def mock_executor(signal: int, bar: CanonicalMarketDataBar):
        orders.append((signal, bar.symbol))

    # Real unverified provenance baseline
    prov = MarketDataProvenance(
        data_source=DataSource.MOCK,
        collection_mode=CollectionMode.FORWARD,
        feed_health=FeedHealth.UNVERIFIED,
        execution_mode=ExecutionMode.PAPER,
        accounting_validation=AccountingValidationStatus.UNVALIDATED,
        real_connection_observed=False,
    )

    pipeline = MarketDataPipelineEngine(
        bar_interval_seconds=60,
        signal_generator=mock_signal,
        paper_executor=mock_executor,
        provenance=prov,
        allow_diagnostic_simulation=False,  # FAIL-CLOSED DEFAULT
    )

    t0 = datetime(2026, 9, 26, 9, 30, 0, tzinfo=timezone.utc)
    t1 = MarketTickEvent(
        symbol="SBIN",
        token="3045",
        exchange_timestamp=t0,
        receive_timestamp=t0,
        sequence_id=1,
        last_traded_price=820.0,
        last_traded_quantity=10,
        cumulative_volume=1000,
    )
    pipeline.process_tick(t1)

    t2 = MarketTickEvent(
        symbol="SBIN",
        token="3045",
        exchange_timestamp=t0 + timedelta(seconds=65),
        receive_timestamp=t0 + timedelta(seconds=65),
        sequence_id=2,
        last_traded_price=825.0,
        last_traded_quantity=10,
        cumulative_volume=1010,
    )
    bar = pipeline.process_tick(t2)

    # Bar is aggregated for observation
    assert bar is not None
    assert bar.symbol == "SBIN"
    assert bar.close == 820.0

    # NON-NEGOTIABLE INVARIANT: Zero signals emitted, zero orders executed
    assert len(signals) == 0
    assert len(orders) == 0
    assert pipeline.signals_emitted == 0


def test_single_slice_end_to_end_vertical_path_with_statutory_accounting():
    """
    Plan Phase 3:
    Full vertical slice: Tick -> Bar -> Signal -> Statutory Friction -> Double-Entry Ledger -> Reconcile.
    Uses allow_diagnostic_simulation=True for controlled slice verification.
    """
    ledger_state = {
        "account_id": "ACC-FORWARD-CANONICAL-100K-01",
        "cash": Decimal("100000.00"),
        "positions": {},
        "orders_executed": 0,
        "total_friction": Decimal("0.00"),
    }

    def breakout_signal(bar: CanonicalMarketDataBar) -> int:
        if bar.close > 822.0:
            return 1  # BUY
        return 0

    def simulated_executor(sig: int, bar: CanonicalMarketDataBar):
        price = Decimal(str(bar.close))
        qty = 10
        friction = IndianStatutoryCostModel.calculate_order_friction(
            leg=OrderLeg.BUY,
            price=price,
            quantity=qty,
            product=ProductType.INTRADAY,
        )
        total_cost = (price * Decimal(qty)) + friction.total_statutory_and_brokerage

        # Pre-trade cash solvency check
        assert ledger_state["cash"] >= total_cost

        # Double-entry posting
        ledger_state["cash"] -= total_cost
        ledger_state["positions"][bar.symbol] = {
            "quantity": qty,
            "entry_price": price,
            "cost_basis": price * Decimal(qty),
        }
        ledger_state["orders_executed"] += 1
        ledger_state["total_friction"] += friction.total_statutory_and_brokerage

    prov = MarketDataProvenance(
        data_source=DataSource.MOCK,
        collection_mode=CollectionMode.FORWARD,
        feed_health=FeedHealth.HEALTHY,
        execution_mode=ExecutionMode.PAPER,
        accounting_validation=AccountingValidationStatus.VERIFIED,
        real_connection_observed=True,
    )

    pipeline = MarketDataPipelineEngine(
        bar_interval_seconds=60,
        signal_generator=breakout_signal,
        paper_executor=simulated_executor,
        provenance=prov,
        allow_diagnostic_simulation=True,
    )

    t0 = datetime(2026, 9, 26, 9, 30, 0, tzinfo=timezone.utc)
    # Ticks inside the 09:30 minute: close at 825.0 (> 822.0 -> breakout!)
    for i, p in enumerate([820.0, 822.0, 824.0, 825.0]):
        tick = MarketTickEvent(
            symbol="SBIN",
            token="3045",
            exchange_timestamp=t0 + timedelta(seconds=i * 10),
            receive_timestamp=t0 + timedelta(seconds=i * 10),
            sequence_id=i + 1,
            last_traded_price=p,
            last_traded_quantity=10,
            cumulative_volume=1000 + (i + 1) * 10,
        )
        pipeline.process_tick(tick)

    # Next tick triggers bar closure and signal execution
    t1 = t0 + timedelta(seconds=65)
    tick_trigger = MarketTickEvent(
        symbol="SBIN",
        token="3045",
        exchange_timestamp=t1,
        receive_timestamp=t1,
        sequence_id=10,
        last_traded_price=826.0,
        last_traded_quantity=10,
        cumulative_volume=1050,
    )
    bar = pipeline.process_tick(tick_trigger)

    assert bar is not None
    assert bar.close == 825.0
    assert pipeline.signals_emitted == 1

    # Verify ledger state invariants
    assert ledger_state["orders_executed"] == 1
    assert "SBIN" in ledger_state["positions"]
    assert ledger_state["positions"]["SBIN"]["quantity"] == 10
    assert ledger_state["total_friction"] > Decimal("0.00")

    # Double-entry balance sheet conservation:
    # Cash + Position Cost Basis + Total Friction == Initial Capital
    reconstructed_capital = (
        ledger_state["cash"]
        + ledger_state["positions"]["SBIN"]["cost_basis"]
        + ledger_state["total_friction"]
    )
    assert reconstructed_capital == Decimal("100000.00")
