import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from oms_project.decision_engine.models import MarketBar, MarketSnapshot, SessionPolicy, MarketMode, DecisionType, StrategyStatus
from oms_project.decision_engine.regime_classifier import MarketRegimeClassifier
from oms_project.decision_engine.strategies import StrategyRegistry
from oms_project.decision_engine.gate import DecisionEngine

def test_data_quality_safety():
    classifier = MarketRegimeClassifier()
    registry = StrategyRegistry()
    session_policy = SessionPolicy("UTC", "09:30", "15:30", "15:45", "16:00", 15)
    engine = DecisionEngine(registry, session_policy, classifier)
    
    current_time = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    snapshot = MarketSnapshot(
        symbol="XYZ", timestamp=current_time, bars_by_timeframe={}, last_price=Decimal("100"), 
        last_price_timestamp=current_time, volume_metrics={"1d": Decimal("1000")}, spread_proxy=None, 
        data_source="mock", data_freshness_seconds=65, quality_status="OK"
    )
    
    # 65s freshness -> HALT_NEW_ENTRIES
    decision = engine.evaluate(snapshot, {"strategy_id": "BULL_PULLBACK"}, {}, {}, [])
    assert decision.decision_type == DecisionType.HALT_NEW_ENTRIES
    assert "MARKET_DATA_INVALID_OR_STALE" in decision.rationale

def test_bullish_regime():
    classifier = MarketRegimeClassifier(volatility_threshold=Decimal('0.5'))
    registry = StrategyRegistry()
    session_policy = SessionPolicy("UTC", "09:30", "15:30", "15:45", "16:00", 15)
    engine = DecisionEngine(registry, session_policy, classifier)
    
    current_time = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    bars = []
    base_price = 100
    for i in range(50):
        t = current_time - timedelta(minutes=50-i)
        bars.append(MarketBar("XYZ", "1m", Decimal(base_price+i), Decimal(base_price+i+1), Decimal(base_price+i), Decimal(base_price+i+1), Decimal("2000"), t, "mock"))
        
    snapshot = MarketSnapshot(
        symbol="XYZ", timestamp=current_time, bars_by_timeframe={"1m": bars}, last_price=Decimal("150"), 
        last_price_timestamp=current_time, volume_metrics={"1d": Decimal("5000")}, spread_proxy=None, 
        data_source="mock", data_freshness_seconds=0, quality_status="OK"
    )
    
    decision = engine.evaluate(snapshot, {"strategy_id": "BULL_PULLBACK"}, {}, {}, bars)
    assert decision.decision_type == DecisionType.CREATE_ORDER_INTENT
    assert decision.market_regime == MarketMode.BULLISH_TREND

def test_bearish_regime():
    classifier = MarketRegimeClassifier(volatility_threshold=Decimal('0.5'))
    registry = StrategyRegistry()
    session_policy = SessionPolicy("UTC", "09:30", "15:30", "15:45", "16:00", 15)
    engine = DecisionEngine(registry, session_policy, classifier)
    
    current_time = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    bars = []
    base_price = 100
    for i in range(50):
        t = current_time - timedelta(minutes=50-i)
        bars.append(MarketBar("XYZ", "1m", Decimal(base_price-i), Decimal(base_price-i), Decimal(base_price-i-1), Decimal(base_price-i-1), Decimal("2000"), t, "mock"))
        
    snapshot = MarketSnapshot(
        symbol="XYZ", timestamp=current_time, bars_by_timeframe={"1m": bars}, last_price=Decimal("50"), 
        last_price_timestamp=current_time, volume_metrics={"1d": Decimal("5000")}, spread_proxy=None, 
        data_source="mock", data_freshness_seconds=0, quality_status="OK"
    )
    
    decision = engine.evaluate(snapshot, {"strategy_id": "BEAR_PULLBACK"}, {}, {}, bars)
    assert decision.decision_type == DecisionType.CREATE_ORDER_INTENT
    assert decision.market_regime == MarketMode.BEARISH_TREND

def test_session_rules():
    classifier = MarketRegimeClassifier()
    registry = StrategyRegistry()
    session_policy = SessionPolicy("UTC", "09:30", "15:30", "15:45", "16:00", 15)
    engine = DecisionEngine(registry, session_policy, classifier)
    
    # Premarket
    current_time = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    snapshot = MarketSnapshot("XYZ", current_time, {}, Decimal("100"), current_time, {"1d": Decimal("1000")}, None, "mock", 0, "OK")
    decision = engine.evaluate(snapshot, {"strategy_id": "BULL_PULLBACK"}, {}, {}, [])
    assert decision.decision_type == DecisionType.NO_TRADE
    assert "PREMARKET" in decision.rationale
    
    # Opening exclusion
    current_time = datetime(2026, 1, 1, 9, 40, tzinfo=timezone.utc)
    snapshot = MarketSnapshot("XYZ", current_time, {}, Decimal("100"), current_time, {"1d": Decimal("1000")}, None, "mock", 0, "OK")
    decision = engine.evaluate(snapshot, {"strategy_id": "BULL_PULLBACK"}, {}, {}, [])
    assert decision.decision_type == DecisionType.NO_TRADE
    assert "OPENING_EXCLUSION_WINDOW" in decision.rationale
    
    # Hard cutoff
    current_time = datetime(2026, 1, 1, 16, 5, tzinfo=timezone.utc)
    snapshot = MarketSnapshot("XYZ", current_time, {}, Decimal("100"), current_time, {"1d": Decimal("1000")}, None, "mock", 0, "OK")
    decision = engine.evaluate(snapshot, {"strategy_id": "BULL_PULLBACK"}, {}, {}, [])
    assert decision.decision_type == DecisionType.EXIT_ALL_INTENT

def test_capital_oms_health_gates():
    classifier = MarketRegimeClassifier()
    registry = StrategyRegistry()
    session_policy = SessionPolicy("UTC", "09:30", "15:30", "15:45", "16:00", 15)
    engine = DecisionEngine(registry, session_policy, classifier)
    current_time = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    snapshot = MarketSnapshot("XYZ", current_time, {}, Decimal("100"), current_time, {"1d": Decimal("1000")}, None, "mock", 0, "OK")
    
    decision = engine.evaluate(snapshot, {}, {}, {"kill_switch_active": True}, [])
    assert decision.decision_type == DecisionType.HALT_ALL
    
    decision = engine.evaluate(snapshot, {}, {}, {"oms_degraded": True}, [])
    assert decision.decision_type == DecisionType.HALT_ALL
    
    decision = engine.evaluate(snapshot, {}, {}, {"reconciliation_broken": True}, [])
    assert decision.decision_type == DecisionType.HALT_NEW_ENTRIES
    
    decision = engine.evaluate(snapshot, {"capital_sufficient": False}, {}, {}, [])
    assert decision.decision_type == DecisionType.NO_TRADE

