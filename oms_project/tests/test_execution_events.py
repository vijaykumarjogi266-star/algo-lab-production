import pytest
import time
from oms_project.gateway import BrokerGateway
from oms_project.schemas import OrderIntent, OrderSide, OrderState
from oms_project.paper_exchange import PaperExchange

def test_T08_duplicate_execution_event():
    """Verify that if the same execution (fill) event is pushed twice, it is deduplicated and not double counted."""
    gateway = BrokerGateway(db_path=":memory:", simulation_mode=False)
    
    # Pre-fund Bot A
    gateway.strategy_balances["BOT_A"] = 100000.0
    gateway.strategy_positions["BOT_A"] = {}
    
    # 1. Place order that gets submitted
    intent = OrderIntent(
        request_id="REQ_T08_1",
        strategy_id="BOT_A",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=10.0,
        price=1200.0, # Match reference price
        timestamp=time.time(),
        expiry=time.time() + 60,
        signature="TEST"
    )
    
    # Process order intent (it gets filled via sync call to paper_exchange, but let's push a raw fill event)
    # To test deduplication, we will directly call the new `process_execution_report` method
    res = gateway.process_order_intent(intent)
    assert res.status == OrderState.FILLED
    
    # The normal process filled it. Current position is 10.
    assert gateway.strategy_positions["BOT_A"]["RELIANCE"] == 10.0
    
    # Now simulate the exchange sending an async webhook with the SAME execution ID
    exec_tx = res.execution_tx # Wait, execution_tx holds signing_token or fill_id?
    
    # Actually, let's create a scenario where we get two explicit fill reports.
    # We will need an execution endpoint.
    fill_id = "EX_TEST_123"
    
    # First report
    success1 = gateway.process_execution_report(
        order_id=res.order_id,
        execution_id=fill_id,
        qty=5.0,
        price=1200.0
    )
    # Since it's a new fill_id (not recorded yet), it should apply
    assert success1 is True
    assert gateway.strategy_positions["BOT_A"]["RELIANCE"] == 15.0  # 10 + 5
    
    # Duplicate report
    success2 = gateway.process_execution_report(
        order_id=res.order_id,
        execution_id=fill_id,
        qty=5.0,
        price=1200.0
    )
    # Must be rejected / deduplicated
    assert success2 is False
    assert gateway.strategy_positions["BOT_A"]["RELIANCE"] == 15.0 # Still 15, no double count
    
    # The ledger must correctly reflect 15 total executed_qty for this order
    order_rec = gateway.db.get_order(res.order_id)
    assert order_rec["executed_qty"] == 15.0

def test_T09_out_of_order_events():
    """Verify that an execution event for an UNKNOWN or SUBMITTED order applies correctly, even if events arrive out of order."""
    gateway = BrokerGateway(db_path=":memory:", simulation_mode=False)
    
    gateway.strategy_balances["BOT_A"] = 100000.0
    gateway.strategy_positions["BOT_A"] = {}
    
    # Let's say order is created but not acknowledged yet, or network failure during submission
    intent = OrderIntent(
        request_id="REQ_T09_1",
        strategy_id="BOT_A",
        symbol="INFY",
        side=OrderSide.BUY,
        qty=10.0,
        price=1500.0, # Match reference price
        timestamp=time.time(),
        expiry=time.time() + 60,
        signature="TEST"
    )
    
    # Simulate network failure -> SUBMISSION_UNKNOWN
    res = gateway.process_order_intent(intent, simulate_network_failure=True)
    if res.status == OrderState.REJECTED:
        print(f"DEBUG REJECTED: {res.message}")
    assert res.status == OrderState.SUBMISSION_UNKNOWN
    
    # Execution report arrives BEFORE broker ack!
    fill_id = "EX_TEST_999"
    success = gateway.process_execution_report(
        order_id=res.order_id,
        execution_id=fill_id,
        qty=10.0,
        price=1500.0
    )
    
    assert success is True
    assert gateway.strategy_positions["BOT_A"]["INFY"] == 10.0
    
    order_rec = gateway.db.get_order(res.order_id)
    assert OrderState(order_rec["state"]) == OrderState.FILLED
    assert order_rec["executed_qty"] == 10.0
