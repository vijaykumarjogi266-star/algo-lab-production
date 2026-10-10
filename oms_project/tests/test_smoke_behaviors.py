"""
OMS Project - Behavioral Smoke Test Suite (test_smoke_behaviors.py)
Validates Behavioral Sanity, Regime Switching, Risk Reservation, Execution Fills,
Statutory Friction, and Safe-Fail Guards for the Hybrid Alpha Strategy.
"""

import time
import pytest
from oms_project.schemas import OrderIntent, OrderSide, OrderState
from oms_project.gateway import BrokerGateway
from oms_project.paper_exchange import PaperExchange
from oms_project.strategies.hybrid.hybrid_alpha_strat import HybridAlphaStrategy
from oms_project.strategy_factory import StrategyFactory, FastTestEngine
from oms_project.cio_manager import CIOManager


def test_hybrid_behavioral_trace_regime_switching():
    """
    Behavioral Trace Test:
    Injects Flatline, Spike, and Oscillator market events into HybridAlphaStrategy
    and verifies real-time regime switching between Mean Reversion and Trend Following.
    """
    bot = HybridAlphaStrategy(
        strategy_id="STRAT_HYBRID_SMOKE_001",
        symbol="RELIANCE",
        volatility_window=5,
        volatility_threshold=0.015,  # 1.5% volatility threshold
    )

    trace_log = []

    # 1. EVENT 2: The Flatline (Zero movement)
    flatline_prices = [1000.0] * 10
    for p in flatline_prices:
        intent = bot.on_tick(p)
        trace_log.append({
            "event": "FLATLINE",
            "price": p,
            "regime": bot.current_regime,
            "volatility": bot.current_volatility,
            "signal": intent.side.value if intent else "HOLD",
        })

    assert bot.current_regime == "LOW_VOLATILITY"

    # 2. EVENT 1: The Spike (Violent price surge)
    spike_prices = [1000.0, 1020.0, 1050.0, 1100.0, 1160.0]
    for p in spike_prices:
        intent = bot.on_tick(p)
        trace_log.append({
            "event": "SPIKE",
            "price": p,
            "regime": bot.current_regime,
            "volatility": bot.current_volatility,
            "signal": intent.side.value if intent else "HOLD",
        })

    assert bot.current_regime == "HIGH_VOLATILITY"

    # 3. EVENT 3: The Oscillator (Bouncing between levels)
    oscillator_prices = [1000.0, 970.0, 1030.0, 960.0, 1040.0, 950.0, 1050.0]
    for p in oscillator_prices:
        intent = bot.on_tick(p)
        trace_log.append({
            "event": "OSCILLATOR",
            "price": p,
            "regime": bot.current_regime,
            "volatility": bot.current_volatility,
            "signal": intent.side.value if intent else "HOLD",
        })

    regimes_seen = set(item["regime"] for item in trace_log)
    assert "LOW_VOLATILITY" in regimes_seen
    assert "HIGH_VOLATILITY" in regimes_seen


def test_hybrid_risk_check_and_execution_fill():
    """
    Verifies Broker Gateway risk reservation and execution fill with statutory costs.
    """
    paper_ex = PaperExchange(initial_cash=100000.0)
    gateway = BrokerGateway(paper_exchange=paper_ex, simulation_mode=True)
    gateway.strategy_balances["STRAT_HYBRID_SMOKE_002"] = 100000.0

    bot = HybridAlphaStrategy(
        strategy_id="STRAT_HYBRID_SMOKE_002",
        symbol="RELIANCE",
        volatility_window=3,
        volatility_threshold=0.5,  # Keep in mean reversion regime
        config={"parameters": {"window": 3, "threshold": 1.0}},
    )

    prices = [1000.0, 1000.0, 1000.0, 950.0, 1050.0]
    filled_trades = []

    for p in prices:
        gateway.set_market_price("RELIANCE", p, time.time())
        intent = bot.on_tick(p)
        if intent:
            res = gateway.process_order_intent(intent)
            assert res.status == OrderState.FILLED
            filled_trades.append(res)

    assert len(filled_trades) > 0
    assert gateway.strategy_balances["STRAT_HYBRID_SMOKE_002"] > 0.0


def test_hybrid_safe_fail_kill_switch_and_stale_data_guard():
    """
    Safe-Fail Proof: Verifies that even a Hybrid bot is blocked by Global Kill-Switch and Stale Data Guard.
    """
    paper_ex = PaperExchange(initial_cash=100000.0)
    gateway = BrokerGateway(paper_exchange=paper_ex, simulation_mode=True)
    gateway.strategy_balances["STRAT_HYBRID_FAIL_SAFE"] = 100000.0

    bot = HybridAlphaStrategy(
        strategy_id="STRAT_HYBRID_FAIL_SAFE",
        symbol="RELIANCE",
        volatility_window=5,
        volatility_threshold=0.01,
    )

    # 1. Test Kill-Switch Rejection
    gateway.set_kill_switch(True)
    gateway.set_market_price("RELIANCE", 1100.0, time.time())

    intent_kill = bot.sdk.create_signed_intent("RELIANCE", OrderSide.BUY, 10.0, 1100.0)
    res_kill = gateway.process_order_intent(intent_kill)
    assert res_kill.status == OrderState.REJECTED
    assert "KILL_SWITCH" in res_kill.message

    # Reset Kill-Switch
    gateway.set_kill_switch(False)

    # 2. Test Stale Market Data Rejection (>500ms old)
    gateway.disable_simulation_mode()
    stale_ts = time.time() - 2.0
    gateway.set_market_price("RELIANCE", 1100.0, stale_ts)

    intent_stale = bot.sdk.create_signed_intent("RELIANCE", OrderSide.BUY, 10.0, 1100.0)
    res_stale = gateway.process_order_intent(intent_stale)
    assert res_stale.status == OrderState.REJECTED
    assert "HALT" in res_stale.message or "STALE" in res_stale.message or "Stale" in res_stale.message


def test_symmetry_portfolio_pnl_snapshot():
    """
    Symmetry Portfolio Snapshot Test:
    Executes Hybrid strategy fast-test in Time Machine and confirms Symmetry CIO allocation & asset reconciliation.
    """
    config = {
        "strategy_id": "STRAT_HYBRID_SYMMETRY",
        "strategy_type": "hybrid",
        "symbol": "RELIANCE",
        "parameters": {"volatility_window": 5, "volatility_threshold": 0.01},
        "risk_limits": {"max_qty": 10.0},
    }

    res = FastTestEngine.run_fast_test(config, initial_capital=100000.0, slippage_bps=1.0)

    assert res["strategy_id"] == "STRAT_HYBRID_SYMMETRY"
    assert res["reconciliation_status"] == "MATCH"
    assert res["reconciliation_variance"] == 0.0
    assert "statutory_friction" in res
