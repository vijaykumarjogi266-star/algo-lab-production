"""Unit Tests for EOD Reconciliation Engine (Work Package C)."""

from services.backtest_engine.execution_lifecycle import OrderSide
from services.paper_engine.session import PaperTradingEngine
from services.reconciliation.eod import EODReconciler


def test_eod_reconciler_clean_session_pass():
    engine = PaperTradingEngine(db_path=":memory:")
    session = engine.create_session(
        name="Test_EOD_Pass",
        strategy_id="VWAP_REVERSION",
        universe=["SBIN"],
        initial_capital=100_000.0,
    )
    engine.start_session(session.session_id)

    # Submit BUY order and fill
    engine.submit_manual_order(
        session_id=session.session_id,
        symbol="SBIN",
        side=OrderSide.BUY,
        quantity=5,
        price=820.0,
        stop_loss=800.0,
    )

    reconciler = EODReconciler()
    report = reconciler.reconcile_session(session)

    assert report.reconciliation_passed is True
    assert len(report.reconciliation_discrepancies) == 0
    assert report.orders_proposed == 1
    assert report.fills_count == 1
    assert report.positions_cost_basis == 4102.3
    assert len(report.evidence_hash) == 64
