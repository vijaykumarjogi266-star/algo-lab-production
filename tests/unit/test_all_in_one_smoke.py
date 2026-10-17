"""Unit Smoke Test for All-In-One Unified Strategy Registry & Dispatcher."""

import pytest
from datetime import datetime, timezone
from quant.strategies.registry import StrategyRegistry
from quant.strategies.base import SignalType


def test_strategy_registry_registration():
    """Verify that all canonical strategies are correctly registered."""
    expected_strategies = [
        "SMACross",
        "VWAPReversion",
        "OpeningRangeBreakout",
        "BuyAndHold",
        "DonchianBreakout",
        "BollingerReversion",
        "TTMSqueezeBreakout",
    ]
    for name in expected_strategies:
        assert StrategyRegistry.is_registered(name), f"Strategy {name} is not registered"
        strat = StrategyRegistry.get_strategy(name)
        assert strat is not None, f"Failed to instantiate {name}"
        assert strat.version is not None, f"Strategy {name} missing version"


def test_strategy_parameter_validation():
    """Verify fail-closed parameter validation logic."""
    # Valid parameters
    valid, err = StrategyRegistry.validate_parameters(
        "SMACross",
        {"fast_period": 9, "slow_period": 21, "stop_loss_atr": 1.5, "target_atr": 3.0}
    )
    assert valid is True
    assert err is None

    # Invalid fast >= slow
    valid, err = StrategyRegistry.validate_parameters(
        "SMACross",
        {"fast_period": 25, "slow_period": 20}
    )
    assert valid is False
    assert "must be < slow_period" in err

    # Invalid stop_loss_atr out of range
    valid, err = StrategyRegistry.validate_parameters(
        "SMACross",
        {"stop_loss_atr": -1.0}
    )
    assert valid is False
    assert "outside valid range" in err


def test_strategy_dispatch_unknown_strategy():
    """Unknown strategy must safely yield WAIT with no crash (Principle 1 & 2)."""
    market_data = {"price": 1500.0, "atr": 20.0}
    decision = StrategyRegistry.dispatch_symbol("UNKNOWN_FANTASY_STRAT", "TCS", market_data)
    assert decision["symbol"] == "TCS"
    assert decision["signal"] == "WAIT"
    assert decision["confidence"] == 0.0
    assert "unknown" in decision["reason"].lower()


def test_strategy_dispatch_canonical():
    """Verify all 7 canonical strategies dispatch without throwing exceptions."""
    dummy_market_data = {
        "price": 2500.0,
        "atr": 35.0,
        "bar_timestamp": datetime.now(timezone.utc),
        "bars": [],
    }

    strategies = [
        "SMACross",
        "VWAPReversion",
        "OpeningRangeBreakout",
        "BuyAndHold",
        "DonchianBreakout",
        "BollingerReversion",
        "TTMSqueezeBreakout",
    ]

    for name in strategies:
        decision = StrategyRegistry.dispatch_symbol(name, "RELIANCE", dummy_market_data)
        assert decision["symbol"] == "RELIANCE"
        assert decision["signal"] in ["BUY", "SELL", "WAIT", "EXIT"]
        assert "price" in decision
        assert "confidence" in decision
        assert "strategy_id" in decision
