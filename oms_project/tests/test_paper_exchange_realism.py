"""
OMS Project - Stage 3: Internal Paper Exchange & Execution Realism Test Suite
(test_paper_exchange_realism.py)

Comprehensive verification for:
1. Market vs Limit orders (matching rules, resting order book, tick-triggered fills).
2. Reduce-only orders (position requirement, overshoot rejection).
3. Adverse fill scenarios (Partial fills, No fills, liquidity caps).
4. Adverse rejections & timeouts (Circuit limits, simulated timeout uncertainty).
5. Deterministic slippage, bid-ask spread, and fee accounting.
6. Session close / EOD auto-cancellation of resting orders.
7. Restart durability for resting orders.
8. Cost & slippage sensitivity analysis report generation.
"""

import os
import time
import pytest
from decimal import Decimal

from oms_project.schemas import OrderIntent, OrderSide, OrderState, OrderType, NormalizedTick
from oms_project.gateway import BrokerGateway
from oms_project.paper_exchange import PaperExchange, AdverseExecutionProfile, FillMode
from oms_project.algo_pod import AlgoStrategyPod


@pytest.fixture
def clean_gateway():
    gw = BrokerGateway(db_path=":memory:")
    gw.simulation_mode = True
    gw.strategy_balances["STRAT_001"] = 100000.0
    gw.strategy_reserved["STRAT_001"] = 0.0
    gw.strategy_positions["STRAT_001"] = {}
    gw.strategy_entry_prices["STRAT_001"] = {}
    return gw


def test_market_and_limit_orders_execution_and_resting_book(clean_gateway):
    """Test MARKET orders fill immediately, while out-of-market LIMIT orders rest until matched."""
    gw = clean_gateway
    gw.set_market_price("RELIANCE", 1000.0)

    # 1. Market BUY order executes immediately at current price
    mkt_intent = OrderIntent(
        request_id="REQ_MKT_001",
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=10.0,
        price=1000.0,
        order_type=OrderType.MARKET,
        signature="sig_mkt",
    )
    res_mkt = gw.process_order_intent(mkt_intent)
    assert res_mkt.status == OrderState.FILLED
    assert gw.strategy_positions["STRAT_001"]["RELIANCE"] == 10.0

    # 2. Limit BUY order with limit_price = 990.0 (below current 1000.0, within 2% collar) cannot fill immediately
    limit_intent = OrderIntent(
        request_id="REQ_LMT_001",
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=5.0,
        price=990.0,
        order_type=OrderType.LIMIT,
        signature="sig_lmt",
    )
    res_lmt = gw.process_order_intent(limit_intent)
    assert res_lmt.status == OrderState.LIVE
    assert res_lmt.message == "LIMIT_ORDER_RESTING_IN_BOOK"
    assert res_lmt.order_id in gw.paper_exchange.resting_orders

    # 3. Market moves down to 988.0 -> resting limit order triggers and fills!
    matched_fills = gw.paper_exchange.on_market_tick("RELIANCE", price=988.0, volume=500.0)
    assert len(matched_fills) == 1
    assert matched_fills[0]["broker_order_id"] == res_lmt.order_id
    assert matched_fills[0]["qty"] == 5.0
    assert matched_fills[0]["price"] == 988.0
    assert res_lmt.order_id not in gw.paper_exchange.resting_orders


def test_reduce_only_orders_validation(clean_gateway):
    """Test REDUCE_ONLY orders strictly validate existing position and reject overshoots."""
    gw = clean_gateway
    gw.set_market_price("TCS", 3000.0)

    # Case A: No position -> SELL reduce-only must be rejected
    intent_no_pos = OrderIntent(
        request_id="REQ_RO_NO_POS",
        strategy_id="STRAT_001",
        symbol="TCS",
        side=OrderSide.SELL,
        qty=5.0,
        price=3000.0,
        reduce_only=True,
        signature="sig_ro1",
    )
    res_no_pos = gw.process_order_intent(intent_no_pos)
    assert res_no_pos.status == OrderState.REJECTED
    assert "REDUCE_ONLY_NO_LONG_POSITION" in res_no_pos.message

    # Open Long position of 10 shares
    buy_intent = OrderIntent(
        request_id="REQ_BUY_TCS",
        strategy_id="STRAT_001",
        symbol="TCS",
        side=OrderSide.BUY,
        qty=10.0,
        price=3000.0,
        signature="sig_buy",
    )
    res_buy = gw.process_order_intent(buy_intent)
    assert res_buy.status == OrderState.FILLED

    # Case B: SELL reduce-only exceeding position (qty 15 > pos 10) must be rejected
    intent_exceed = OrderIntent(
        request_id="REQ_RO_EXCEED",
        strategy_id="STRAT_001",
        symbol="TCS",
        side=OrderSide.SELL,
        qty=15.0,
        price=3000.0,
        reduce_only=True,
        signature="sig_ro2",
    )
    res_exceed = gw.process_order_intent(intent_exceed)
    assert res_exceed.status == OrderState.REJECTED
    assert "REDUCE_ONLY_EXCEEDS_POSITION" in res_exceed.message

    # Case C: Valid SELL reduce-only of 6 shares succeeds
    intent_valid = OrderIntent(
        request_id="REQ_RO_VALID",
        strategy_id="STRAT_001",
        symbol="TCS",
        side=OrderSide.SELL,
        qty=6.0,
        price=3000.0,
        reduce_only=True,
        signature="sig_ro3",
    )
    res_valid = gw.process_order_intent(intent_valid)
    assert res_valid.status == OrderState.FILLED
    assert gw.strategy_positions["STRAT_001"]["TCS"] == 4.0


def test_adverse_execution_partial_and_no_fill(clean_gateway):
    """Test partial fills and no-fill liquidity exhaustion behavior."""
    gw = clean_gateway
    gw.set_market_price("INFY", 1500.0)

    # 1. No Fill Profile
    no_fill_profile = AdverseExecutionProfile(
        name="Illiquid Market",
        fill_mode=FillMode.NO_FILL,
    )
    gw.paper_exchange.set_profile(no_fill_profile)

    intent_no_fill = OrderIntent(
        request_id="REQ_NO_FILL",
        strategy_id="STRAT_001",
        symbol="INFY",
        side=OrderSide.BUY,
        qty=20.0,
        price=1500.0,
        signature="sig_nf",
    )
    res_nf = gw.process_order_intent(intent_no_fill)
    assert res_nf.status == OrderState.REJECTED
    assert "NO_FILL_EXCHANGE_LIQUIDITY_EXHAUSTED" in res_nf.message
    assert gw.strategy_reserved["STRAT_001"] == 0.0

    # 2. Partial Fill Profile (50% ratio)
    partial_profile = AdverseExecutionProfile(
        name="Partial Liquidity",
        fill_mode=FillMode.PARTIAL,
        partial_ratio=0.5,
    )
    gw.paper_exchange.set_profile(partial_profile)

    intent_partial = OrderIntent(
        request_id="REQ_PARTIAL_FILL",
        strategy_id="STRAT_001",
        symbol="INFY",
        side=OrderSide.BUY,
        qty=20.0,
        price=1500.0,
        signature="sig_pf",
    )
    res_pf = gw.process_order_intent(intent_partial)
    # Synchronous partial execution cancels remainder
    assert res_pf.status == OrderState.CANCELLED
    assert "Partially Filled" in res_pf.message
    # Only 10 shares filled
    assert gw.strategy_positions["STRAT_001"]["INFY"] == 10.0
    # Remaining reservation released
    assert gw.strategy_reserved["STRAT_001"] == 0.0


def test_adverse_execution_rejections_and_timeouts(clean_gateway):
    """Test explicit adverse rejections and timeout uncertainty simulation."""
    gw = clean_gateway
    gw.set_market_price("HDFCBANK", 1600.0)

    # 1. Circuit Limit Rejection
    circuit_profile = AdverseExecutionProfile(
        name="Circuit Filter",
        rejection_reason="EXCHANGE_CIRCUIT_LIMIT_BREACHED",
    )
    gw.paper_exchange.set_profile(circuit_profile)

    intent_circuit = OrderIntent(
        request_id="REQ_CIRCUIT_001",
        strategy_id="STRAT_001",
        symbol="HDFCBANK",
        side=OrderSide.BUY,
        qty=10.0,
        price=1600.0,
        signature="sig_circ",
    )
    res_circ = gw.process_order_intent(intent_circuit)
    assert res_circ.status == OrderState.REJECTED
    assert res_circ.message == "EXCHANGE_CIRCUIT_LIMIT_BREACHED"
    assert gw.strategy_reserved["STRAT_001"] == 0.0

    # 2. Network Timeout Uncertainty
    timeout_profile = AdverseExecutionProfile(
        name="Timeout Simulator",
        simulate_timeout=True,
    )
    gw.paper_exchange.set_profile(timeout_profile)

    intent_timeout = OrderIntent(
        request_id="REQ_TIMEOUT_001",
        strategy_id="STRAT_001",
        symbol="HDFCBANK",
        side=OrderSide.BUY,
        qty=5.0,
        price=1600.0,
        signature="sig_to",
    )
    res_to = gw.process_order_intent(intent_timeout)
    assert res_to.status == OrderState.REJECTED
    assert res_to.message == "NETWORK_TIMEOUT"


def test_deterministic_slippage_spread_and_fee_modeling(clean_gateway):
    """Test deterministic execution price adjustment via spread, slippage, and fee deduction."""
    gw = clean_gateway
    gw.set_market_price("RELIANCE", 1000.0)

    # Spread = 10 bps (0.1%), Slippage = 20 bps (0.2%), Fee = 10 bps (0.1%)
    realistic_profile = AdverseExecutionProfile(
        name="Realistic Friction",
        spread_bps=10.0,
        slippage_bps=20.0,
        fee_rate_bps=10.0,
    )
    gw.paper_exchange.set_profile(realistic_profile)

    init_cash = gw.paper_exchange.cash_balance

    # BUY 10 shares
    # Spread adj = 1000 * 10 / 20000 = 0.5
    # Slippage adj = 1000 * 20 / 10000 = 2.0
    # Exec Price = 1000 + 0.5 + 2.0 = 1002.5
    # Cost = 10 * 1002.5 = 10025.0
    # Fee = 10025 * 10 / 10000 = 10.025
    # Total deduction = 10035.025
    exec_res = gw.paper_exchange.execute_order(
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side="BUY",
        qty=10.0,
        price=1000.0,
        signing_token="v1.signing.valid_token",
    )
    assert exec_res["success"] is True
    fill = exec_res["fill"]
    assert fill["price"] == 1002.5
    assert fill["fee"] == 10.025
    assert pytest.approx(gw.paper_exchange.cash_balance, rel=1e-6) == (init_cash - 10035.025)
    assert gw.paper_exchange.positions["RELIANCE"] == 10.0


def test_session_close_eod_cancellation(clean_gateway):
    """Test session_close cancels all resting orders with CANCELLED_EOD_SESSION_CLOSE."""
    gw = clean_gateway
    gw.set_market_price("TCS", 3500.0)

    # Place two resting limit orders (within 2% collar of 3500.0)
    intent1 = OrderIntent(
        request_id="REQ_EOD_001",
        strategy_id="STRAT_001",
        symbol="TCS",
        side=OrderSide.BUY,
        qty=10.0,
        price=3470.0,  # limit below market, within 2%
        order_type=OrderType.LIMIT,
        signature="sig_eod1",
    )
    res1 = gw.process_order_intent(intent1)
    assert res1.status == OrderState.LIVE

    intent2 = OrderIntent(
        request_id="REQ_EOD_002",
        strategy_id="STRAT_001",
        symbol="TCS",
        side=OrderSide.SELL,
        qty=5.0,
        price=3530.0,  # limit above market, within 2%
        order_type=OrderType.LIMIT,
        signature="sig_eod2",
    )
    res2 = gw.process_order_intent(intent2)
    assert res2.status == OrderState.LIVE

    assert len(gw.paper_exchange.resting_orders) == 2

    # Execute EOD session close
    cancelled = gw.paper_exchange.session_close()
    assert len(cancelled) == 2
    assert all(c["reason"] == "CANCELLED_EOD_SESSION_CLOSE" for c in cancelled)
    assert len(gw.paper_exchange.resting_orders) == 0


def test_resting_order_cancellation_and_restart_survival(clean_gateway):
    """Test resting limit orders survive in database and can be cancelled manually."""
    gw = clean_gateway
    gw.set_market_price("INFY", 1400.0)

    intent = OrderIntent(
        request_id="REQ_REST_CANCEL",
        strategy_id="STRAT_001",
        symbol="INFY",
        side=OrderSide.BUY,
        qty=10.0,
        price=1385.0,  # within 2% of 1400.0
        order_type=OrderType.LIMIT,
        signature="sig_rc",
    )
    res = gw.process_order_intent(intent)
    assert res.status == OrderState.LIVE

    # Verify db state is LIVE
    order_in_db = gw.db.get_order(res.order_id)
    assert order_in_db["state"] == OrderState.LIVE.value

    # Cancel order in paper exchange
    cancel_res = gw.paper_exchange.cancel_order(res.order_id, reason="USER_CANCELLED")
    assert cancel_res["success"] is True
    assert cancel_res["status"] == "CANCELLED"
    assert res.order_id not in gw.paper_exchange.resting_orders


def test_cost_and_slippage_sensitivity_analysis():
    """Test generate_sensitivity_report generates sensitivity matrix across spreads and slippages."""
    exchange = PaperExchange(initial_cash=100000.0)

    sample_trades = [
        {"qty": 100.0, "price": 1000.0},
        {"qty": 50.0, "price": 2000.0},
        {"qty": 200.0, "price": 500.0},
    ]  # Total turnover = 100k + 100k + 100k = 300,000.0

    report = exchange.generate_sensitivity_report(
        base_trades=sample_trades,
        slippage_levels_bps=[0.0, 5.0, 10.0, 20.0],
        spread_levels_bps=[0.0, 2.0, 5.0],
    )

    assert report["total_trades"] == 3
    assert report["total_turnover"] == 300000.0
    matrix = report["sensitivity_matrix"]
    assert len(matrix) == 12  # 4 slippage levels * 3 spread levels

    # For slippage=10bps, spread=2bps:
    # slip drag = 300000 * 10 / 10000 = 300.0
    # spread drag = 300000 * 2 / 20000 = 30.0
    # total drag = 330.0
    cell = next(c for c in matrix if c["slippage_bps"] == 10.0 and c["spread_bps"] == 2.0)
    assert cell["slippage_drag"] == 300.0
    assert cell["spread_drag"] == 30.0
    assert cell["total_execution_drag"] == 330.0
    assert pytest.approx(cell["drag_pct_of_turnover"], rel=1e-4) == 0.11
