"""
OMS Project - QUANT-OS Stage 2: The Time Machine Automated Test Suite
Pytest coverage for HistoricalReplayEngine, Simulation Broker, Slippage Engine,
Simulation Lock, Clean-Slate Reset, Determinism Proof, and StrategyOptimizer.
"""

import time
import tempfile
import csv
import pytest
from typing import List, Dict, Any

from oms_project.schemas import OrderIntent, OrderSide, OrderState
from oms_project.gateway import BrokerGateway
from oms_project.paper_exchange import PaperExchange
from oms_project.central_data_feed import MarketDataService
from oms_project.replay_service import HistoricalReplayEngine, generate_synthetic_ticks
from oms_project.optimizer import StrategyOptimizer
from oms_project.strategies.mean_reversion.mean_reversion_strat import MeanReversionStrategy
from oms_project.strategies.mean_reversion.strategy_sdk import StrategySDK


def test_replay_service_loading_and_playback():
    """Test HistoricalReplayEngine loads ticks and publishes sync broadcasts."""
    feed = MarketDataService()
    replay = HistoricalReplayEngine(market_data_service=feed, playback_speed=0.0)

    ticks = generate_synthetic_ticks(symbol="RELIANCE", count=50, seed=123)
    replay.load_ticks(ticks)

    received_ticks = []
    feed.subscribe_market_data("RELIANCE", lambda t: received_ticks.append(t))

    count = replay.replay_ticks_sync()
    assert count == 50
    assert len(received_ticks) == 50
    assert received_ticks[0].symbol == "RELIANCE"
    assert replay.get_elapsed_time() >= 0.0


def test_replay_service_csv_loader():
    """Test loading historical tick data from CSV file."""
    ticks = [
        {"symbol": "RELIANCE", "price": 1200.0, "volume": 100, "timestamp": 1000.0},
        {"symbol": "RELIANCE", "price": 1205.0, "volume": 150, "timestamp": 1001.0},
    ]
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["symbol", "price", "volume", "timestamp"])
        writer.writeheader()
        writer.writerows(ticks)
        temp_csv_path = f.name

    feed = MarketDataService()
    replay = HistoricalReplayEngine(market_data_service=feed, playback_speed=0.0)
    replay.load_csv(temp_csv_path)

    assert len(replay.ticks) == 2
    assert replay.ticks[0]["price"] == 1200.0
    assert replay.ticks[1]["price"] == 1205.0


def test_simulation_lock_blocks_external_calls():
    """Test Simulation Lock raises PermissionError if external broker API call is attempted."""
    gateway = BrokerGateway(simulation_mode=True)
    assert gateway.simulation_mode is True

    with pytest.raises(PermissionError) as exc_info:
        gateway.execute_external_broker_api_call("https://api.broker.com/v1/orders", {"order": "test"})

    assert "permanently disabled in Algo Lab" in str(exc_info.value)


def test_slippage_engine_buy_and_sell():
    """Test Slippage Engine correctly adjusts buy and sell execution prices."""
    # BUY order with 10bps slippage (0.1% increase)
    gw_buy = BrokerGateway(simulation_mode=True, slippage_bps=10.0)
    gw_buy.strategy_balances["STRAT_001"] = 100000.0
    gw_buy.set_market_price("RELIANCE", 1000.0)

    intent_buy = OrderIntent(
        request_id="REQ_SLIP_BUY_001",
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=10.0,
        price=1000.0,
        signature="sig_slip_buy",
    )
    res_buy = gw_buy.process_order_intent(intent_buy)
    assert res_buy.status == OrderState.FILLED
    # Executed price = 1000 * (1 + 10/10000) = 1001.0
    assert pytest.approx(res_buy.price, rel=1e-6) == 1001.0
    assert pytest.approx(res_buy.reserved_value, rel=1e-6) == 10010.0
    assert pytest.approx(gw_buy.strategy_balances["STRAT_001"], rel=1e-6) == 89990.0

    # SELL order with 10bps slippage (0.1% decrease)
    gw_sell = BrokerGateway(simulation_mode=True, slippage_bps=10.0)
    gw_sell.strategy_balances["STRAT_001"] = 100000.0
    gw_sell.strategy_positions["STRAT_001"]["RELIANCE"] = 10.0
    gw_sell.paper_exchange.positions["RELIANCE"] = 10.0
    gw_sell.set_market_price("RELIANCE", 1000.0)

    intent_sell = OrderIntent(
        request_id="REQ_SLIP_SELL_001",
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side=OrderSide.SELL,
        qty=10.0,
        price=1000.0,
        signature="sig_slip_sell",
    )
    res_sell = gw_sell.process_order_intent(intent_sell)
    assert res_sell.status == OrderState.FILLED
    # Executed price = 1000 * (1 - 10/10000) = 999.0
    assert pytest.approx(res_sell.price, rel=1e-6) == 999.0
    assert pytest.approx(gw_sell.strategy_balances["STRAT_001"], rel=1e-6) == 109990.0


def test_clean_slate_reset():
    """Test reset_simulation wipes DB ledger, positions, balances, and idempotency cache."""
    gateway = BrokerGateway(simulation_mode=True, paper_exchange=PaperExchange(initial_cash=100000.0))
    gateway.set_market_price("RELIANCE", 1000.0)
    intent = OrderIntent(
        request_id="REQ_RESET_TEST_001",
        strategy_id="STRAT_MEAN_REV_001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=10.0,
        price=1000.0,
        signature="sig_reset",
    )
    res = gateway.process_order_intent(intent)
    assert res.status == OrderState.FILLED
    assert len(gateway.idempotency_cache) == 1
    assert gateway.strategy_positions.get("STRAT_MEAN_REV_001", {}).get("RELIANCE", 0.0) == 10.0

    # Perform Clean-Slate Reset
    gateway.reset_simulation(initial_cash=50000.0)

    assert len(gateway.idempotency_cache) == 0
    assert gateway.strategy_balances["STRAT_MEAN_REV_001"] == 50000.0
    assert gateway.strategy_positions["STRAT_MEAN_REV_001"] == {}
    assert len(gateway.paper_exchange.execution_history) == 0


def test_determinism_proof_8_decimal_precision():
    """Test that two identical backtest runs yield bit-for-bit identical results to 8 decimal places."""
    ticks = generate_synthetic_ticks(symbol="RELIANCE", count=300, seed=99)
    opt = StrategyOptimizer(ticks=ticks, initial_cash=100000.0)

    res1 = opt.run_single_backtest(window_size=10, std_dev_threshold=1.5)
    res2 = opt.run_single_backtest(window_size=10, std_dev_threshold=1.5)

    assert res1["final_equity"] == res2["final_equity"]
    assert res1["net_pnl"] == res2["net_pnl"]
    assert res1["total_trades"] == res2["total_trades"]
    assert res1["max_drawdown_pct"] == res2["max_drawdown_pct"]
    assert res1["reconciliation_variance"] == 0.0
    assert res1["reconciliation_status"] == "MATCH"


def test_strategy_optimizer_grid_search():
    """Test StrategyOptimizer grid search parameter sweep."""
    ticks = generate_synthetic_ticks(symbol="RELIANCE", count=200, seed=77)
    opt = StrategyOptimizer(ticks=ticks, initial_cash=100000.0)

    opt_res = opt.grid_search(window_range=[5, 10], std_dev_range=[1.0, 1.5])
    assert "best_parameters" in opt_res
    assert "all_results" in opt_res
    assert len(opt_res["all_results"]) == 4

    best = opt_res["best_parameters"]
    assert best["window_size"] in [5, 10]
    assert best["std_dev_threshold"] in [1.0, 1.5]
    assert best["reconciliation_status"] == "MATCH"
    assert best["reconciliation_variance"] == 0.0
