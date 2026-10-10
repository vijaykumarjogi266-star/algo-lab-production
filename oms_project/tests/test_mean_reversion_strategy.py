"""
OMS Project - Mean Reversion Bot & Strategy SDK Integration Tests
Verifies SMA calculation, Bollinger Bands, signal generation, and OrderIntent routing.
"""

import unittest
from oms_project.schemas import OrderSide, OrderState
from oms_project.gateway import BrokerGateway
from oms_project.strategies.mean_reversion.strategy_sdk import StrategySDK
from oms_project.strategies.mean_reversion.mean_reversion_strat import MeanReversionStrategy


class TestMeanReversionStrategyBot(unittest.TestCase):
    def setUp(self):
        self.gateway = BrokerGateway()
        self.sdk = StrategySDK(strategy_id="STRAT_MEAN_REV_001")
        self.bot = MeanReversionStrategy(
            strategy_id="STRAT_MEAN_REV_001",
            symbol="RELIANCE",
            window_size=5,
            std_dev_threshold=1.0,
            order_qty=10.0,
            sdk=self.sdk,
        )
        self.gateway.strategy_balances["STRAT_MEAN_REV_001"] = 100000.0

    def test_sdk_redis_connection_status(self):
        connected = self.sdk.connect_market_data_feed()
        self.assertTrue(connected)
        self.assertTrue(self.sdk.is_connected_to_redis)

    def test_mean_reversion_signal_buy_oversold(self):
        # Feed 5 ticks around 1200.0
        for p in [1200.0, 1201.0, 1199.0, 1200.0, 1200.0]:
            self.bot.on_tick(p)

        # Drop price sharply to 1180.0 (Oversold -> Price < Lower Band)
        intent = self.bot.on_tick(1180.0)
        self.assertIsNotNone(intent)
        self.assertEqual(intent.side, OrderSide.BUY)
        self.assertEqual(intent.qty, 10.0)
        self.assertEqual(intent.price, 1180.0)

        # Submit intent to Broker Gateway
        self.gateway.set_market_price("RELIANCE", 1180.0)
        res = self.gateway.process_order_intent(intent)
        self.assertEqual(res.status, OrderState.FILLED)

    def test_mean_reversion_signal_sell_overbought(self):
        # Feed 5 ticks around 1200.0
        for p in [1200.0, 1200.0, 1200.0, 1200.0, 1200.0]:
            self.bot.on_tick(p)

        # Spike price sharply to 1220.0 (Overbought -> Price > Upper Band)
        intent = self.bot.on_tick(1220.0)
        self.assertIsNotNone(intent)
        self.assertEqual(intent.side, OrderSide.SELL)
        self.assertEqual(intent.qty, 10.0)
        self.assertEqual(intent.price, 1220.0)

        # Submit intent to Broker Gateway
        self.gateway.set_market_price("RELIANCE", 1220.0)
        res = self.gateway.process_order_intent(intent)
        self.assertEqual(res.status, OrderState.FILLED)


if __name__ == "__main__":
    unittest.main()
