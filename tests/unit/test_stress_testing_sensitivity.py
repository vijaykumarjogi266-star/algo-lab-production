"""
Unit tests for Algo Lab Backtest Stress Testing & Drawdown Sensitivity Engine.
"""

from datetime import datetime, date
import numpy as np
import polars as pl
import pytest

from services.backtest_engine.stress_testing_engine import (
    StressTestingEngine,
    ACTIVE_STRATEGIES,
    REGIME_WINDOWS,
    SLIPPAGE_GRID,
)


@pytest.fixture
def mock_datasets():
    """Generates synthetic 5-year multi-symbol daily datasets."""
    np.random.seed(42)
    symbols = ["RELIANCE", "TCS", "INFY"]
    datasets = {}

    dates = pl.datetime_range(
        start=pl.datetime(2021, 1, 1, 9, 15),
        end=pl.datetime(2026, 1, 1, 15, 30),
        interval="1d",
        eager=True,
    )

    n = len(dates)
    for sym in symbols:
        base = 2000.0 if sym == "RELIANCE" else (3000.0 if sym == "TCS" else 1500.0)
        walk = np.cumsum(np.random.normal(0.5, 5.0, n))
        closes = base + walk
        highs = closes + np.random.uniform(2.0, 10.0, n)
        lows = closes - np.random.uniform(2.0, 10.0, n)
        opens = closes - np.random.normal(0.0, 3.0, n)
        volumes = np.random.randint(100000, 500000, n)

        df = pl.DataFrame({
            "date": dates,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        })
        datasets[sym] = df

    return datasets


def test_filter_datasets_by_date(mock_datasets):
    engine = StressTestingEngine(mock_datasets)
    filtered = engine.filter_datasets_by_date("2021-01-01", "2021-12-31")

    assert len(filtered) == len(mock_datasets)
    for sym, df in filtered.items():
        assert df["date"].min().date() >= date(2021, 1, 1)
        assert df["date"].max().date() <= date(2021, 12, 31)


def test_evaluate_regime_stress_testing(mock_datasets):
    engine = StressTestingEngine(mock_datasets)
    regime_results = engine.evaluate_regime_stress_testing("STRATEGY_A")

    assert len(regime_results) == len(REGIME_WINDOWS)
    for r in regime_results:
        assert "regime_id" in r
        assert "profit_factor" in r
        assert "max_drawdown_pct" in r
        assert "win_rate_pct" in r


def test_evaluate_slippage_sensitivity(mock_datasets):
    engine = StressTestingEngine(mock_datasets)
    slippage_results = engine.evaluate_slippage_sensitivity("STRATEGY_A")

    assert len(slippage_results) == len(SLIPPAGE_GRID)
    # 0 bps should have 0 slippage drag compared to baseline
    assert slippage_results[0]["slippage_drag_inr"] == 0.0
    # Higher slippage should increase total friction or drag
    assert slippage_results[-1]["slippage_bps"] == 50


def test_drawdown_sensitivity_curve(mock_datasets):
    engine = StressTestingEngine(mock_datasets)
    dd_curve = engine.compute_drawdown_sensitivity_curve("STRATEGY_A")

    assert "max_drawdown_pct" in dd_curve
    assert "max_consecutive_losses" in dd_curve
    assert "recovery_factor" in dd_curve
    assert "taleb_certification" in dd_curve


def test_comprehensive_stress_test_selective_filtering(mock_datasets):
    engine = StressTestingEngine(mock_datasets)
    # Test selective execution for STRATEGY_SUPER_ADAPTIVE
    report = engine.execute_comprehensive_stress_test(strategies=["STRATEGY_SUPER_ADAPTIVE"])

    assert "strategies" in report
    assert "STRATEGY_SUPER_ADAPTIVE" in report["strategies"]
    assert len(report["strategies"]) == 1
    strat_data = report["strategies"]["STRATEGY_SUPER_ADAPTIVE"]
    assert len(strat_data["regime_stress_testing"]) == len(REGIME_WINDOWS)
    assert len(strat_data["slippage_friction_sensitivity"]) == len(SLIPPAGE_GRID)
