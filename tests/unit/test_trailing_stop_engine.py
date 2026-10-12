"""
Unit tests for Algo Lab Real-Time Automated Tick Monitoring & Trailing Stop Engine.
"""

from datetime import datetime, time
import pytest
import zoneinfo

from services.backtest_engine.contracts import OrderSide
from services.paper_engine.session import PaperTradingEngine, SessionStatus
from services.paper_engine.trailing_stop_engine import (
    TrailingStopEngine,
    PositionGuardState,
    TrailingPositionConfig,
    FrozenClock,
    IST_TZ,
)

# Standard market-hours frozen clock (10:30:00 IST)
FROZEN_MARKET_TIME = datetime(2026, 10, 12, 10, 30, 0, tzinfo=IST_TZ)


@pytest.fixture
def market_hours_clock():
    return FrozenClock(FROZEN_MARKET_TIME)


@pytest.fixture
def test_engine_and_session(tmp_path):
    db_file = str(tmp_path / "test_paper.db")
    engine = PaperTradingEngine(db_file)
    session = engine.create_session(
        name="TEST_TRAILING_SESSION",
        strategy_id="TEST_ORB",
        universe=["EICHERMOT", "TRENT"],
        initial_capital=200000.0,
    )
    engine.start_session(session.session_id)

    # Buy EICHERMOT: 1 qty @ 7000.0 with mandatory stop_loss (within 10k trade cap)
    engine.submit_manual_order(
        session_id=session.session_id,
        symbol="EICHERMOT",
        side=OrderSide.BUY,
        quantity=1,
        price=7000.0,
        stop_loss=6800.0,
    )
    return engine, session.session_id


def test_guard_state_initialization():
    guard = PositionGuardState.create(
        symbol="EICHERMOT",
        quantity=2,
        entry_price=7000.0,
        side=OrderSide.BUY,
        config=TrailingPositionConfig(
            symbol="EICHERMOT",
            stop_loss_pct=0.02,     # 2% SL -> 6860.0
            target_pct=0.04,        # 4% Target -> 7280.0
            trailing_distance_pct=0.01,
            breakeven_trigger_pct=0.01,
        )
    )

    assert guard.symbol == "EICHERMOT"
    assert guard.stop_loss == 6860.0
    assert guard.target_price == 7280.0
    assert guard.highest_watermark == 7000.0
    assert not guard.breakeven_locked
    assert not guard.is_closed


def test_breakeven_lock_and_ratchet_upward(market_hours_clock):
    guard = PositionGuardState.create(
        symbol="EICHERMOT",
        quantity=2,
        entry_price=7000.0,
        side=OrderSide.BUY,
        config=TrailingPositionConfig(
            symbol="EICHERMOT",
            stop_loss_pct=0.02,           # SL: 6860.0
            target_pct=0.10,              # 10% target so 7250 doesn't exit on target
            breakeven_trigger_pct=0.01,   # +1% = 7070.0
            trailing_distance_pct=0.01,   # 1% trail
            ratchet_step_pct=0.005,       # 0.5% min step = 35.0
        )
    )

    # 1. Price moves to 7050 (+0.7%, below breakeven trigger)
    should_exit, reason = guard.evaluate_tick(7050.0, clock=market_hours_clock)
    assert not should_exit
    assert not guard.breakeven_locked
    assert guard.highest_watermark == 7050.0

    # 2. Price touches 7100 (+1.43% > 1% breakeven trigger)
    should_exit, reason = guard.evaluate_tick(7100.0, clock=market_hours_clock)
    assert not should_exit
    assert guard.breakeven_locked
    assert guard.stop_loss >= 7000.0  # Locked to at least entry!

    # 3. Price peaks at 7300 (+4.28%)
    # Candidate trail: 7300 * 0.99 = 7227.0
    should_exit, reason = guard.evaluate_tick(7300.0, clock=market_hours_clock)
    assert not should_exit
    assert guard.stop_loss == 7227.0

    # 4. Price dips to 7250 (stop loss must NEVER ratchet down)
    should_exit, reason = guard.evaluate_tick(7250.0, clock=market_hours_clock)
    assert not should_exit
    assert guard.stop_loss == 7227.0  # Invariant: stop loss ratchets only up!


def test_trailing_stop_loss_exit(market_hours_clock):
    guard = PositionGuardState.create(
        symbol="EICHERMOT",
        quantity=2,
        entry_price=7000.0,
        side=OrderSide.BUY,
        config=TrailingPositionConfig(
            symbol="EICHERMOT",
            stop_loss_pct=0.02,
            trailing_distance_pct=0.01,
            ratchet_step_pct=0.005,
        )
    )

    # Ratchet high to 7200 -> SL becomes 7200 * 0.99 = 7128.0
    guard.evaluate_tick(7200.0, clock=market_hours_clock)
    assert guard.stop_loss == 7128.0

    # Tick falls below 7128 -> Exit
    should_exit, reason = guard.evaluate_tick(7120.0, clock=market_hours_clock)
    assert should_exit
    assert reason == "TRAILING_STOP_LOSS_HIT"


def test_profit_target_exit(market_hours_clock):
    guard = PositionGuardState.create(
        symbol="EICHERMOT",
        quantity=2,
        entry_price=7000.0,
        side=OrderSide.BUY,
        target_price=7250.0,
    )

    should_exit, reason = guard.evaluate_tick(7250.0, clock=market_hours_clock)
    assert should_exit
    assert reason == "PROFIT_TARGET_HIT"


def test_mandatory_1515_ist_auto_square_off():
    guard = PositionGuardState.create(
        symbol="EICHERMOT",
        quantity=2,
        entry_price=7000.0,
        side=OrderSide.BUY,
    )

    # Time before 15:15 IST (e.g. 14:30)
    t_before = datetime(2026, 10, 12, 14, 30, 0, tzinfo=IST_TZ)
    should_exit, reason = guard.evaluate_tick(7010.0, current_time_ist=t_before)
    assert not should_exit

    # Time at 15:15:01 IST
    t_after = datetime(2026, 10, 12, 15, 15, 1, tzinfo=IST_TZ)
    should_exit, reason = guard.evaluate_tick(7010.0, current_time_ist=t_after)
    assert should_exit
    assert reason == "AUTO_SQUARE_OFF_1515_IST"


def test_trailing_stop_engine_execution_and_session_persistence(test_engine_and_session, market_hours_clock):
    paper_engine, session_id = test_engine_and_session
    trailing_engine = TrailingStopEngine(paper_engine, session_id, clock=market_hours_clock)

    # Guard should be synced for EICHERMOT
    guard = trailing_engine.get_guard("EICHERMOT")
    assert guard is not None
    assert guard.quantity == 1
    assert abs(guard.entry_price - 7000.0) < 10.0  # Execution with slippage

    # Process tick that ratchets price up
    r1 = trailing_engine.process_tick("EICHERMOT", 7150.0)
    assert r1["status"] == "ACTIVE_MONITORING"
    assert r1["ltp"] == 7150.0

    # Process tick that hits target
    guard.target_price = 7200.0
    r2 = trailing_engine.process_tick("EICHERMOT", 7200.0)
    assert r2["status"] == "EXECUTED_EXIT"
    assert r2["exit_reason"] == "PROFIT_TARGET_HIT"
    assert r2["quantity"] == 1

    # Verify session in DB: Position should now be closed!
    updated_session = paper_engine.get_session(session_id)
    assert "EICHERMOT" not in updated_session.portfolio.positions
    assert updated_session.portfolio.total_realized_pnl > 0.0


def test_concurrent_ticks_single_exit(test_engine_and_session, market_hours_clock):
    """Guarantees thread-safety: concurrent ticks attempting to exit fire exactly 1 order."""
    import concurrent.futures
    paper_engine, session_id = test_engine_and_session
    trailing_engine = TrailingStopEngine(paper_engine, session_id, clock=market_hours_clock)

    # 10 threads concurrently sending exit-triggering tick (6500 <= initial stop loss 6895)
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(trailing_engine.process_tick, "EICHERMOT", 6500.0) for _ in range(10)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    executed_exits = [r for r in results if r.get("status") == "EXECUTED_EXIT"]
    ignored_exits = [r for r in results if r.get("status") == "IGNORED"]

    assert len(executed_exits) == 1, f"Expected exactly 1 EXECUTED_EXIT, got {len(executed_exits)}"
    assert len(ignored_exits) == 9

    # Verify session only executed 1 fill for exit
    updated_session = paper_engine.get_session(session_id)
    assert "EICHERMOT" not in updated_session.portfolio.positions
    # 1 buy fill + 1 sell fill = 2 fills total
    assert len(updated_session.fills) == 2


def test_exit_risk_rejection_safety(test_engine_and_session, market_hours_clock):
    """Guarantees that risk rejections do NOT drop monitoring or mark guard as closed."""
    from unittest.mock import MagicMock
    from services.backtest_engine.execution_lifecycle import OrderLifecycleState

    paper_engine, session_id = test_engine_and_session
    trailing_engine = TrailingStopEngine(paper_engine, session_id, clock=market_hours_clock)

    # Mock manual order submission returning a rejected order (fill=None)
    mock_rejected = MagicMock()
    mock_rejected.order_id = "rej_test_1"
    mock_rejected.state = OrderLifecycleState.ORDER_REJECTED
    mock_rejected.rejection_reason = "Solvency limit breached in test"
    paper_engine.submit_manual_order = MagicMock(return_value=(mock_rejected, None))

    res = trailing_engine.process_tick("EICHERMOT", 6500.0)
    assert res["status"] == "EXIT_REJECTED"
    assert res["rejection_reason"] == "Solvency limit breached in test"

    guard = trailing_engine.get_guard("EICHERMOT")
    assert guard is not None
    assert not guard.is_closed, "Guard must remain open to protect position after rejection"


def test_short_position_ratchet_and_watermark_sync(tmp_path, market_hours_clock):
    """Guarantees short positions track lowest watermark and ratchet trailing stops downward."""
    db_file = str(tmp_path / "test_short.db")
    engine = PaperTradingEngine(db_file)
    session = engine.create_session(
        name="TEST_SHORT_SESSION",
        strategy_id="TEST_SHORT",
        universe=["TRENT"],
        initial_capital=200000.0,
    )
    engine.start_session(session.session_id)

    trailing_engine = TrailingStopEngine(engine, session.session_id, clock=market_hours_clock)
    # Register short guard directly in engine
    trailing_engine.guards["TRENT"] = PositionGuardState.create(
        symbol="TRENT",
        quantity=2,
        entry_price=3000.0,
        side=OrderSide.SELL,
        config=TrailingPositionConfig(
            symbol="TRENT",
            stop_loss_pct=0.02,          # SL: 3060.0
            breakeven_trigger_pct=0.01,  # 1% drop -> BE lock at 3000.0
            trailing_distance_pct=0.01,  # 1% trail
            ratchet_step_pct=0.005,      # 0.5% ratchet step
        ),
    )

    guard = trailing_engine.get_guard("TRENT")
    assert guard is not None
    assert guard.side == OrderSide.SELL
    assert guard.lowest_watermark <= 3000.0

    # 1. Price drops to 2960 (-1.33% > 1% breakeven trigger)
    should_exit, _ = guard.evaluate_tick(2960.0, clock=market_hours_clock)
    assert not should_exit
    assert guard.breakeven_locked
    assert guard.stop_loss <= 3000.0

    # 2. Price drops further to 2900 (-3.33%)
    # Candidate trail: 2900 * 1.01 = 2929.0
    should_exit, _ = guard.evaluate_tick(2900.0, clock=market_hours_clock)
    assert not should_exit
    assert guard.lowest_watermark == 2900.0
    assert guard.stop_loss == 2929.0

    # 3. Pullback up touches trailing stop -> Exit
    should_exit, reason = guard.evaluate_tick(2930.0, clock=market_hours_clock)
    assert should_exit
    assert reason == "TRAILING_STOP_LOSS_HIT"


def test_external_session_closure_synchronization(test_engine_and_session):
    """Guarantees guards recognize external position square-offs and stop processing ticks."""
    paper_engine, session_id = test_engine_and_session
    trailing_engine = TrailingStopEngine(paper_engine, session_id)

    # Close position directly in paper engine
    paper_engine.submit_manual_order(
        session_id=session_id,
        symbol="EICHERMOT",
        side=OrderSide.SELL,
        quantity=1,
        price=7000.0,
        stop_loss=7200.0,
    )

    # Resync
    trailing_engine.sync_from_session()
    guard = trailing_engine.get_guard("EICHERMOT")
    assert guard.is_closed
    assert guard.exit_reason == "CLOSED_EXTERNALLY"

    # Subsequent tick must be ignored
    res = trailing_engine.process_tick("EICHERMOT", 7100.0)
    assert res["status"] == "IGNORED"
