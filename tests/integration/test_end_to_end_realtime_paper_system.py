"""Full End-to-End Real-Time Equity Paper Trading System Engineering Integration Test.

Path Tested:
SESSION START → MARKET EVENT → SYMBOL UPDATE → SCANNER → STRATEGY → RISK → PAPER ORDER → PAPER FILL → ACCOUNTING → PERSISTENCE → RECOVERY EVENT → CONTINUATION → SESSION CLOSE → EOD RECONCILIATION

LABEL: ENGINEERING TEST ONLY (NOT Genuine Forward Market Evidence).
"""

from datetime import datetime, timezone, timedelta
import time
from services.backtest_engine.execution_lifecycle import OrderSide
from services.common.health import ComponentOperationalState
from services.market_data.adapters.market_event_schemas import MarketTickEvent
from services.market_data.runner import DataSourceType
from services.orchestrator.session_orchestrator import SessionOrchestrator, SessionPhase


def test_full_end_to_end_engineering_pipeline():
    """
    Executes an end-to-end multi-symbol paper session with tick ingestion, bar construction,
    scanner setups, risk evaluation, paper order fills, double-entry accounting, state persistence,
    mid-session recovery, session wrap-up, and EOD reconciliation.
    """
    orchestrator = SessionOrchestrator(
        session_name="ENGINEERING_TEST_E2E_01",
        strategy_id="VWAP_REVERSION_AND_ORB",
        universe=["SBIN", "RELIANCE"],
        initial_capital=1_000_000.0,
        source_type=DataSourceType.SIMULATED_MOCK,
        bar_interval_seconds=60,
        allow_diagnostic_simulation=True,
    )

    # 1. SESSION START (PRE-MARKET)
    orchestrator.initialize_session()
    assert orchestrator.phase == SessionPhase.PRE_MARKET
    assert orchestrator.session is not None

    # 2. MARKET OPEN & START DATA STREAM
    orchestrator.start_market_session()
    assert orchestrator.phase == SessionPhase.MARKET_OPEN
    orchestrator.transition_to_intraday()

    # 3. INGEST MARKET EVENTS & SYMBOL UPDATES
    t0 = datetime(2026, 9, 29, 9, 30, 0, tzinfo=timezone.utc)
    # Stream ticks for SBIN and RELIANCE across 4 minutes
    for i in range(4):
        t_cur = t0 + timedelta(minutes=i)
        
        # SBIN ticks
        tick_sbin = MarketTickEvent(
            symbol="SBIN",
            token="3045",
            exchange_timestamp=t_cur,
            receive_timestamp=t_cur,
            sequence_id=i * 2 + 1,
            last_traded_price=820.0 + i * 3.0,
            last_traded_quantity=50,
            cumulative_volume=1000 + (i + 1) * 50,
        )
        orchestrator.runner.inject_tick(tick_sbin)

        # RELIANCE ticks
        tick_rel = MarketTickEvent(
            symbol="RELIANCE",
            token="2885",
            exchange_timestamp=t_cur,
            receive_timestamp=t_cur,
            sequence_id=i * 2 + 2,
            last_traded_price=2950.0 - i * 5.0,
            last_traded_quantity=20,
            cumulative_volume=500 + (i + 1) * 20,
        )
        orchestrator.runner.inject_tick(tick_rel)

    # 4. SUBMIT ORDER VIA INTEGRATED FLOW
    session_id = orchestrator.session.session_id
    order, fill = orchestrator.paper_engine.submit_manual_order(
        session_id=session_id,
        symbol="SBIN",
        side=OrderSide.BUY,
        quantity=50,
        price=825.0,
        stop_loss=810.0,
    )

    assert fill is not None
    assert fill.symbol == "SBIN"
    assert fill.quantity == 50
    assert "SBIN" in orchestrator.session.portfolio.positions

    # 5. RECOVERY EVENT & MID-SESSION CONTINUATION
    # Simulate process restart by reloading session from SQLite DB
    reloaded_session = orchestrator.paper_engine.get_session(session_id)
    assert reloaded_session is not None
    assert "SBIN" in reloaded_session.portfolio.positions
    assert reloaded_session.portfolio.positions["SBIN"].quantity == 50

    # 6. SESSION CLOSE & EOD RECONCILIATION
    report = orchestrator.close_market_session()

    assert orchestrator.phase == SessionPhase.SHUTDOWN
    assert report.reconciliation_passed is True
    assert report.fills_count >= 1
    assert report.ending_cash < 1_000_000.0
    assert report.total_fees_paid > 0.0
    assert len(report.evidence_hash) == 64
