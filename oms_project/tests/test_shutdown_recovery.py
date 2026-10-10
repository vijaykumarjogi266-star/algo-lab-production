import pytest
import time
from oms_project.schemas import OrderIntent, OrderSide, OrderState, ShutdownState
from oms_project.gateway import BrokerGateway

def test_shutdown_blocks_new_entry():
    gw = BrokerGateway()
    gw.reset_simulation()
    gw.initiate_shutdown("Test shutdown block")
    
    intent = OrderIntent(
        request_id="req_block",
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=10.0,
        price=1200.0,
        signature="TEST"
    )
    
    res = gw.process_order_intent(intent)
    assert res.status == OrderState.REJECTED
    assert res.message == "SHUTDOWN_NEW_ENTRIES_BLOCKED"
    assert gw.strategy_reserved["STRAT_001"] == 0.0

def test_shutdown_allows_reduce_only_request():
    gw = BrokerGateway()
    gw.reset_simulation()
    
    # Establish position
    intent = OrderIntent(
        request_id="req_open",
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=10.0,
        price=1200.0,
        signature="TEST"
    )
    res = gw.process_order_intent(intent)
    assert gw.strategy_positions["STRAT_001"]["RELIANCE"] == 10.0
    
    gw.initiate_shutdown("Test shutdown reduce")
    
    # Valid reduce only
    intent_reduce = OrderIntent(
        request_id="req_close",
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side=OrderSide.SELL,
        qty=10.0,
        price=1200.0,
        signature="TEST",
        reduce_only=True
    )
    res_reduce = gw.process_order_intent(intent_reduce)
    assert res_reduce.status != OrderState.REJECTED
    
    # Invalid reduce only (increases exposure)
    intent_invalid = OrderIntent(
        request_id="req_close_invalid",
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=5.0,
        price=1200.0,
        signature="TEST",
        reduce_only=True
    )
    res_invalid = gw.process_order_intent(intent_invalid)
    assert res_invalid.status == OrderState.REJECTED
    assert res_invalid.message == "SHUTDOWN_REDUCE_ONLY_NO_POSITION"

def test_t18_entry_fill_during_shutdown():
    gw = BrokerGateway()
    gw.reset_simulation()
    
    intent = OrderIntent(
        request_id="req_t18",
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=10.0,
        price=1200.0,
        signature="TEST"
    )
    res = gw.process_order_intent(intent, simulate_network_failure=True)
    assert res.status == OrderState.SUBMISSION_UNKNOWN
    
    gw.initiate_shutdown("T18 Shutdown")
    
    gw.process_execution_report(res.order_id, "exec_t18", 10.0, 1200.0)
    
    order = gw.db.get_order(res.order_id)
    assert order["state"] == OrderState.FILLED.value
    assert gw.strategy_positions["STRAT_001"]["RELIANCE"] == 10.0
    assert gw.strategy_reserved["STRAT_001"] == 0.0
    
    # Duplicate ignored
    gw.process_execution_report(res.order_id, "exec_t18", 10.0, 1200.0)
    assert gw.strategy_positions["STRAT_001"]["RELIANCE"] == 10.0
    
    cur = gw.db.conn.execute("SELECT * FROM shutdown_events WHERE event_type = 'EXECUTION_RECEIVED'")
    assert len(cur.fetchall()) == 1

def test_t19_closing_order_rejected_during_shutdown():
    gw = BrokerGateway()
    gw.reset_simulation()
    
    intent = OrderIntent(
        request_id="req_open_t19",
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=10.0,
        price=1200.0,
        signature="TEST"
    )
    res = gw.process_order_intent(intent)
    assert gw.strategy_positions["STRAT_001"]["RELIANCE"] == 10.0
    
    gw.initiate_shutdown("T19 Shutdown")
    
    intent_close = OrderIntent(
        request_id="req_close_t19",
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side=OrderSide.SELL,
        qty=10.0,
        price=1200.0,
        signature="TEST",
        reduce_only=True
    )
    res_close = gw.process_order_intent(intent_close, simulate_network_failure=True)
    assert res_close.status == OrderState.SUBMISSION_UNKNOWN
    
    gw.resolve_uncertain_order(res_close.order_id, {"status": "REJECTED"})
    
    order = gw.db.get_order(res_close.order_id)
    assert order["state"] == OrderState.REJECTED.value
    assert gw.strategy_positions["STRAT_001"]["RELIANCE"] == 10.0
    assert gw.shutdown_state == ShutdownState.SHUTDOWN_REQUESTED

def test_t20_partial_closing_fill_during_shutdown():
    gw = BrokerGateway()
    gw.reset_simulation()
    
    intent = OrderIntent(
        request_id="req_open_t20",
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=10.0,
        price=1200.0,
        signature="TEST"
    )
    res = gw.process_order_intent(intent)
    assert gw.strategy_positions["STRAT_001"]["RELIANCE"] == 10.0
    
    gw.initiate_shutdown("T20 Shutdown")
    
    intent_close = OrderIntent(
        request_id="req_close_t20",
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side=OrderSide.SELL,
        qty=10.0,
        price=1200.0,
        signature="TEST",
        reduce_only=True
    )
    res_close = gw.process_order_intent(intent_close, simulate_network_failure=True)
    
    gw.process_execution_report(res_close.order_id, "exec_close_t20_1", 4.0, 1200.0)
    
    order = gw.db.get_order(res_close.order_id)
    assert order["executed_qty"] == 4.0
    assert gw.strategy_positions["STRAT_001"]["RELIANCE"] == 6.0
    
    # confirmed cancellation for remainder
    gw.resolve_uncertain_order(res_close.order_id, {"status": "CANCELLED"})
    order = gw.db.get_order(res_close.order_id)
    assert order["state"] == OrderState.CANCELLED.value
    assert gw.strategy_positions["STRAT_001"]["RELIANCE"] == 6.0

def test_shutdown_recovery_reloads_state(tmp_path):
    db_file = str(tmp_path / "recovery_shutdown.db")
    gw = BrokerGateway(db_path=db_file)
    gw.reset_simulation()
    
    intent = OrderIntent(
        request_id="req_open_rec",
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=10.0,
        price=1200.0,
        signature="TEST"
    )
    res = gw.process_order_intent(intent)
    assert gw.strategy_positions["STRAT_001"]["RELIANCE"] == 10.0
    
    gw.initiate_shutdown("Recovery Test")
    
    gw.db.conn.close()
    
    gw2 = BrokerGateway(db_path=db_file)
    # mock balances
    gw2.strategy_balances["STRAT_001"] = 100000.0 - 12000.0
    
    assert gw2.shutdown_state == ShutdownState.SHUTDOWN_REQUESTED
    assert gw2.strategy_positions["STRAT_001"]["RELIANCE"] == 10.0
    
    # Try new entry
    intent2 = OrderIntent(
        request_id="req_fail",
        strategy_id="STRAT_001",
        symbol="INFY",
        side=OrderSide.BUY,
        qty=10.0,
        price=1500.0,
        signature="TEST"
    )
    res2 = gw2.process_order_intent(intent2)
    assert res2.status == OrderState.REJECTED
    assert res2.message == "SHUTDOWN_NEW_ENTRIES_BLOCKED"
