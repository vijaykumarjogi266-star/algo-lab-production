"""Unit Tests for Multi-Symbol Real-Time Equity Scanner (Work Package B)."""

from datetime import datetime, timezone, timedelta
from data.schemas.canonical_market_data import CanonicalMarketDataBar
from data.schemas.contracts import DataQualityStatus
from services.scanner.engine import MultiSymbolScannerEngine, SymbolScannerState
from services.common.health import ComponentOperationalState


def test_scanner_symbol_state_isolation():
    state_sbin = SymbolScannerState("SBIN")
    state_tcs = SymbolScannerState("TCS")

    t0 = datetime(2026, 9, 29, 9, 30, 0, tzinfo=timezone.utc)
    bar_sbin = CanonicalMarketDataBar(
        timestamp=t0,
        symbol="SBIN",
        exchange="NSE",
        timeframe="1m",
        open=820.0,
        high=825.0,
        low=818.0,
        close=822.0,
        volume=1000,
        quality_status=DataQualityStatus.VALID,
    )
    bar_tcs = CanonicalMarketDataBar(
        timestamp=t0,
        symbol="TCS",
        exchange="NSE",
        timeframe="1m",
        open=4150.0,
        high=4170.0,
        low=4140.0,
        close=4165.0,
        volume=500,
        quality_status=DataQualityStatus.VALID,
    )

    state_sbin.append_bar(bar_sbin)
    state_tcs.append_bar(bar_tcs)

    assert len(state_sbin.history) == 1
    assert len(state_tcs.history) == 1
    assert state_sbin.history[0].close == 822.0
    assert state_tcs.history[0].close == 4165.0


def test_scanner_engine_bar_processing():
    engine = MultiSymbolScannerEngine(universe=["SBIN", "RELIANCE"])
    candidates = []
    engine.subscribe_candidates(lambda c: candidates.append(c))

    t0 = datetime(2026, 9, 29, 9, 30, 0, tzinfo=timezone.utc)
    # Feed 4 bars of 5-minute interval for SBIN to trigger VWAP / ORB setup evaluation
    for i, (o, h, l, c, v) in enumerate([
        (820.0, 822.0, 819.0, 821.0, 1000),
        (821.0, 825.0, 820.0, 824.0, 1500),
        (824.0, 828.0, 823.0, 827.0, 2000),
        (827.0, 835.0, 826.0, 834.0, 3000),
    ]):
        bar = CanonicalMarketDataBar(
            timestamp=t0 + timedelta(minutes=i * 5),
            symbol="SBIN",
            exchange="NSE",
            timeframe="5m",
            open=o,
            high=h,
            low=l,
            close=c,
            volume=float(v),
            quality_status=DataQualityStatus.VALID,
        )
        engine.process_bar(bar)

    assert engine.bars_scanned == 4
    assert engine.scanner_health.state == ComponentOperationalState.RUNNING
    assert engine.strategy_health.state == ComponentOperationalState.RUNNING
