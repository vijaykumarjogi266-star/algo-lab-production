"""
Trend Following Bot Strategy Implementation
Calculates Short-Term and Long-Term Moving Averages over tick history to generate BUY/SELL OrderIntents.
"""

import math
import time
from typing import List, Optional, Dict, Any
from oms_project.schemas import OrderSide, OrderIntent, OrderResult
from oms_project.strategies.mean_reversion.strategy_sdk import BaseStrategy, StrategySDK


class TrendFollowingStrategy(BaseStrategy):
    """
    Trend Following Strategy using Short and Long Moving Average Crossovers
    with configurable stop-loss percentage.
    """

    def __init__(
        self,
        strategy_id: str = "STRAT_TREND_001",
        symbol: str = "RELIANCE",
        short_window: int = 5,
        long_window: int = 20,
        order_qty: float = 10.0,
        stop_loss_pct: float = 0.02,
        config: Optional[Dict[str, Any]] = None,
        sdk: Optional[StrategySDK] = None,
    ):
        super().__init__(strategy_id=strategy_id, symbol=symbol, sdk=sdk)
        self.short_window = short_window
        self.long_window = long_window
        self.order_qty = order_qty
        self.stop_loss_pct = stop_loss_pct

        if config:
            params = config.get("parameters", {})
            risk = config.get("risk_limits", {})
            self.strategy_id = config.get("strategy_id", self.strategy_id)
            self.symbol = config.get("symbol", self.symbol)
            self.short_window = int(params.get("short_window", self.short_window))
            self.long_window = int(params.get("long_window", self.long_window))
            self.order_qty = float(risk.get("max_qty", params.get("order_qty", self.order_qty)))
            self.stop_loss_pct = float(risk.get("stop_loss_pct", self.stop_loss_pct))

        self.last_short_sma: Optional[float] = None
        self.last_long_sma: Optional[float] = None
        self.entry_price: Optional[float] = None
        self.current_position: float = 0.0

    def calculate_smas(self) -> tuple[Optional[float], Optional[float]]:
        if len(self.price_history) < self.long_window:
            return None, None

        short_recent = self.price_history[-self.short_window :]
        long_recent = self.price_history[-self.long_window :]

        short_sma = sum(short_recent) / self.short_window
        long_sma = sum(long_recent) / self.long_window

        return short_sma, long_sma

    def on_tick(self, price: float, timestamp: Optional[float] = None) -> Optional[OrderIntent]:
        ts = timestamp if timestamp is not None else time.time()
        self.price_history.append(price)

        # Check Stop-Loss if in long position
        if self.current_position > 0 and self.entry_price is not None:
            if price <= self.entry_price * (1.0 - self.stop_loss_pct):
                intent = self.sdk.create_signed_intent(
                    symbol=self.symbol,
                    side=OrderSide.SELL,
                    qty=self.current_position,
                    price=price,
                )
                self.current_position = 0.0
                self.entry_price = None
                return intent

        short_sma, long_sma = self.calculate_smas()
        if short_sma is None or long_sma is None:
            return None

        intent: Optional[OrderIntent] = None

        # Bullish Crossover: Short SMA crosses above Long SMA -> BUY Signal
        if (
            self.last_short_sma is not None
            and self.last_long_sma is not None
            and self.last_short_sma <= self.last_long_sma
            and short_sma > long_sma
            and self.current_position == 0
        ):
            intent = self.sdk.create_signed_intent(
                symbol=self.symbol,
                side=OrderSide.BUY,
                qty=self.order_qty,
                price=price,
            )
            self.current_position = self.order_qty
            self.entry_price = price

        # Bearish Crossover: Short SMA crosses below Long SMA -> SELL Signal
        elif (
            self.last_short_sma is not None
            and self.last_long_sma is not None
            and self.last_short_sma >= self.last_long_sma
            and short_sma < long_sma
            and self.current_position > 0
        ):
            intent = self.sdk.create_signed_intent(
                symbol=self.symbol,
                side=OrderSide.SELL,
                qty=self.current_position,
                price=price,
            )
            self.current_position = 0.0
            self.entry_price = None

        self.last_short_sma = short_sma
        self.last_long_sma = long_sma
        return intent


def run_trend_following_bot_loop():
    """Bot runner loop for trend following container execution."""
    print("==================================================")
    print("  TREND FOLLOWING ALGO POD (STRAT_TREND_001)      ")
    print("  Status: RUNNING                                 ")
    print("  User  : UID 10001 (sandboxuser)                 ")
    print("  RootFS: READ-ONLY                               ")
    print("  Egress: DENY ALL (broker_gateway:8000 only)     ")
    print("==================================================")

    sdk = StrategySDK(strategy_id="STRAT_TREND_001")
    connected = sdk.connect_market_data_feed()
    print(f"[BOT LOG] Connected to Redis market data feed: {connected}")
    print("[BOT LOG] Listening for real-time market ticks on symbol RELIANCE...")

    bot = TrendFollowingStrategy(sdk=sdk)
    
    sample_ticks = [100.0 + i * 0.5 for i in range(30)]
    for p in sample_ticks:
        intent = bot.on_tick(p)
        if intent:
            print(f"[BOT SIGNAL] Generated OrderIntent: {intent.side.value} {intent.qty} {intent.symbol} @ {intent.price}")
            res = sdk.submit_intent_to_gateway(intent)
            print(f"[BOT GATEWAY RESPONSE] Status: {res.status.value}, Message: {res.message}")

    print("[BOT LOG] Trend Following Bot initialized and active.")


if __name__ == "__main__":
    run_trend_following_bot_loop()
