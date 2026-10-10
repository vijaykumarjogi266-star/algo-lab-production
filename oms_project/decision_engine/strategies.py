from typing import List, Optional
from .models import MarketRegimeAssessment, MarketMode, TechnicalSignalSet, PriceActionSignalSet, StrategyDecision, DecisionType, StrategyStatus
from decimal import Decimal
import uuid
from datetime import datetime, timezone

class BaseStrategy:
    strategy_id: str = "BASE"
    version: str = "1.0"
    permitted_modes: List[MarketMode] = []
    status: StrategyStatus = StrategyStatus.APPROVED_FOR_INTERNAL_INTENTS
    
    def evaluate(self, regime: MarketRegimeAssessment, tech: TechnicalSignalSet, pa: PriceActionSignalSet, current_price: Decimal) -> StrategyDecision:
        raise NotImplementedError

class BullishTrendPullbackStrategy(BaseStrategy):
    strategy_id = "BULL_PULLBACK"
    permitted_modes = [MarketMode.BULLISH_TREND]
    
    def evaluate(self, regime: MarketRegimeAssessment, tech: TechnicalSignalSet, pa: PriceActionSignalSet, current_price: Decimal) -> StrategyDecision:
        if self.status == StrategyStatus.DISABLED:
            return StrategyDecision(DecisionType.NO_TRADE, self.strategy_id, None, None, None, None, None, 1.0, ["STRATEGY_DISABLED"], ["DISABLED"], [], regime.market_mode, str(uuid.uuid4()), datetime.now(timezone.utc))
            
        if regime.market_mode not in self.permitted_modes:
            return StrategyDecision(DecisionType.NO_TRADE, self.strategy_id, None, None, None, None, None, 1.0, ["REGIME_NOT_PERMITTED"], [f"MODE_{regime.market_mode.name}"], [], regime.market_mode, str(uuid.uuid4()), datetime.now(timezone.utc))
            
        # Require price above VWAP
        if tech.vwap and current_price < tech.vwap:
            return StrategyDecision(DecisionType.WAIT, self.strategy_id, "BUY", None, None, None, None, 0.5, ["WAITING_FOR_VWAP_RECLAIM"], ["PRICE_BELOW_VWAP"], [], regime.market_mode, str(uuid.uuid4()), datetime.now(timezone.utc))
            
        return StrategyDecision(
            DecisionType.CREATE_ORDER_INTENT,
            self.strategy_id,
            "BUY",
            Decimal("1.0"),
            current_price,
            current_price * Decimal("0.99"),
            current_price * Decimal("1.03"),
            0.8,
            ["BULLISH_TREND_CONFIRMED", "PRICE_ABOVE_VWAP"],
            [],
            [],
            regime.market_mode,
            str(uuid.uuid4()),
            datetime.now(timezone.utc)
        )

class BearishTrendPullbackStrategy(BaseStrategy):
    strategy_id = "BEAR_PULLBACK"
    permitted_modes = [MarketMode.BEARISH_TREND]
    
    def evaluate(self, regime: MarketRegimeAssessment, tech: TechnicalSignalSet, pa: PriceActionSignalSet, current_price: Decimal) -> StrategyDecision:
        if self.status == StrategyStatus.DISABLED:
            return StrategyDecision(DecisionType.NO_TRADE, self.strategy_id, None, None, None, None, None, 1.0, ["STRATEGY_DISABLED"], ["DISABLED"], [], regime.market_mode, str(uuid.uuid4()), datetime.now(timezone.utc))
            
        if regime.market_mode not in self.permitted_modes:
            return StrategyDecision(DecisionType.NO_TRADE, self.strategy_id, None, None, None, None, None, 1.0, ["REGIME_NOT_PERMITTED"], [f"MODE_{regime.market_mode.name}"], [], regime.market_mode, str(uuid.uuid4()), datetime.now(timezone.utc))
            
        # Require price below VWAP
        if tech.vwap and current_price > tech.vwap:
            return StrategyDecision(DecisionType.WAIT, self.strategy_id, "SELL", None, None, None, None, 0.5, ["WAITING_FOR_VWAP_REJECT"], ["PRICE_ABOVE_VWAP"], [], regime.market_mode, str(uuid.uuid4()), datetime.now(timezone.utc))
            
        return StrategyDecision(
            DecisionType.CREATE_ORDER_INTENT,
            self.strategy_id,
            "SELL",
            Decimal("1.0"),
            current_price,
            current_price * Decimal("1.01"),
            current_price * Decimal("0.97"),
            0.8,
            ["BEARISH_TREND_CONFIRMED", "PRICE_BELOW_VWAP"],
            [],
            [],
            regime.market_mode,
            str(uuid.uuid4()),
            datetime.now(timezone.utc)
        )

class RangeMeanReversionStrategy(BaseStrategy):
    strategy_id = "RANGE_MR"
    permitted_modes = [MarketMode.RANGE_BOUND]
    
    def evaluate(self, regime: MarketRegimeAssessment, tech: TechnicalSignalSet, pa: PriceActionSignalSet, current_price: Decimal) -> StrategyDecision:
        if regime.market_mode not in self.permitted_modes:
            return StrategyDecision(DecisionType.NO_TRADE, self.strategy_id, None, None, None, None, None, 1.0, ["REGIME_NOT_PERMITTED"], [f"MODE_{regime.market_mode.name}"], [], regime.market_mode, str(uuid.uuid4()), datetime.now(timezone.utc))
            
        return StrategyDecision(
            DecisionType.CREATE_ORDER_INTENT,
            self.strategy_id,
            "BUY",
            Decimal("1.0"),
            current_price,
            current_price * Decimal("0.99"),
            current_price * Decimal("1.02"),
            0.7,
            ["RANGE_BOUND_CONFIRMED"],
            [],
            [],
            regime.market_mode,
            str(uuid.uuid4()),
            datetime.now(timezone.utc)
        )

class IntradayExitManager(BaseStrategy):
    strategy_id = "EXIT_MANAGER"
    permitted_modes = [m for m in MarketMode] # All modes
    
    def evaluate(self, regime: MarketRegimeAssessment, tech: TechnicalSignalSet, pa: PriceActionSignalSet, current_price: Decimal) -> StrategyDecision:
        # Exit manager only proposes REDUCE_ONLY or EXIT_ALL, never entry
        return StrategyDecision(
            DecisionType.NO_TRADE, # By default it does nothing unless triggered by DecisionGate
            self.strategy_id,
            None, None, None, None, None, 1.0, [], [], [], regime.market_mode, str(uuid.uuid4()), datetime.now(timezone.utc)
        )

class StrategyRegistry:
    def __init__(self):
        self.strategies = {
            "BULL_PULLBACK": BullishTrendPullbackStrategy(),
            "BEAR_PULLBACK": BearishTrendPullbackStrategy(),
            "RANGE_MR": RangeMeanReversionStrategy(),
            "EXIT_MANAGER": IntradayExitManager()
        }
        
    def get_strategy(self, strategy_id: str) -> Optional[BaseStrategy]:
        return self.strategies.get(strategy_id)
