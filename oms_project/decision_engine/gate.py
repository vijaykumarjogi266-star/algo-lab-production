from datetime import datetime, timezone
from decimal import Decimal
import uuid
from .models import MarketSnapshot, TechnicalSignalSet, PriceActionSignalSet, MarketRegimeAssessment, StrategyDecision, DecisionType, SessionPolicy, MarketMode
from .strategies import StrategyRegistry, BaseStrategy

class DecisionGate:
    def __init__(self, registry: StrategyRegistry, session_policy: SessionPolicy):
        self.registry = registry
        self.session_policy = session_policy
        
    def _parse_time(self, t_str: str) -> tuple:
        h, m = map(int, t_str.split(':'))
        return h, m
        
    def _is_after(self, dt: datetime, t_str: str) -> bool:
        h, m = self._parse_time(t_str)
        return dt.hour > h or (dt.hour == h and dt.minute >= m)
        
    def _is_before(self, dt: datetime, t_str: str) -> bool:
        return not self._is_after(dt, t_str)

    def evaluate(self, 
                 snapshot: MarketSnapshot, 
                 tech: TechnicalSignalSet, 
                 pa: PriceActionSignalSet, 
                 regime: MarketRegimeAssessment, 
                 strategy_id: str,
                 kill_switch_active: bool,
                 reconciliation_broken: bool,
                 oms_degraded: bool,
                 capital_sufficient: bool,
                 current_time_utc: datetime) -> StrategyDecision:
                 
        # 1. HALT_ALL checks
        if kill_switch_active:
            return StrategyDecision(DecisionType.HALT_ALL, strategy_id, None, None, None, None, None, 1.0, ["KILL_SWITCH_ACTIVE"], ["KILL_SWITCH"], ["CRITICAL_SAFETY"], regime.market_mode, str(uuid.uuid4()), current_time_utc)
        if oms_degraded:
            return StrategyDecision(DecisionType.HALT_ALL, strategy_id, None, None, None, None, None, 1.0, ["OMS_DEGRADED"], ["OMS_HEALTH"], ["CRITICAL_SAFETY"], regime.market_mode, str(uuid.uuid4()), current_time_utc)
            
        # Session checks
        is_hard_cutoff = self._is_after(current_time_utc, self.session_policy.hard_end_of_day_cutoff_time)
        is_mandatory_exit = self._is_after(current_time_utc, self.session_policy.mandatory_exit_cutoff_time)
        is_entry_cutoff = self._is_after(current_time_utc, self.session_policy.entry_cutoff_time)
        is_premarket = self._is_before(current_time_utc, self.session_policy.session_start_time)
        
        # 3. EXIT_ALL checks
        if is_hard_cutoff:
            return StrategyDecision(DecisionType.EXIT_ALL_INTENT, strategy_id, None, None, None, None, None, 1.0, ["HARD_CUTOFF_REACHED"], ["END_OF_DAY"], [], regime.market_mode, str(uuid.uuid4()), current_time_utc)
            
        # 2. HALT_NEW_ENTRIES checks
        if reconciliation_broken:
            return StrategyDecision(DecisionType.HALT_NEW_ENTRIES, strategy_id, None, None, None, None, None, 1.0, ["RECONCILIATION_BROKEN"], ["RECONCILIATION"], ["SAFETY_LIMIT"], regime.market_mode, str(uuid.uuid4()), current_time_utc)
        if snapshot.quality_status != "OK" or snapshot.data_freshness_seconds > 60:
            return StrategyDecision(DecisionType.HALT_NEW_ENTRIES, strategy_id, None, None, None, None, None, 1.0, ["MARKET_DATA_INVALID_OR_STALE"], ["DATA_QUALITY"], ["DATA_SAFETY"], regime.market_mode, str(uuid.uuid4()), current_time_utc)
        if is_premarket:
            return StrategyDecision(DecisionType.NO_TRADE, strategy_id, None, None, None, None, None, 1.0, ["PREMARKET"], ["SESSION_RULES"], [], regime.market_mode, str(uuid.uuid4()), current_time_utc)
        
        # Opening exclusion
        # Simplified: assume session start + mins
        start_h, start_m = self._parse_time(self.session_policy.session_start_time)
        start_mins = start_h * 60 + start_m
        curr_mins = current_time_utc.hour * 60 + current_time_utc.minute
        if curr_mins < start_mins + self.session_policy.opening_volatility_exclusion_mins:
            return StrategyDecision(DecisionType.NO_TRADE, strategy_id, None, None, None, None, None, 1.0, ["OPENING_EXCLUSION_WINDOW"], ["SESSION_RULES"], [], regime.market_mode, str(uuid.uuid4()), current_time_utc)
            
        # 4. REDUCE_ONLY checks
        if is_mandatory_exit:
            return StrategyDecision(DecisionType.REDUCE_ONLY_INTENT, strategy_id, None, None, None, None, None, 1.0, ["MANDATORY_EXIT_WINDOW"], ["END_OF_DAY"], [], regime.market_mode, str(uuid.uuid4()), current_time_utc)
            
        if is_entry_cutoff:
            return StrategyDecision(DecisionType.NO_TRADE, strategy_id, None, None, None, None, None, 1.0, ["ENTRY_CUTOFF_REACHED"], ["SESSION_RULES"], [], regime.market_mode, str(uuid.uuid4()), current_time_utc)
            
        if not capital_sufficient:
            return StrategyDecision(DecisionType.NO_TRADE, strategy_id, None, None, None, None, None, 1.0, ["INSUFFICIENT_CAPITAL"], ["CAPITAL"], [], regime.market_mode, str(uuid.uuid4()), current_time_utc)
            
        if regime.market_mode in [MarketMode.DATA_UNAVAILABLE, MarketMode.UNCERTAIN, MarketMode.HIGH_VOLATILITY, MarketMode.LOW_LIQUIDITY]:
            return StrategyDecision(DecisionType.NO_TRADE, strategy_id, None, None, None, None, None, 1.0, [f"UNSAFE_REGIME_{regime.market_mode.name}"], ["REGIME"], [], regime.market_mode, str(uuid.uuid4()), current_time_utc)
            
        strategy = self.registry.get_strategy(strategy_id)
        if not strategy:
            return StrategyDecision(DecisionType.NO_TRADE, strategy_id, None, None, None, None, None, 1.0, ["UNKNOWN_STRATEGY"], ["STRATEGY_POLICY"], [], regime.market_mode, str(uuid.uuid4()), current_time_utc)
            
        decision = strategy.evaluate(regime, tech, pa, snapshot.last_price)
        
        # Override strategy decision if it violates entry rules
        if decision.decision_type == DecisionType.CREATE_ORDER_INTENT:
            if decision.market_regime not in strategy.permitted_modes:
                return StrategyDecision(DecisionType.NO_TRADE, strategy_id, None, None, None, None, None, 1.0, ["STRATEGY_VIOLATED_REGIME_POLICY"], ["STRATEGY_POLICY"], [], regime.market_mode, str(uuid.uuid4()), current_time_utc)
                
        return decision

class DecisionEngine:
    def __init__(self, registry: StrategyRegistry, session_policy: SessionPolicy, classifier: MarketRegimeAssessment):
        self.registry = registry
        self.session_policy = session_policy
        self.classifier = classifier
        self.gate = DecisionGate(registry, session_policy)
        
    def evaluate(self, snapshot: MarketSnapshot, account_context: dict, portfolio_context: dict, system_context: dict, bars: list) -> StrategyDecision:
        from .technical_analysis import compute_technical_signals
        from .price_action import evaluate_price_action
        
        tech = compute_technical_signals(bars)
        pa = evaluate_price_action(bars)
        regime = self.classifier.classify(snapshot, tech, pa)
        
        current_time = snapshot.timestamp
        strategy_id = account_context.get("strategy_id", "BASE")
        kill_switch = system_context.get("kill_switch_active", False)
        oms_degraded = system_context.get("oms_degraded", False)
        reconciliation_broken = system_context.get("reconciliation_broken", False)
        capital_sufficient = account_context.get("capital_sufficient", True)
        
        return self.gate.evaluate(snapshot, tech, pa, regime, strategy_id, kill_switch, reconciliation_broken, oms_degraded, capital_sufficient, current_time)
