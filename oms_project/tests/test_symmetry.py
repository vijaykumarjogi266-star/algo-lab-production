"""
OMS Project - QUANT-OS Stage 3 Wave 1 Verification Suite (test_symmetry.py)
Verifies:
1. BaseStrategy SDK get_conviction() and on_order_update capital allocation callbacks.
2. CIO Manager Performance-Weighted Capital Allocation across active pods.
3. Broker Gateway Concentration Penalty enforcement on correlated positions.
4. Real-time portfolio correlation detection.
"""

import pytest
from oms_project.gateway import BrokerGateway
from oms_project.schemas import OrderSide, OrderState
from oms_project.cio_manager import CIOManager
from oms_project.strategies.mean_reversion.strategy_sdk import BaseStrategy, StrategySDK


class MockStrategy(BaseStrategy):
    """Concrete mock strategy for testing Symmetry SDK features."""

    def __init__(self, strategy_id: str, symbol: str):
        super().__init__(strategy_id=strategy_id, symbol=symbol)
        self.conviction = 0.85

    def on_tick(self, price: float, timestamp: float):
        return self.sdk.create_signed_intent(
            symbol=self.symbol,
            side=OrderSide.BUY,
            qty=10.0,
            price=price,
        )


def test_base_strategy_sdk_conviction_and_allocation():
    """Verify get_conviction() returns valid scores and on_order_update updates allocated capital."""
    bot = MockStrategy(strategy_id="BOT_ALPHA", symbol="RELIANCE")
    
    # Test conviction boundary enforcement
    assert bot.get_conviction() == 0.85
    bot.conviction = 1.5
    assert bot.get_conviction() == 1.0
    bot.conviction = -0.5
    assert bot.get_conviction() == 0.0

    # Test allocated capital callback
    assert bot.allocated_capital == 100000.0
    bot.on_order_update(order_result=None, allocated_capital=250000.0)
    assert bot.allocated_capital == 250000.0


def test_cio_performance_weighted_allocation():
    """Verify CIO Manager computes performance-weighted allocations and updates pod capital."""
    gateway = BrokerGateway()
    cio = CIOManager(gateway=gateway, total_portfolio_capital=1000000.0, min_pod_floor_pct=0.10)

    bot_a = MockStrategy(strategy_id="BOT_A", symbol="RELIANCE")
    bot_b = MockStrategy(strategy_id="BOT_B", symbol="NIFTY")

    cio.register_pod("BOT_A", strategy_instance=bot_a)
    cio.register_pod("BOT_B", strategy_instance=bot_b)

    # Initially zero trades, allocations are equalized
    initial_allocs = cio.rebalance_allocations()
    assert initial_allocs["BOT_A"] == 500000.0
    assert initial_allocs["BOT_B"] == 500000.0
    assert bot_a.allocated_capital == 500000.0
    assert bot_b.allocated_capital == 500000.0

    # Simulate Bot A generating ₹50,000 profit while Bot B is flat
    cio.record_pod_pnl("BOT_A", 50000.0)
    updated_allocs = cio.rebalance_allocations()

    # Bot A should receive more capital than Bot B, but Bot B maintains min floor (10% = ₹100,000)
    assert updated_allocs["BOT_A"] > updated_allocs["BOT_B"]
    assert updated_allocs["BOT_B"] >= 100000.0
    assert gateway.strategy_balances["BOT_A"] == updated_allocs["BOT_A"]
    assert bot_a.allocated_capital == updated_allocs["BOT_A"]


def test_broker_gateway_concentration_penalty():
    """Verify Gateway applies a Concentration Penalty when Bot B requests BUY on symbol already held LONG by Bot A."""
    gateway = BrokerGateway()
    sdk_a = StrategySDK(strategy_id="BOT_A")
    sdk_b = StrategySDK(strategy_id="BOT_B")

    # Set balances for both bots
    gateway.strategy_balances["BOT_A"] = 100000.0
    gateway.strategy_balances["BOT_B"] = 100000.0

    # Bot A places a BUY order for 10 units of RELIANCE @ 1200
    intent_a = sdk_a.create_signed_intent(symbol="RELIANCE", side=OrderSide.BUY, qty=10.0, price=1200.0)
    res_a = gateway.process_order_intent(intent_a)

    assert res_a.status == OrderState.FILLED
    assert res_a.qty == 10.0
    assert gateway.strategy_positions["BOT_A"]["RELIANCE"] == 10.0

    # Bot B requests BUY for 10 units of RELIANCE @ 1200 (Correlated order)
    intent_b = sdk_b.create_signed_intent(symbol="RELIANCE", side=OrderSide.BUY, qty=10.0, price=1200.0)
    res_b = gateway.process_order_intent(intent_b)

    # Broker Gateway detects correlation risk and applies 50% Concentration Penalty
    assert res_b.status == OrderState.FILLED
    assert res_b.qty == 5.0  # Penalized from 10.0 to 5.0
    assert "CONCENTRATION_PENALTY_APPLIED" in res_b.message
    assert gateway.strategy_positions["BOT_B"]["RELIANCE"] == 5.0


def test_cio_portfolio_correlation_detection():
    """Verify CIO Manager detects symbol overlap and position correlation across pods."""
    gateway = BrokerGateway()
    cio = CIOManager(gateway=gateway)

    # Setup positions for Bot A and Bot B
    gateway.strategy_positions["BOT_A"] = {"RELIANCE": 10.0, "INFY": 5.0}
    gateway.strategy_positions["BOT_B"] = {"RELIANCE": 5.0, "NIFTY": 2.0}

    report = cio.detect_portfolio_correlation()

    assert report["has_correlation_risk"] is True
    assert "RELIANCE" in report["correlated_symbols"]
    assert len(report["correlated_symbols"]["RELIANCE"]) == 2
