"""Quant Strategies Package."""

from quant.strategies.base import BaseStrategy, SignalType, StrategyDecision
from quant.strategies.registry import StrategyRegistry
from quant.strategies.sma_cross import SMACross
from quant.strategies.vwap_reversion import VWAPReversion
from quant.strategies.orb import OpeningRangeBreakout
from quant.strategies.buy_and_hold import BuyAndHold
from quant.strategies.donchian_breakout import DonchianBreakout
from quant.strategies.bollinger_reversion import BollingerReversion
from quant.strategies.volatility_squeeze import TTMSqueezeBreakout

__all__ = [
    "BaseStrategy",
    "SignalType",
    "StrategyDecision",
    "StrategyRegistry",
    "SMACross",
    "VWAPReversion",
    "OpeningRangeBreakout",
    "BuyAndHold",
    "DonchianBreakout",
    "BollingerReversion",
    "TTMSqueezeBreakout",
]
