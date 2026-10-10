"""Adversarial Failure & Robustness Integration Tests.

Attacks system with:
- Duplicate ticks
- Missing/stale ticks
- Malformed messages / Pydantic validation errors
- Out-of-order sequence numbers
- Risk limit breaches (solvency & capital limits)
- Safety lock violation attempt
"""

from datetime import datetime, timezone, timedelta
import pytest

from services.backtest_engine.execution_lifecycle import OrderSide, OrderLifecycleState
from services.market_data.adapters.market_event_schemas import MarketTickEvent
from services.market_data.runner import RealTimeMarketDataRunner, DataSourceType
from services.orchestrator.session_orchestrator import SessionOrchestrator


def test_adversarial_duplicate_and_out_of_order_ticks():
    runner = RealTimeMarketDataRunner(
        source_type=DataSourceType.SIMULATED_MOCK,
        symbols=["SBIN"],
        bar_interval_seconds=60,
        allow_diagnostic_simulation=True,
    )

    t0 = datetime(2026, 9, 29, 9, 30, 0, tzinfo=timezone.utc)
    t1 = MarketTickEvent(
        symbol="SBIN", token="3045", exchange_timestamp=t0, receive_timestamp=t0, sequence_id=10, last_traded_price=820.0, last_traded_quantity=10, cumulative_volume=1000
    )
    # Duplicate tick (same sequence_id 10)
    t1_dup = MarketTickEvent(
        symbol="SBIN", token="3045", exchange_timestamp=t0, receive_timestamp=t0, sequence_id=10, last_traded_price=825.0, last_traded_quantity=10, cumulative_volume=1000
    )
    # Out of order tick (earlier sequence_id 5)
    t_old = MarketTickEvent(
        symbol="SBIN", token="3045", exchange_timestamp=t0 - timedelta(seconds=10), receive_timestamp=t0, sequence_id=5, last_traded_price=815.0, last_traded_quantity=10, cumulative_volume=1000
    )

    runner.inject_tick(t1)
    runner.inject_tick(t1_dup)
    runner.inject_tick(t_old)

    telemetry = runner.pipeline.get_pipeline_telemetry()
    assert telemetry["total_ticks_received"] == 3
    assert telemetry["duplicates_dropped"] == 2  # t1_dup and t_old (sequence_id <= 10 dropped)


def test_adversarial_malformed_tick_schema_rejection():
    runner = RealTimeMarketDataRunner(
        source_type=DataSourceType.SIMULATED_MOCK,
        symbols=["SBIN"],
        allow_diagnostic_simulation=True,
    )

    t0 = datetime(2026, 9, 29, 9, 30, 0, tzinfo=timezone.utc)
    # Malformed negative price rejected fail-closed by Pydantic schema validator
    with pytest.raises(ValueError):
        MarketTickEvent(
            symbol="SBIN", token="3045", exchange_timestamp=t0, receive_timestamp=t0, sequence_id=1, last_traded_price=-500.0, last_traded_quantity=10, cumulative_volume=1000
        )

    # Valid tick schema passes to pipeline
    t_valid = MarketTickEvent(
        symbol="SBIN", token="3045", exchange_timestamp=t0, receive_timestamp=t0, sequence_id=1, last_traded_price=820.0, last_traded_quantity=10, cumulative_volume=1000
    )
    runner.inject_tick(t_valid)
    assert runner.pipeline.valid_ticks_processed == 1


def test_adversarial_risk_rejection_zero_mutation():
    orchestrator = SessionOrchestrator(
        session_name="Risk_Rejection_Attack",
        initial_capital=100_000.0,
        allow_diagnostic_simulation=True,
    )
    orchestrator.initialize_session()
    orchestrator.start_market_session()

    session_id = orchestrator.session.session_id
    initial_cash = orchestrator.session.portfolio.cash

    # Submit order exceeding max trade capital (5% = 5,000 INR; 50,000 INR order proposed)
    order, fill = orchestrator.paper_engine.submit_manual_order(
        session_id=session_id,
        symbol="SBIN",
        side=OrderSide.BUY,
        quantity=100,
        price=500.0,
        stop_loss=490.0,
    )

    assert fill is None
    assert order.state == OrderLifecycleState.ORDER_REJECTED
    # NON-NEGOTIABLE INVARIANT: Cash must remain strictly UNMUTATED on rejection
    assert orchestrator.session.portfolio.cash == initial_cash
    assert "SBIN" not in orchestrator.session.portfolio.positions

    orchestrator.close_market_session()


def test_adversarial_safety_lock_breach_prevention():
    """Verify system fails closed if ALLOW_LIVE_TRADING is set to True."""
    from apps.api.core.config import settings
    original_flag = settings.ALLOW_LIVE_TRADING
    try:
        settings.ALLOW_LIVE_TRADING = True
        orchestrator = SessionOrchestrator(session_name="Safety_Breach_Test")
        with pytest.raises(PermissionError, match="SAFETY LOCK BREACH DETECTED"):
            orchestrator.initialize_session()
    finally:
        settings.ALLOW_LIVE_TRADING = original_flag
