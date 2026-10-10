import unittest
from unittest.mock import patch
from oms_project.gateway import BrokerGateway
from oms_project.schemas import OrderIntent, OrderSide, OrderState
from oms_project.algo_pod import AlgoStrategyPod

class TestGatewayPartialFills(unittest.TestCase):
    def setUp(self):
        self.gateway = BrokerGateway(db_path=":memory:")
        self.pod = AlgoStrategyPod(strategy_id="STRAT_001")

    def test_T06_partial_fill_and_cancellation(self):
        intent = self.pod.create_order_intent(symbol="RELIANCE", side=OrderSide.BUY, qty=10, price=1200.0)
        
        # Inject partial fill (4 out of 10)
        def mock_execute(*args, **kwargs):
            return {
                "success": True, 
                "fill": {
                    "fill_id": "FILL_001",
                    "qty": 4.0,
                    "price": 1200.0
                }
            }
            
        with patch.object(self.gateway.paper_exchange, 'execute_order', side_effect=mock_execute):
            res = self.gateway.process_order_intent(intent)
            
        self.assertEqual(res.status, OrderState.CANCELLED)
        
        # Validate position is 4
        self.assertEqual(self.gateway.strategy_positions["STRAT_001"]["RELIANCE"], 4.0)
        
        # Validate db state
        order = self.gateway.db.get_order(res.order_id)
        self.assertEqual(order["state"], OrderState.CANCELLED.value)
        self.assertEqual(order["executed_qty"], 4.0)
        
        # Validate risk reservation is fully released (unfilled portion cancelled)
        self.assertEqual(self.gateway.strategy_reserved["STRAT_001"], 0.0)

if __name__ == "__main__":
    unittest.main()
