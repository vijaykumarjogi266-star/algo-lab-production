"""
OMS Project - End-to-End "Life-of-a-Trade" Validation Test Suite
Automated Pytest coverage for Golden Path, Adversarial Guardrails (2A, 2B, 2C, 2D), and Asset Reconciliation.
"""

import time
import pytest
import urllib.request
import urllib.error

from oms_project.schemas import OrderIntent, OrderSide, OrderState
from oms_project.gateway import BrokerGateway
from oms_project.paper_exchange import PaperExchange
from oms_project.central_data_feed import MarketDataService
from oms_project.strategies.mean_reversion.mean_reversion_strat import MeanReversionStrategy
from oms_project.strategies.mean_reversion.strategy_sdk import StrategySDK
from oms_project.scripts.reconciliation import AssetReconciler


def test_scenario_1_golden_path_execution():
    """Test Scenario 1: Golden Path Execution from Market Tick to Position Broadcast."""
    paper_ex = PaperExchange(initial_cash=100000.0)
    gateway = BrokerGateway(paper_exchange=paper_ex, max_market_data_staleness_ms=500.0)
    feed = MarketDataService()
    sdk = StrategySDK(strategy_id="STRAT_MEAN_REV_001")
    bot = MeanReversionStrategy(
        strategy_id="STRAT_MEAN_REV_001",
        symbol="RELIANCE",
        window_size=5,
        std_dev_threshold=1.0,
        order_qty=10.0,
        sdk=sdk,
    )
    gateway.strategy_balances["STRAT_MEAN_REV_001"] = 100000.0

    position_broadcasts = []

    def on_pos_update(strat_id, symbol, pos, cash):
        position_broadcasts.append((strat_id, symbol, pos, cash))

    gateway.subscribe_position_updates(on_pos_update)
    feed.connect_with_backoff()
    feed.subscribe_market_data("RELIANCE", lambda tick: gateway.set_market_price(tick.symbol, tick.price, tick.timestamp))

    # Warmup ticks
    for p in [1200.0, 1201.0, 1199.0, 1200.0, 1200.0]:
        t = time.time()
        feed.publish_tick_broadcast({"symbol": "RELIANCE", "price": p, "timestamp": t})
        bot.on_tick(p, timestamp=t)

    # Oversold tick -> BUY OrderIntent
    now = time.time()
    feed.publish_tick_broadcast({"symbol": "RELIANCE", "price": 1180.0, "timestamp": now})
    feed.emit_system_heartbeat()

    # Step A: Intent generation
    intent = bot.on_tick(1180.0, timestamp=now)
    assert intent is not None
    assert intent.side == OrderSide.BUY
    assert intent.qty == 10.0
    assert intent.signature is not None

    # Step B, C, D: Gateway processing & paper exchange fill
    res = gateway.process_order_intent(intent)
    assert res.status == OrderState.FILLED
    assert res.reserved_value == 11800.0
    assert res.execution_tx.startswith("v1.signing.")

    # Position broadcast assertion
    assert len(position_broadcasts) == 1
    strat_id, symbol, pos, cash = position_broadcasts[0]
    assert strat_id == "STRAT_MEAN_REV_001"
    assert symbol == "RELIANCE"
    assert pos == 10.0
    assert cash == 88200.0


def test_scenario_2a_network_escape_isolation():
    """Test Scenario 2A: Network Escape Test (Isolation Check)."""
    # Verify AlgoPod container has no direct exchange keys / API client
    sdk = StrategySDK(strategy_id="STRAT_001")
    assert not hasattr(sdk, "exchange_api_key")

    # Outbound call to external/unauthorized IP returns TIMEOUT or CONNECTION REFUSED
    try:
        req = urllib.request.Request("http://192.0.2.1:8080", headers={"User-Agent": "AlgoPod/1.0"})
        with urllib.request.urlopen(req, timeout=0.2):
            escaped = True
    except (urllib.error.URLError, TimeoutError, Exception):
        escaped = False

    assert escaped is False, "Network escape test failed: Outbound traffic was allowed!"


def test_scenario_2b_risk_exhaustion_rejection():
    """Test Scenario 2B: Risk-Exhaustion Test."""
    gateway = BrokerGateway()
    gateway.strategy_balances["STRAT_LOW_BAL"] = 100.0
    gateway.set_market_price("RELIANCE", 1200.0, timestamp=time.time())

    intent = OrderIntent(
        request_id="REQ_RISK_TEST_001",
        strategy_id="STRAT_LOW_BAL",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=10.0,
        price=1200.0,
        signature="sig_test_risk",
    )

    res = gateway.process_order_intent(intent)
    assert res.status == OrderState.REJECTED
    assert "REJECTED_INSUFFICIENT_STRATEGY_BALANCE" in res.message
    assert gateway.strategy_balances["STRAT_LOW_BAL"] == 100.0


def test_scenario_2c_dead_heartbeat_fail_closed():
    """Test Scenario 2C: Dead Heartbeat Test."""
    gateway = BrokerGateway(max_market_data_staleness_ms=500.0)
    stale_time = time.time() - 0.700  # 700ms ago (>500ms max staleness)
    gateway.set_market_price("RELIANCE", 1200.0, timestamp=stale_time)

    intent = OrderIntent(
        request_id="REQ_DEAD_HB_001",
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=5.0,
        price=1200.0,
        timestamp=time.time(),
        signature="sig_test_dead_hb",
    )

    res = gateway.process_order_intent(intent)
    assert res.status == OrderState.REJECTED
    assert "REJECTED_STALE_MARKET_DATA" in res.message


def test_scenario_2d_idempotency_attack():
    """Test Scenario 2D: Idempotency Attack Test."""
    gateway = BrokerGateway(paper_exchange=PaperExchange(initial_cash=100000.0))
    intent = OrderIntent(
        request_id="REQ_IDEMP_ATTACK_001",
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=10.0,
        price=1200.0,
        signature="sig_test_idemp",
    )

    responses = [gateway.process_order_intent(intent) for _ in range(5)]

    # Attempt 1 -> FILLED
    assert responses[0].status == OrderState.FILLED

    # Attempts 2 to 5 -> Original response replayed (FILLED)
    for res in responses[1:]:
        assert res.status == OrderState.FILLED
        assert res.request_id == responses[0].request_id

    # Verify zero balance double-deduction
    assert gateway.strategy_balances["STRAT_001"] == 88000.0


def test_final_reconciliation_zero_variance():
    """Test Final Asset Reconciliation: Broker Ledger vs Paper Exchange."""
    ex = PaperExchange(initial_cash=100000.0)
    gw = BrokerGateway(paper_exchange=ex)
    gw.strategy_balances["STRAT_MEAN_REV_001"] = 100000.0
    gw.set_market_price("RELIANCE", 1200.0, timestamp=time.time())

    # Process 2 trades: BUY 10 RELIANCE @ 1200, SELL 5 RELIANCE @ 1220
    buy_intent = OrderIntent(
        request_id="REQ_RECON_BUY_001",
        strategy_id="STRAT_MEAN_REV_001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=10.0,
        price=1200.0,
        signature="sig_recon_1",
    )
    sell_intent = OrderIntent(
        request_id="REQ_RECON_SELL_001",
        strategy_id="STRAT_MEAN_REV_001",
        symbol="RELIANCE",
        side=OrderSide.SELL,
        qty=5.0,
        price=1220.0,
        signature="sig_recon_2",
    )

    gw.process_order_intent(buy_intent)
    gw.process_order_intent(sell_intent)

    reconciler = AssetReconciler(gw, ex)
    report = reconciler.run_reconciliation("STRAT_MEAN_REV_001")

    assert report["status"] == "MATCH"
    assert report["variance"] == 0.0
