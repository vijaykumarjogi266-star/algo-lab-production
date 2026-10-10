import time
import unittest
from oms_project.gateway import BrokerGateway
from oms_project.schemas import OrderIntent, OrderSide, OrderState
from oms_project.algo_pod import AlgoStrategyPod

class TestGatewayShutdown(unittest.TestCase):
    def setUp(self):
        self.gateway = BrokerGateway(db_path=":memory:")
        self.pod = AlgoStrategyPod(strategy_id="STRAT_001")

    def test_duplicate_shutdown(self):
        # 1. Enter position
        intent = self.pod.create_order_intent(symbol="RELIANCE", side=OrderSide.BUY, qty=10, price=1200.0)
        self.gateway.process_order_intent(intent)
        
        # 2. Run shutdown twice concurrently
        res1 = self.gateway.force_flatten_positions()
        res2 = self.gateway.force_flatten_positions()
        
        # res1 should execute, res2 should do nothing
        self.assertEqual(len(res1), 1)
        self.assertEqual(res1[0].status, OrderState.FILLED)
        
        self.assertEqual(len(res2), 0)
        
        # Position should be zero
        self.assertEqual(self.gateway.strategy_positions["STRAT_001"]["RELIANCE"], 0.0)

    def test_shutdown_with_unknown_order(self):
        intent = self.pod.create_order_intent(symbol="RELIANCE", side=OrderSide.BUY, qty=10, price=1200.0)
        res = self.gateway.process_order_intent(intent, simulate_network_failure=True)
        self.assertEqual(res.status, OrderState.SUBMISSION_UNKNOWN)
        
        # If we shutdown, it should resolve unknown orders first!
        # If we don't, it might miss the exposure.
        
        # Hack the paper exchange to simulate it WAS filled
        self.gateway.paper_exchange.execute_order(
            "STRAT_001", "RELIANCE", "BUY", 10, 1200.0, self.gateway.vault.get_exchange_signing_token("STRAT_001"), broker_order_id=res.order_id
        )
        
        # Now force_flatten_positions MUST flatten it!
        flatten_results = self.gateway.force_flatten_positions()
        
        # Verify it was flattened
        self.assertEqual(self.gateway.strategy_positions["STRAT_001"]["RELIANCE"], 0.0)
        # Verify balance is back to initial (minus slippage/fees if any, which is 0 here)
        self.assertEqual(self.gateway.strategy_balances["STRAT_001"], 100000.0)

if __name__ == "__main__":
    unittest.main()
