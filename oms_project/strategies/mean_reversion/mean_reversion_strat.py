"""
Mean Reversion Bot Strategy Implementation
Calculates SMA and Bollinger Bands over tick history to generate BUY/SELL OrderIntents.
"""

import math
import time
from typing import List, Optional, Dict, Any
from oms_project.schemas import OrderSide, OrderIntent, OrderResult
from oms_project.strategies.mean_reversion.strategy_sdk import BaseStrategy, StrategySDK


class MeanReversionStrategy(BaseStrategy):
    """
    Mean Reversion Strategy using Simple Moving Average (SMA)
    and Bollinger Bands (std_dev threshold).
    """

    def __init__(
        self,
        strategy_id: str = "STRAT_MEAN_REV_001",
        symbol: str = "RELIANCE",
        window_size: int = 10,
        std_dev_threshold: float = 1.5,
        order_qty: float = 10.0,
        stop_loss_pct: float = 0.02,
        config: Optional[Dict[str, Any]] = None,
        sdk: Optional[StrategySDK] = None,
    ):
        super().__init__(strategy_id=strategy_id, symbol=symbol, sdk=sdk)
        self.window_size = window_size
        self.std_dev_threshold = std_dev_threshold
        self.order_qty = order_qty
        self.stop_loss_pct = stop_loss_pct

        if config:
            params = config.get("parameters", {})
            risk = config.get("risk_limits", {})
            self.strategy_id = config.get("strategy_id", self.strategy_id)
            self.symbol = config.get("symbol", self.symbol)
            self.window_size = int(params.get("window", params.get("window_size", self.window_size)))
            self.std_dev_threshold = float(params.get("threshold", params.get("std_dev_threshold", self.std_dev_threshold)))
            self.order_qty = float(risk.get("max_qty", params.get("order_qty", self.order_qty)))
            self.stop_loss_pct = float(risk.get("stop_loss_pct", self.stop_loss_pct))

    def calculate_sma_and_bands(self) -> tuple[Optional[float], Optional[float], Optional[float]]:
        if len(self.price_history) < self.window_size:
            return None, None, None

        recent = self.price_history[-self.window_size:]
        sma = sum(recent) / self.window_size
        variance = sum((p - sma) ** 2 for p in recent) / self.window_size
        std_dev = math.sqrt(variance)

        upper_band = sma + (self.std_dev_threshold * std_dev)
        lower_band = sma - (self.std_dev_threshold * std_dev)
        return sma, upper_band, lower_band

    def on_tick(self, price: float, timestamp: Optional[float] = None) -> Optional[OrderIntent]:
        ts = timestamp if timestamp is not None else time.time()
        self.price_history.append(price)

        sma, upper_band, lower_band = self.calculate_sma_and_bands()
        if sma is None or upper_band is None or lower_band is None:
            return None

        # Mean Reversion Signal Generation:
        # 1. Price below lower band -> Oversold -> Generate BUY OrderIntent
        if price < lower_band:
            intent = self.sdk.create_signed_intent(
                symbol=self.symbol,
                side=OrderSide.BUY,
                qty=self.order_qty,
                price=price,
            )
            return intent

        # 2. Price above upper band -> Overbought -> Generate SELL OrderIntent
        elif price > upper_band:
            intent = self.sdk.create_signed_intent(
                symbol=self.symbol,
                side=OrderSide.SELL,
                qty=self.order_qty,
                price=price,
            )
            return intent

        return None


def run_mean_reversion_bot_loop():
    """Bot runner loop for container execution."""
    print("==================================================")
    print("  MEAN REVERSION ALGO POD (STRAT_MEAN_REV_001)   ")
    print("  Status: RUNNING                                 ")
    print("  User  : UID 10001 (sandboxuser)                 ")
    print("  RootFS: READ-ONLY                               ")
    print("  Egress: DENY ALL (broker_gateway:8000 only)     ")
    print("==================================================")

    sdk = StrategySDK(strategy_id="STRAT_MEAN_REV_001")
    connected = sdk.connect_market_data_feed()
    print(f"[BOT LOG] Connected to Redis market data feed: {connected}")
    print("[BOT LOG] Listening for real-time market ticks on symbol RELIANCE...")

    bot = MeanReversionStrategy(sdk=sdk)
    
    # Warmup tick series
    sample_ticks = [1200.0, 1201.0, 1199.5, 1200.5, 1202.0, 1198.0, 1197.0, 1195.0, 1193.0, 1190.0, 1185.0]
    for p in sample_ticks:
        intent = bot.on_tick(p)
        if intent:
            print(f"[BOT SIGNAL] Generated OrderIntent: {intent.side.value} {intent.qty} {intent.symbol} @ {intent.price}")
            res = sdk.submit_intent_to_gateway(intent)
            print(f"[BOT GATEWAY RESPONSE] Status: {res.status.value}, Message: {res.message}")

    print("[BOT LOG] Mean Reversion Bot initialized and active.")


if __name__ == "__main__":
    run_mean_reversion_bot_loop()
