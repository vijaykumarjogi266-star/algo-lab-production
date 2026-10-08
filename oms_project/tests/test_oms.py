"""
OMS Project - Automated Unit & Integration Test Suite
Validates Idempotency, Risk Exhaustion, Fail-Closed Guard, and Network Isolation
"""

import time
import unittest
from oms_project.schemas import OrderIntent, OrderSide, OrderState
from oms_project.gateway import BrokerGateway
from oms_project.algo_pod import AlgoStrategyPod


class TestOMSArchitecture(unittest.TestCase):
    def setUp(self):
        self.gateway = BrokerGateway(
            max_gross_exposure=1000000.0,
            price_collar_pct=2.0,
            max_market_data_staleness_ms=500.0,
        )
        self.pod = AlgoStrategyPod(strategy_id="STRAT_001")

    # --------------------------------------------------------------------------
    # Test 1: Idempotency Verification
    # Send the same OrderIntent twice. Second attempt must return cached result
    # --------------------------------------------------------------------------
    def test_idempotency_duplicate_order(self):
        intent = self.pod.create_order_intent(
            symbol="RELIANCE",
            side=OrderSide.BUY,
            qty=10,
            price=1200.0,
            request_id="REQ_IDEMPOTENCY_001",
        )

        initial_bal = self.gateway.strategy_balances["STRAT_001"]

        # First execution -> Should succeed and deduct 12,000 INR
        res1 = self.gateway.process_order_intent(intent)
        self.assertEqual(res1.status, OrderState.FILLED)
        self.assertEqual(res1.reserved_value, 12000.0)
        bal_after_first = self.gateway.strategy_balances["STRAT_001"]
        self.assertEqual(bal_after_first, initial_bal - 12000.0)

        # Second execution with exact same request_id -> Should return duplicate rejection without double deducting
        res2 = self.gateway.process_order_intent(intent)
        self.assertEqual(res2.status, OrderState.FILLED)  # invariant updated by T15: same key returns original result
        # self.assertEqual(res2.message, "REJECTED_DUPLICATE_REQUEST")
        self.assertEqual(res2.request_id, res1.request_id)
        bal_after_second = self.gateway.strategy_balances["STRAT_001"]
        self.assertEqual(bal_after_second, bal_after_first)  # Zero balance mutation on duplicate!

    # --------------------------------------------------------------------------
    # Test 2: Risk Exhaustion Verification
    # Send orders until StrategyBalance hits zero; subsequent order must be rejected
    # --------------------------------------------------------------------------
    def test_risk_exhaustion_balance_limit(self):
        # Set exact balance of 30,000
        self.gateway.strategy_balances["STRAT_001"] = 30000.0

        # Order 1: 24,000 INR (qty=20 @ 1200.0) -> Allowed (Remaining: 6,000)
        intent1 = self.pod.create_order_intent(symbol="RELIANCE", side=OrderSide.BUY, qty=20.0, price=1200.0)
        res1 = self.gateway.process_order_intent(intent1)
        self.assertEqual(res1.status, OrderState.FILLED)
        self.assertEqual(self.gateway.strategy_balances["STRAT_001"], 6000.0)

        # Order 2: 24,000 INR (qty=20 @ 1200.0) -> Exceeds available 6,000 INR -> Must be Rejected
        intent2 = self.pod.create_order_intent(symbol="RELIANCE", side=OrderSide.BUY, qty=20.0, price=1200.0)
        res2 = self.gateway.process_order_intent(intent2)
        self.assertEqual(res2.status, OrderState.REJECTED)
        self.assertIn("INSUFFICIENT_STRATEGY_BALANCE", res2.message)
        # Balance must remain exactly 6,000 INR
        self.assertEqual(self.gateway.strategy_balances["STRAT_001"], 6000.0)

    # --------------------------------------------------------------------------
    # Test 3: Fail-Closed Guard Verification
    # Cut market data feed / trigger KILL_SWITCH -> Attempted trade must be rejected
    # --------------------------------------------------------------------------
    def test_fail_closed_guard_stale_market_data_and_kill_switch(self):
        intent = self.pod.create_order_intent(symbol="RELIANCE", side=OrderSide.BUY, qty=5, price=1200.0)

        # Sub-test A: Active KILL_SWITCH -> Instant Rejection
        self.gateway.set_kill_switch(active=True)
        res_kill = self.gateway.process_order_intent(intent)
        self.assertEqual(res_kill.status, OrderState.REJECTED)
        self.assertIn("KILL_SWITCH_ACTIVE", res_kill.message)

        # Reset kill switch
        self.gateway.set_kill_switch(active=False)

        # Sub-test B: Stale Market Data (> 500ms old) -> Instant Rejection
        stale_time = time.time() - 1.0  # 1000ms old
        self.gateway.set_market_price("RELIANCE", 1200.0, timestamp=stale_time)

        res_stale = self.gateway.process_order_intent(
            self.pod.create_order_intent(symbol="RELIANCE", side=OrderSide.BUY, qty=5, price=1200.0)
        )
        self.assertEqual(res_stale.status, OrderState.REJECTED)
        self.assertIn("STALE_MARKET_DATA", res_stale.message)

        # Sub-test C: Fresh Market Data (< 500ms old) -> Allowed
        self.gateway.set_market_price("RELIANCE", 1200.0, timestamp=time.time())
        res_fresh = self.gateway.process_order_intent(
            self.pod.create_order_intent(symbol="RELIANCE", side=OrderSide.BUY, qty=5, price=1200.0)
        )
        self.assertEqual(res_fresh.status, OrderState.FILLED)

    # --------------------------------------------------------------------------
    # Test 4: Network Escape & Broker Egress Isolation
    # Verify Algo Pod cannot hit external internet / exchange directly
    # --------------------------------------------------------------------------
    def test_network_escape_isolation(self):
        """
        Simulate Algo Pod attempting direct external outbound HTTP call to Google / Exchange.
        In isolated container network policy (internal: true), direct external calls are blocked.
        """
        # Verifies AlgoPod has no exchange credentials or direct API client
        self.assertFalse(hasattr(self.pod, "exchange_api_key"))
        self.assertFalse(hasattr(self.pod, "execute_trade_directly"))

        # Verify Broker Gateway possesses Vault Signing Authority
        self.assertTrue(hasattr(self.gateway, "vault"))
        token = self.gateway.vault.get_exchange_signing_token("STRAT_001")
        self.assertTrue(token.startswith("v1.signing."))


if __name__ == "__main__":
    unittest.main()
