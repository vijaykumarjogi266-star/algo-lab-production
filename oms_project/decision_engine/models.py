from enum import Enum
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from decimal import Decimal
from datetime import datetime

class MarketMode(Enum):
    BULLISH_TREND = "BULLISH_TREND"
    BEARISH_TREND = "BEARISH_TREND"
    RANGE_BOUND = "RANGE_BOUND"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_LIQUIDITY = "LOW_LIQUIDITY"
    EVENT_RISK = "EVENT_RISK"
    UNCERTAIN = "UNCERTAIN"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"

class DecisionType(Enum):
    NO_TRADE = "NO_TRADE"
    WAIT = "WAIT"
    CREATE_ORDER_INTENT = "CREATE_ORDER_INTENT"
    REDUCE_ONLY_INTENT = "REDUCE_ONLY_INTENT"
    EXIT_ALL_INTENT = "EXIT_ALL_INTENT"
    HALT_NEW_ENTRIES = "HALT_NEW_ENTRIES"
    HALT_ALL = "HALT_ALL"

class StrategyStatus(Enum):
    DISABLED = "DISABLED"
    SHADOW = "SHADOW"
    APPROVED_FOR_INTERNAL_INTENTS = "APPROVED_FOR_INTERNAL_INTENTS"

@dataclass(frozen=True)
class MarketBar:
    symbol: str
    timeframe: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    timestamp: datetime
    source: str
    quality_flags: List[str] = field(default_factory=list)

@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    timestamp: datetime
    bars_by_timeframe: Dict[str, List[MarketBar]]
    last_price: Decimal
    last_price_timestamp: datetime
    volume_metrics: Dict[str, Decimal]
    spread_proxy: Optional[Decimal]
    data_source: str
    data_freshness_seconds: float
    quality_status: str

@dataclass(frozen=True)
class TechnicalSignalSet:
    trend_direction: int # 1 for up, -1 for down, 0 for neutral
    fast_ma: Optional[Decimal]
    slow_ma: Optional[Decimal]
    vwap: Optional[Decimal]
    rsi: Optional[Decimal]
    macd_line: Optional[Decimal]
    macd_signal: Optional[Decimal]
    macd_histogram: Optional[Decimal]
    atr: Optional[Decimal]
    bollinger_upper: Optional[Decimal]
    bollinger_lower: Optional[Decimal]
    relative_volume: Optional[Decimal]
    support_levels: List[Decimal] = field(default_factory=list)
    resistance_levels: List[Decimal] = field(default_factory=list)
    indicator_warnings: List[str] = field(default_factory=list)
    data_completeness: float = 1.0

@dataclass(frozen=True)
class PriceActionSignalSet:
    higher_highs: bool
    higher_lows: bool
    lower_highs: bool
    lower_lows: bool
    breakout_status: bool
    failed_breakout_status: bool
    support_proximity: bool
    resistance_proximity: bool
    range_expansion: bool
    volume_confirmation: bool
    confidence: float
    rationale: List[str] = field(default_factory=list)

@dataclass(frozen=True)
class MarketRegimeAssessment:
    market_mode: MarketMode
    confidence: float
    evidence: List[str]
    warnings: List[str]
    assessment_timestamp: datetime
    freshness_status: str

@dataclass(frozen=True)
class StrategyDecision:
    decision_type: DecisionType
    strategy_id: Optional[str]
    direction: Optional[str]
    proposed_qty: Optional[Decimal]
    reference_price: Optional[Decimal]
    stop_loss: Optional[Decimal]
    target: Optional[Decimal]
    confidence: float
    rationale: List[str]
    blocking_reasons: List[str]
    risk_warnings: List[str]
    market_regime: MarketMode
    correlation_id: str
    timestamp: datetime

@dataclass(frozen=True)
class SessionPolicy:
    market_timezone: str
    session_start_time: str # "HH:MM"
    entry_cutoff_time: str
    mandatory_exit_cutoff_time: str
    hard_end_of_day_cutoff_time: str
    opening_volatility_exclusion_mins: int
    midday_exclusion_start: Optional[str] = None
    midday_exclusion_end: Optional[str] = None
    no_overnight: bool = True
