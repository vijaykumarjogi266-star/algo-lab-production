"""
OMS Project - Hybrid Alpha Strategy Implementation (hybrid_alpha_strat.py)
Combines Mean Reversion and Trend Following strategy logic, dynamically switching
regimes based on rolling volatility calculation.
"""

import math
import time
from typing import List, Optional, Dict, Any
from oms_project.schemas import OrderSide, OrderIntent, OrderResult
from oms_project.strategies.mean_reversion.strategy_sdk import BaseStrategy, StrategySDK
from oms_project.strategies.mean_reversion.mean_reversion_strat import MeanReversionStrategy
from oms_project.strategies.trend_following.trend_following_strat import TrendFollowingStrategy


class HybridAlphaStrategy(BaseStrategy):
    """
    Hybrid Alpha Strategy:
    - Low Volatility Regime (< threshold): Mean Reversion Logic
    - High Volatility Regime (> threshold): Trend Following Logic
    - Dynamic Conviction Score Blending based on regime strength.
    """

    def __init__(
        self,
        strategy_id: str = "STRAT_HYBRID_001",
        symbol: str = "RELIANCE",
        volatility_window: int = 10,
        volatility_threshold: float = 0.01,  # 1.0% volatility threshold
        config: Optional[Dict[str, Any]] = None,
        sdk: Optional[StrategySDK] = None,
    ):
        super().__init__(strategy_id=strategy_id, symbol=symbol, sdk=sdk)
        self.volatility_window = volatility_window
        self.volatility_threshold = volatility_threshold

        # Initialize component strategies
        self.mean_rev_bot = MeanReversionStrategy(
            strategy_id=strategy_id, symbol=symbol, sdk=self.sdk, config=config
        )
        self.trend_bot = TrendFollowingStrategy(
            strategy_id=strategy_id, symbol=symbol, sdk=self.sdk, config=config
        )

        if config:
            params = config.get("parameters", {})
            self.volatility_window = int(params.get("volatility_window", self.volatility_window))
            self.volatility_threshold = float(params.get("volatility_threshold", self.volatility_threshold))

        self.current_regime: str = "LOW_VOLATILITY"  # "LOW_VOLATILITY" or "HIGH_VOLATILITY"
        self.current_volatility: float = 0.0

    def calculate_volatility(self) -> float:
        """Calculates normalized rolling volatility (standard deviation of returns / mean price)."""
        if len(self.price_history) < self.volatility_window:
            return 0.0

        recent = self.price_history[-self.volatility_window :]
        mean = sum(recent) / len(recent)
        if mean <= 0:
            return 0.0

        variance = sum((p - mean) ** 2 for p in recent) / len(recent)
        std_dev = math.sqrt(variance)
        return std_dev / mean

    def get_conviction(self) -> float:
        """
        Returns conviction score weighted by regime strength.
        """
        vol = self.current_volatility
        if vol <= 0:
            return 0.5

        if self.current_regime == "LOW_VOLATILITY":
            regime_strength = max(0.5, 1.0 - (vol / max(0.0001, self.volatility_threshold)))
            base_conviction = self.mean_rev_bot.get_conviction()
        else:
            regime_strength = min(1.0, vol / max(0.0001, self.volatility_threshold))
            base_conviction = self.trend_bot.get_conviction()

        self.conviction = base_conviction * regime_strength
        return max(0.0, min(1.0, float(self.conviction)))

    def on_tick(self, price: float, timestamp: Optional[float] = None) -> Optional[OrderIntent]:
        ts = timestamp if timestamp is not None else time.time()
        self.price_history.append(price)

        # Compute current volatility
        self.current_volatility = self.calculate_volatility()

        # Regime Switching Logic
        if self.current_volatility >= self.volatility_threshold:
            self.current_regime = "HIGH_VOLATILITY"
            self.trend_bot.price_history = list(self.price_history[:-1])
            self.mean_rev_bot.price_history = list(self.price_history)
            intent = self.trend_bot.on_tick(price, timestamp=ts)
        else:
            self.current_regime = "LOW_VOLATILITY"
            self.mean_rev_bot.price_history = list(self.price_history[:-1])
            self.trend_bot.price_history = list(self.price_history)
            intent = self.mean_rev_bot.on_tick(price, timestamp=ts)

        return intent

