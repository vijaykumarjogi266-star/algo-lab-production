"""
Unit tests for Deep Multi-Interval Scanner & Market Regime Evaluation Engine.
"""

import numpy as np
import pandas as pd
import pytest

from services.scanner.nifty100_universe import (
    Nifty100UniverseManager,
    AUTHORITATIVE_NIFTY_100_CONSTITUENTS,
)
from services.scanner.deep_multi_interval_scanner import (
    DeepMultiIntervalScanner,
    MarketRegimeType,
    SetupType,
    compute_interval_indicators,
)


@pytest.fixture
def synthetic_ohlcv_df():
    """Generates synthetic 100-bar OHLCV DataFrame."""
    np.random.seed(42)
    n = 60
    dates = pd.date_range("2026-09-01", periods=n, freq="15min")
    base = 1000.0
    walk = np.cumsum(np.random.normal(0.5, 3.0, n))
    close = base + walk
    high = close + np.random.uniform(1.0, 5.0, n)
    low = close - np.random.uniform(1.0, 5.0, n)
    open_ = close - np.random.normal(0.0, 2.0, n)
    vol = np.random.randint(10000, 50000, n)

    return pd.DataFrame({
        "Open": open_,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": vol,
    }, index=dates)


def test_nifty100_universe_manager():
    mgr = Nifty100UniverseManager()
    symbols = mgr.get_symbols()
    assert len(symbols) >= 100
    assert "RELIANCE" in symbols
    assert "TCS" in symbols
    assert "EICHERMOT" in symbols
    assert "TRENT" in symbols
    assert "HAL" in symbols

    sector_map = mgr.get_sector_map()
    assert sector_map["TCS"] == "INFORMATION_TECHNOLOGY"
    assert sector_map["EICHERMOT"] == "AUTOMOTIVE"
    assert sector_map["TRENT"] == "CONSUMER_SERVICES"


def test_compute_interval_indicators(synthetic_ohlcv_df):
    df_calc = compute_interval_indicators(synthetic_ohlcv_df)

    expected_cols = [
        "EMA_20", "SMA_50", "RSI_14", "ATR_14", "ATR_PCT",
        "BB_UPPER", "BB_LOWER", "BB_WIDTH", "RVOL", "DONCHIAN_HIGH_20", "ADX_14"
    ]
    for col in expected_cols:
        assert col in df_calc.columns, f"Missing column {col}"

    assert not df_calc["EMA_20"].isna().all()
    assert not df_calc["RSI_14"].isna().all()
    assert not df_calc["ATR_14"].isna().all()
    assert not df_calc["BB_WIDTH"].isna().all()


def test_evaluate_symbol_interval_breakout():
    # Construct a clear Donchian breakout scenario
    np.random.seed(1)
    n = 30
    dates = pd.date_range("2026-10-01", periods=n, freq="1h")
    closes = [100.0 + i for i in range(n - 1)] + [150.0]  # Massive breakout candle
    highs = [c + 1.0 for c in closes]
    lows = [c - 1.0 for c in closes]
    opens = closes.copy()
    vols = [1000] * (n - 1) + [5000]  # RVOL > 1.25

    df = pd.DataFrame({"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": vols}, index=dates)
    scanner = DeepMultiIntervalScanner(universe_symbols=["TESTSYM"])
    result = scanner.evaluate_symbol_interval("TESTSYM", df, "1h")

    assert result is not None
    assert result["symbol"] == "TESTSYM"
    assert result["setup"] in [SetupType.DONCHIAN_BREAKOUT.value, SetupType.VOLATILITY_EXPANSION.value]
    assert result["score"] >= 8.5
    assert result["stop_loss"] < 150.0
    assert result["take_profit"] > 150.0


def test_evaluate_market_regime():
    scanner = DeepMultiIntervalScanner()
    # 5 bullish stocks
    data = {}
    for i in range(5):
        dates = pd.date_range("2026-10-01", periods=30, freq="D")
        closes = [100.0 + (j * 2.0) for j in range(30)]
        df = pd.DataFrame({
            "Open": closes,
            "High": [c + 2.0 for c in closes],
            "Low": [c - 2.0 for c in closes],
            "Close": closes,
            "Volume": [10000] * 30,
        }, index=dates)
        data[f"SYM_{i}"] = df

    regime = scanner.evaluate_market_regime(data, "1d")
    assert regime["interval"] == "1d"
    assert regime["breadth_pct_above_ema20"] == 100.0
    assert regime["regime"] == MarketRegimeType.BULL_TREND_STRONG.value
