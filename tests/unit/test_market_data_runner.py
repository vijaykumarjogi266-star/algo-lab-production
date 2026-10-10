"""Unit Tests for Real-Time Market Data Stream Runner (Work Package A)."""

from datetime import datetime, timezone
import time
from services.market_data.runner import RealTimeMarketDataRunner, DataSourceType
from services.market_data.adapters.market_event_schemas import MarketTickEvent, CollectionMode
from data.schemas.canonical_market_data import CanonicalMarketDataBar
from services.common.health import ComponentOperationalState


def test_market_data_runner_mock_stream():
    received_ticks = []
    received_bars = []

    runner = RealTimeMarketDataRunner(
        source_type=DataSourceType.SIMULATED_MOCK,
        symbols=["SBIN", "RELIANCE"],
        bar_interval_seconds=60,
        allow_diagnostic_simulation=True,
    )

    runner.subscribe_ticks(lambda t: received_ticks.append(t))
    runner.subscribe_bars(lambda b: received_bars.append(b))

    runner.start()
    time.sleep(0.3)
    runner.stop()

    assert len(received_ticks) > 0
    assert runner.health.state == ComponentOperationalState.STOPPED
    assert runner.provenance.collection_mode == CollectionMode.REPLAY


def test_market_data_runner_provenance_isolation():
    """Verify historical/replay runner does not claim GENUINE_FORWARD_PAPER_EVIDENCE."""
    runner = RealTimeMarketDataRunner(
        source_type=DataSourceType.SIMULATED_MOCK,
        symbols=["SBIN"],
    )
    assert runner.provenance.collection_mode == CollectionMode.REPLAY
    assert runner.provenance.real_connection_observed is False


def test_market_data_runner_manual_tick_injection():
    received_bars = []

    runner = RealTimeMarketDataRunner(
        source_type=DataSourceType.SIMULATED_MOCK,
        symbols=["SBIN"],
        bar_interval_seconds=60,
        allow_diagnostic_simulation=True,
    )
    runner.subscribe_bars(lambda b: received_bars.append(b))

    t0 = datetime(2026, 9, 29, 9, 30, 0, tzinfo=timezone.utc)
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
    t2 = MarketTickEvent(
        symbol="SBIN",
        token="3045",
        exchange_timestamp=t0.replace(minute=31, second=5),
        receive_timestamp=t0.replace(minute=31, second=5),
        sequence_id=2,
        last_traded_price=825.0,
        last_traded_quantity=10,
        cumulative_volume=1010,
    )

    runner.inject_tick(t1)
    bar = runner.inject_tick(t2)

    assert bar is not None
    assert bar.symbol == "SBIN"
    assert bar.close == 820.0
    assert len(received_bars) == 1
