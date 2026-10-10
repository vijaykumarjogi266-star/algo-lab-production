import time
import os
import unittest
from oms_project.gateway import BrokerGateway
from oms_project.schemas import OrderIntent, OrderSide, OrderState
from oms_project.algo_pod import AlgoStrategyPod

class TestGatewayCrashRecovery(unittest.TestCase):
    def setUp(self):
        self.db_path = f"/tmp/test_ledger_{time.time()}.db"
        self.gateway = BrokerGateway(db_path=self.db_path, max_gross_exposure=1000000.0)
        self.pod = AlgoStrategyPod(strategy_id="STRAT_001")

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_crash_mid_posting_session_restart_recovery(self):
        # 1. Execute an order
        intent = self.pod.create_order_intent(symbol="RELIANCE", side=OrderSide.BUY, qty=10, price=1200.0)
        res1 = self.gateway.process_order_intent(intent)
        self.assertEqual(res1.status, OrderState.FILLED)
        
        # Verify state
        self.assertEqual(self.gateway.strategy_positions["STRAT_001"]["RELIANCE"], 10)
        self.assertEqual(self.gateway.strategy_balances["STRAT_001"], 100000.0 - 12000.0)
        
        # 2. Simulate crash by destroying gateway and creating a new one with same DB
        del self.gateway
        
        # 3. Recover
        recovered_gateway = BrokerGateway(db_path=self.db_path, max_gross_exposure=1000000.0)
        
        # Verify state is reconstructed
        self.assertEqual(recovered_gateway.strategy_positions["STRAT_001"]["RELIANCE"], 10)
        self.assertEqual(recovered_gateway.strategy_balances["STRAT_001"], 100000.0 - 12000.0)

if __name__ == "__main__":
    unittest.main()
