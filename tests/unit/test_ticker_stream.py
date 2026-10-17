"""
Unit tests for SubSecondTickerStream (Pillar 2).
Verifies:
- Ticker event processing and latest price storage.
- Instant sub-second Stop Loss triggering.
- Instant sub-second Target hit triggering.
- Breakeven lock upward ratchet on +1.0R gain.
"""

import pytest
import time
from datetime import datetime, timezone
from services.market_data.ticker_stream import SubSecondTickerStream


def test_ticker_stream_latest_price_update():
    stream = SubSecondTickerStream(simulation_mode=True)
    stream._process_tick("RELIANCE", 2850.50, datetime.now(timezone.utc), volume=100)
    assert stream.get_latest_price("RELIANCE") == 2850.50
    assert stream.get_latest_price("reliance.ns") == 2850.50


def test_ticker_stream_stop_loss_trigger():
    stream = SubSecondTickerStream(simulation_mode=True)
    triggered = []

    def on_exit(sym, price, reason):
        triggered.append((sym, price, reason))

    stream.register_protective_guard(
        symbol="INFY",
        entry_price=1000.0,
        stop_loss=990.0,
        target_price=1020.0,
        quantity=10,
        position_id="POS_1",
        on_exit_trigger_cb=on_exit,
    )

    # Price moves within bounds
    stream._process_tick("INFY", 995.0, datetime.now(timezone.utc))
    assert len(triggered) == 0

    # Price breaches Stop Loss
    stream._process_tick("INFY", 989.50, datetime.now(timezone.utc))
    assert len(triggered) == 1
    assert triggered[0] == ("INFY", 989.50, "STOP_LOSS_HIT")


def test_ticker_stream_target_hit_trigger():
    stream = SubSecondTickerStream(simulation_mode=True)
    triggered = []

    def on_exit(sym, price, reason):
        triggered.append((sym, price, reason))

    stream.register_protective_guard(
        symbol="TCS",
        entry_price=3500.0,
        stop_loss=3450.0,
        target_price=3600.0,
        quantity=5,
        position_id="POS_2",
        on_exit_trigger_cb=on_exit,
    )

    # Price reaches target
    stream._process_tick("TCS", 3605.0, datetime.now(timezone.utc))
    assert len(triggered) == 1
    assert triggered[0] == ("TCS", 3605.0, "TARGET_HIT")


def test_ticker_stream_breakeven_ratchet():
    stream = SubSecondTickerStream(simulation_mode=True)

    stream.register_protective_guard(
        symbol="SBIN",
        entry_price=800.0,
        stop_loss=790.0,
        target_price=830.0,
        quantity=15,
        position_id="POS_3",
    )

    guard = stream.active_monitored_stops["SBIN"]
    assert guard["breakeven_locked"] is False
    assert guard["stop_loss"] == 790.0

    # Price moves up +10 points (+1.0R risk distance)
    stream._process_tick("SBIN", 811.0, datetime.now(timezone.utc))
    assert guard["breakeven_locked"] is True
    # Stop loss moved up above entry + friction buffer
    assert guard["stop_loss"] > 800.0
