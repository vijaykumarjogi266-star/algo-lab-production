import time
import unittest
from oms_project.gateway import BrokerGateway
from oms_project.schemas import OrderIntent, OrderSide, OrderState
from oms_project.algo_pod import AlgoStrategyPod

class TestGatewayOrderResolution(unittest.TestCase):
    def setUp(self):
        self.gateway = BrokerGateway(db_path=":memory:")
        self.pod = AlgoStrategyPod(strategy_id="STRAT_001")

    def test_timeout_order_resolution_not_found(self):
        # Initial cash
        initial_bal = self.gateway.strategy_balances["STRAT_001"]

        intent = self.pod.create_order_intent(symbol="RELIANCE", side=OrderSide.BUY, qty=10, price=1200.0)
        
        # 1. Simulate network timeout yielding SUBMISSION_UNKNOWN
        res1 = self.gateway.process_order_intent(intent, simulate_network_failure=True)
        self.assertEqual(res1.status, OrderState.SUBMISSION_UNKNOWN)
        
        # Verify risk is reserved
        self.assertEqual(self.gateway.strategy_reserved["STRAT_001"], 12000.0)
        self.assertEqual(self.gateway.strategy_balances["STRAT_001"], initial_bal - 12000.0)
        
        # 2. Resolve unknown orders
        self.gateway.resolve_unknown_orders()
        
        # Because simulate_network_failure prevented it from reaching PaperExchange, query_order will return None
        # It should transition to REJECTED and release risk
        self.assertEqual(self.gateway.strategy_reserved["STRAT_001"], 0.0)
        self.assertEqual(self.gateway.strategy_balances["STRAT_001"], initial_bal)
        
        order = self.gateway.db.get_order(res1.order_id)
        self.assertEqual(order["state"], OrderState.REJECTED.value)

    def test_timeout_order_resolution_found(self):
        # 1. First inject a "fake" successful order into PaperExchange that matches our order_id to simulate timeout AFTER execution
        order_id = f"ORD_{int(time.time()*1000)}"
        self.gateway.paper_exchange.execute_order(
            "STRAT_001", "RELIANCE", "BUY", 10, 1200.0, self.gateway.vault.get_exchange_signing_token("STRAT_001"), broker_order_id=order_id
        )
        
        # We also need to get it in the ledger as SUBMISSION_UNKNOWN
        # This is a bit tricky to simulate directly via process_order_intent without rewriting the test setup.
        # Let's insert it manually into the ledger
        self.gateway.db.conn.execute(
            "INSERT INTO order_ledger (order_id, request_id, strategy_id, symbol, side, qty, price, state, reserved_value, created_at, updated_at, reconciliation_required) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (order_id, order_id, "STRAT_001", "RELIANCE", "BUY", 10.0, 1200.0, OrderState.SUBMISSION_UNKNOWN.value, 12000.0, time.time(), time.time(), 1)
        )
        # Deduct risk
        initial_bal = self.gateway.strategy_balances["STRAT_001"]
        self.gateway.strategy_balances["STRAT_001"] -= 12000.0
        self.gateway.strategy_reserved["STRAT_001"] += 12000.0
        
        # 2. Resolve
        self.gateway.resolve_unknown_orders()
        
        # Should be filled
        self.assertEqual(self.gateway.strategy_reserved["STRAT_001"], 0.0)
        self.assertEqual(self.gateway.strategy_balances["STRAT_001"], initial_bal - 12000.0)
        self.assertEqual(self.gateway.strategy_positions["STRAT_001"]["RELIANCE"], 10)
        
        order = self.gateway.db.get_order(order_id)
        self.assertEqual(order["state"], OrderState.FILLED.value)
        self.assertEqual(order["executed_qty"], 10.0)

if __name__ == "__main__":
    unittest.main()
