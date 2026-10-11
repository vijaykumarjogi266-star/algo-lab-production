"""
OMS Project - Stage 2: Deterministic Historical Replay & Market-Regime Evaluation Tests
(test_deterministic_replay.py)

Comprehensive verification for:
1. ReplayClock monotonicity and session/calendar awareness.
2. Strict look-ahead bias prevention (LookAheadBiasError).
3. Multi-symbol chronological event stream synchronization.
4. Market regime classification across trend, range, volatility, liquidity, session window, and degraded data.
5. Regime-aware strategy decision gating.
6. End-to-end replay from verified dataset to durable execution report in database.
7. Bit-for-bit mathematical determinism proof across repeated runs.
8. Tampered dataset fail-closed quarantine before replay execution.
"""

import os
import csv
import json
import math
import time
import uuid
import tempfile
import sqlite3
from decimal import Decimal
from datetime import datetime, timezone, time as dt_time
import pytest
from zoneinfo import ZoneInfo

from oms_project.database import OrderLedgerDB
from oms_project.data_registry import (
    HistoricalDataRegistry,
    ChecksumMismatchError,
    DataQualityValidationError,
    DatasetQuarantinedError,
)
from oms_project.calendar_service import NSECalendarService, IST_TZ
from oms_project.deterministic_replay import (
    ReplayClock,
    ReplayClockMonotonicityError,
    LookAheadBiasError,
    BoundedEventStream,
    MarketRegime,
    RegimeEvaluator,
    ReplayExecutionEngine,
)
from oms_project.strategies.mean_reversion.mean_reversion_strat import MeanReversionStrategy


@pytest.fixture
def test_db(tmp_path):
    db_file = str(tmp_path / "test_stage2_replay.db")
    db = OrderLedgerDB(db_path=db_file)
    return db


def _create_sample_csv(rows, tmp_path=None):
    if tmp_path:
        csv_file = str(tmp_path / f"test_{uuid.uuid4().hex[:8]}.csv")
    else:
        fd, csv_file = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
    with open(csv_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["symbol", "price", "volume", "timestamp"])
        writer.writeheader()
        writer.writerows(rows)
    return csv_file


def test_replay_clock_monotonicity_and_session_awareness():
    """Verify ReplayClock advances monotonically and enforces Indian market session boundaries."""
    # 2026-03-24 09:20:00 IST = Tuesday (trading day)
    ist_dt = datetime(2026, 3, 24, 9, 20, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    t0 = ist_dt.timestamp()

    clock = ReplayClock(initial_time=t0, tz_name="Asia/Kolkata")
    assert clock.current_time == t0
    assert clock.is_regular_session() is True
    assert clock.is_opening_or_closing_window() is True  # 09:20 is in 09:15-09:30 opening window

    # Advancing forward works
    t1 = t0 + 60.0
    clock.advance_to(t1)
    assert clock.current_time == t1

    # Moving backwards raises ReplayClockMonotonicityError
    with pytest.raises(ReplayClockMonotonicityError) as exc_info:
        clock.advance_to(t0 - 10.0)
    assert "Clock cannot move backwards" in str(exc_info.value)

    # 11:00 IST -> regular session, but not opening or closing window
    clock.advance_to(datetime(2026, 3, 24, 11, 0, 0, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp())
    assert clock.is_regular_session() is True
    assert clock.is_opening_or_closing_window() is False

    # 15:20 IST -> regular session and in closing window (15:15 - 15:30)
    clock.advance_to(datetime(2026, 3, 24, 15, 20, 0, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp())
    assert clock.is_regular_session() is True
    assert clock.is_opening_or_closing_window() is True

    # 16:00 IST -> outside regular session
    clock.advance_to(datetime(2026, 3, 24, 16, 0, 0, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp())
    assert clock.is_regular_session() is False


def test_strict_look_ahead_bias_prevention():
    """Verify that BoundedEventStream strictly prevents any look-ahead leakage."""
    clock = ReplayClock(initial_time=1000.0)
    stream = BoundedEventStream(clock=clock)

    events = [
        {"symbol": "TCS", "price": 3500.0, "volume": 100, "timestamp": 1000.0},
        {"symbol": "TCS", "price": 3505.0, "volume": 150, "timestamp": 1001.0},
        {"symbol": "TCS", "price": 3510.0, "volume": 120, "timestamp": 1002.0},
        {"symbol": "TCS", "price": 3515.0, "volume": 130, "timestamp": 1003.0},
    ]
    stream.load_events(events)

    # Process first two events: clock advances to 1001.0
    ev1 = stream.next_event()
    assert ev1["timestamp"] == 1000.0
    ev2 = stream.next_event()
    assert ev2["timestamp"] == 1001.0
    assert clock.current_time == 1001.0

    # Querying history up to current clock succeeds
    hist = stream.get_history(symbol="TCS")
    assert len(hist) == 2
    assert [e["timestamp"] for e in hist] == [1000.0, 1001.0]

    # Querying future data (e.g. end = 1002.0) must raise LookAheadBiasError
    with pytest.raises(LookAheadBiasError) as exc_info:
        stream.get_history(symbol="TCS", end=1002.0)
    assert "Look-ahead violation" in str(exc_info.value)

    # Calling peek_future must immediately raise LookAheadBiasError
    with pytest.raises(LookAheadBiasError) as exc_info2:
        stream.peek_future(delta_seconds=1.0)
    assert "Future peeking is prohibited" in str(exc_info2.value)


def test_multi_symbol_synchronization():
    """Verify multi-symbol events are ordered strictly by (timestamp, symbol)."""
    clock = ReplayClock(initial_time=1000.0)
    stream = BoundedEventStream(clock=clock)

    # Deliberately unordered multi-symbol events
    raw_events = [
        {"symbol": "INFY", "price": 1500.0, "volume": 50, "timestamp": 1002.0},
        {"symbol": "TCS", "price": 3500.0, "volume": 100, "timestamp": 1000.0},
        {"symbol": "RELIANCE", "price": 2500.0, "volume": 70, "timestamp": 1001.0},
        {"symbol": "INFY", "price": 1495.0, "volume": 60, "timestamp": 1000.0},
        {"symbol": "TCS", "price": 3510.0, "volume": 110, "timestamp": 1002.0},
    ]
    stream.load_events(raw_events)

    processed_order = []
    while stream.has_next():
        ev = stream.next_event()
        processed_order.append((ev["timestamp"], ev["symbol"]))

    expected_order = [
        (1000.0, "INFY"),
        (1000.0, "TCS"),
        (1001.0, "RELIANCE"),
        (1002.0, "INFY"),
        (1002.0, "TCS"),
    ]
    assert processed_order == expected_order


def test_market_regime_classification_across_regimes():
    """Verify RegimeEvaluator correctly identifies multiple regimes."""
    evaluator = RegimeEvaluator(
        volatility_threshold=0.01,
        min_volume_threshold=20.0,
        trend_threshold_pct=0.005,
        window_size=10,
    )

    # 1. Opening window detection
    clock_open = ReplayClock(
        initial_time=datetime(2026, 3, 24, 9, 20, 0, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp()
    )
    regime, conf = evaluator.evaluate(clock_open, [], {"price": 1000.0, "timestamp": clock_open.current_time})
    assert regime == MarketRegime.OPENING_CLOSING_VOLATILITY
    assert conf >= 0.9

    # Clock at midday (11:30 IST)
    clock_midday = ReplayClock(
        initial_time=datetime(2026, 3, 24, 11, 30, 0, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp()
    )

    # 2. Bullish Trend detection
    bull_history = [
        {"price": 1000.0 + (i * 2.0), "volume": 100.0, "timestamp": clock_midday.current_time - (10 - i)}
        for i in range(10)
    ]
    regime_bull, conf_bull = evaluator.evaluate(
        clock_midday, bull_history, {"price": 1020.0, "timestamp": clock_midday.current_time}
    )
    assert regime_bull == MarketRegime.BULLISH_TREND

    # 3. Bearish Trend detection
    bear_history = [
        {"price": 1020.0 - (i * 2.0), "volume": 100.0, "timestamp": clock_midday.current_time - (10 - i)}
        for i in range(10)
    ]
    regime_bear, conf_bear = evaluator.evaluate(
        clock_midday, bear_history, {"price": 1000.0, "timestamp": clock_midday.current_time}
    )
    assert regime_bear == MarketRegime.BEARISH_TREND

    # 4. Low Liquidity detection
    illiquid_history = [
        {"price": 1000.0, "volume": 5.0, "timestamp": clock_midday.current_time - (10 - i)}
        for i in range(10)
    ]
    regime_illiquid, conf_illiquid = evaluator.evaluate(
        clock_midday, illiquid_history, {"price": 1000.0, "timestamp": clock_midday.current_time}
    )
    assert regime_illiquid == MarketRegime.LOW_LIQUIDITY

    # 5. Degraded Data (large gap > 300s during trading hours)
    gap_history = [
        {"price": 1000.0, "volume": 100.0, "timestamp": clock_midday.current_time - 500.0},
        {"price": 1000.5, "volume": 100.0, "timestamp": clock_midday.current_time},
    ]
    regime_gap, conf_gap = evaluator.evaluate(
        clock_midday, gap_history, {"price": 1000.5, "timestamp": clock_midday.current_time}
    )
    assert regime_gap == MarketRegime.DEGRADED_DATA


def test_regime_aware_strategy_gating(test_db, tmp_path):
    """Verify that regime gating prevents trading during restricted regimes."""
    registry = HistoricalDataRegistry(test_db)

    # Synthetic ticks: oscillating prices during midday
    base_ts = datetime(2026, 3, 24, 11, 0, 0, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp()
    rows = []
    for i in range(60):
        p = 1000.0 + (math.sin(i / 3.0) * 8.0)
        rows.append({
            "symbol": "RELIANCE",
            "timestamp": base_ts + (i * 1.0),
            "price": round(p, 2),
            "volume": 100.0,
        })
    csv_file = _create_sample_csv(rows, tmp_path)

    meta, q_report = registry.register_dataset(
        file_path=csv_file,
        name="Regime Gate Test Dataset",
        source="INTERNAL_SIM",
        provider="TEST",
        acquisition_date="2026-03-24",
        symbols=["RELIANCE"],
        market="NSE",
        timezone="Asia/Kolkata",
    )
    assert q_report.is_valid is True

    engine = ReplayExecutionEngine(db_path=test_db.db_path, initial_cash=100000.0)

    # 1. Run with allowed_regimes = [HIGH_VOLATILITY] (since market is RANGE_BOUND, strategy should be blocked)
    report_blocked = engine.run_replay(
        dataset_id=meta.dataset_id,
        registry=registry,
        strategy_class=MeanReversionStrategy,
        strategy_params={"window_size": 10, "std_dev_threshold": 1.2, "order_qty": 10.0},
        allowed_regimes=[MarketRegime.HIGH_VOLATILITY],
    )
    assert report_blocked["total_orders"] == 0
    assert report_blocked["total_fills"] == 0

    # 2. Run with allowed_regimes = [RANGE_BOUND, LOW_VOLATILITY] (permits trading)
    report_allowed = engine.run_replay(
        dataset_id=meta.dataset_id,
        registry=registry,
        strategy_class=MeanReversionStrategy,
        strategy_params={"window_size": 10, "std_dev_threshold": 1.2, "order_qty": 10.0},
        allowed_regimes=[MarketRegime.RANGE_BOUND, MarketRegime.LOW_VOLATILITY],
    )
    assert report_allowed["total_orders"] > 0
    assert report_allowed["total_fills"] > 0
    assert report_allowed["reconciliation_status"] == "MATCH"


def test_full_replay_pipeline_from_verified_dataset_to_durable_report(test_db, tmp_path):
    """Verify end-to-end replay workflow creates durable report in SQLite database."""
    registry = HistoricalDataRegistry(test_db)

    base_ts = datetime(2026, 3, 24, 11, 0, 0, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp()
    rows = []
    for i in range(80):
        p = 1200.0 + (math.sin(i / 4.0) * 12.0)
        rows.append({
            "symbol": "TCS",
            "timestamp": base_ts + (i * 1.0),
            "price": round(p, 2),
            "volume": 80.0,
        })
    csv_file = _create_sample_csv(rows, tmp_path)

    meta, _ = registry.register_dataset(
        file_path=csv_file,
        name="Pipeline TCS Dataset",
        source="INTERNAL_SIM",
        provider="TEST",
        acquisition_date="2026-03-24",
        symbols=["TCS"],
        market="NSE",
        timezone="Asia/Kolkata",
    )

    engine = ReplayExecutionEngine(db_path=test_db.db_path, initial_cash=100000.0, slippage_bps=5.0, fee_rate_bps=2.0)
    report = engine.run_replay(
        dataset_id=meta.dataset_id,
        registry=registry,
        strategy_class=MeanReversionStrategy,
        strategy_params={"window_size": 10, "std_dev_threshold": 1.0, "order_qty": 5.0},
        symbol="TCS",
    )

    # Verify report structure
    assert report["dataset_id"] == meta.dataset_id
    assert report["dataset_checksum"] == meta.sha256_checksum
    assert report["total_ticks"] == 80
    assert report["total_decisions"] == 80
    assert report["total_fills"] > 0
    assert Decimal(report["total_fees"]) > Decimal("0.00")
    assert Decimal(report["total_slippage"]) > Decimal("0.00")
    assert report["reconciliation_status"] == "MATCH"

    # Query durable report from database
    cursor = test_db.conn.cursor()
    cursor.execute("SELECT * FROM replay_execution_reports WHERE report_id = ?", (report["report_id"],))
    db_row = cursor.fetchone()
    assert db_row is not None
    assert db_row[1] == report["replay_run_id"]
    assert db_row[4] == meta.dataset_id


def test_determinism_proof_bit_for_bit_identical_runs(test_db, tmp_path):
    """Verify two runs on identical inputs yield bit-for-bit identical results to 8 decimal places."""
    registry = HistoricalDataRegistry(test_db)

    base_ts = datetime(2026, 3, 24, 11, 0, 0, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp()
    rows = []
    for i in range(100):
        p = 2500.0 + (math.sin(i / 5.0) * 15.0)
        rows.append({
            "symbol": "INFY",
            "timestamp": base_ts + (i * 1.0),
            "price": round(p, 2),
            "volume": 120.0,
        })
    csv_file = _create_sample_csv(rows, tmp_path)

    meta, _ = registry.register_dataset(
        file_path=csv_file,
        name="Determinism Dataset",
        source="INTERNAL_SIM",
        provider="TEST",
        acquisition_date="2026-03-24",
        symbols=["INFY"],
        market="NSE",
        timezone="Asia/Kolkata",
    )

    engine1 = ReplayExecutionEngine(db_path=test_db.db_path, initial_cash=100000.0, slippage_bps=5.0)
    res1 = engine1.run_replay(
        dataset_id=meta.dataset_id,
        registry=registry,
        strategy_class=MeanReversionStrategy,
        strategy_params={"window_size": 10, "std_dev_threshold": 1.1, "order_qty": 10.0},
        symbol="INFY",
    )

    engine2 = ReplayExecutionEngine(db_path=test_db.db_path, initial_cash=100000.0, slippage_bps=5.0)
    res2 = engine2.run_replay(
        dataset_id=meta.dataset_id,
        registry=registry,
        strategy_class=MeanReversionStrategy,
        strategy_params={"window_size": 10, "std_dev_threshold": 1.1, "order_qty": 10.0},
        symbol="INFY",
    )

    # Assert bit-for-bit mathematical identity across metrics
    assert res1["net_pnl"] == res2["net_pnl"]
    assert res1["final_equity"] == res2["final_equity"]
    assert res1["max_drawdown_pct"] == res2["max_drawdown_pct"]
    assert res1["turnover"] == res2["turnover"]
    assert res1["total_fees"] == res2["total_fees"]
    assert res1["total_slippage"] == res2["total_slippage"]
    assert res1["total_orders"] == res2["total_orders"]
    assert res1["total_fills"] == res2["total_fills"]
    assert res1["total_rejections"] == res2["total_rejections"]
    assert res1["regimes_summary"] == res2["regimes_summary"]
    assert res1["regimes_trades"] == res2["regimes_trades"]
    assert res1["reconciliation_status"] == res2["reconciliation_status"]


def test_tampered_dataset_blocks_replay_execution(test_db, tmp_path):
    """Verify that a tampered dataset fails closed before replay execution starts."""
    registry = HistoricalDataRegistry(test_db)

    base_ts = 1750000000.0
    rows = [
        {"symbol": "TCS", "timestamp": base_ts, "price": 3000.0, "volume": 10.0},
        {"symbol": "TCS", "timestamp": base_ts + 1.0, "price": 3005.0, "volume": 15.0},
    ]
    csv_file = _create_sample_csv(rows, tmp_path)

    meta, _ = registry.register_dataset(
        file_path=csv_file,
        name="Tamper Block Dataset",
        source="INTERNAL_SIM",
        provider="TEST",
        acquisition_date="2026-03-24",
        symbols=["TCS"],
        market="NSE",
        timezone="Asia/Kolkata",
    )

    # Tamper with the file
    with open(csv_file, mode="a", encoding="utf-8") as f:
        f.write("TCS,3999.0,999.0,1750000002.0\n")

    engine = ReplayExecutionEngine(db_path=test_db.db_path, initial_cash=100000.0)

    # Simulation must fail closed with ChecksumMismatchError and NOT execute
    with pytest.raises(ChecksumMismatchError) as exc_info:
        engine.run_replay(
            dataset_id=meta.dataset_id,
            registry=registry,
            strategy_class=MeanReversionStrategy,
            strategy_params={"window_size": 5, "std_dev_threshold": 1.0},
            symbol="TCS",
        )
    assert "Integrity breach" in str(exc_info.value)
    assert "Quarantined" in str(exc_info.value)

    # Verify status in database is QUARANTINED
    cursor = test_db.conn.cursor()
    cursor.execute("SELECT quality_status FROM dataset_registry WHERE dataset_id = ?", (meta.dataset_id,))
    assert cursor.fetchone()[0] == "QUARANTINED"
