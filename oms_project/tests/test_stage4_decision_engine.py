"""
OMS Project - Stage 4: Decision Engine, Candidate Intents & Market Adaptability Test Suite
(test_stage4_decision_engine.py)

Comprehensive test coverage verifying:
1. Candidate Intent Lifecycle & Audit Trails (CANDIDATE -> RISK_APPROVED -> SIZED -> DISPATCHED).
2. Illegal state transition rejection (CandidateIntentTransitionError).
3. Market Adaptation Profiles & Transition Management:
   - Confirmation threshold (anti-whipsaw filter).
   - Immediate fail-closed emergency escalation (DEGRADED_DATA, HIGH_VOLATILITY).
   - Hysteresis cooldown on de-escalation from adverse regimes.
4. Fail-closed controls: DEGRADED_DATA strictly blocks new entries; allows REDUCE_ONLY.
5. Strategy Regime Gating: Incompatible strategy intents rejected with REJECTED_BY_REGIME.
6. Dynamic Risk Sizing under Adverse Regimes:
   - HIGH_VOLATILITY scalar sizing.
   - LOW_LIQUIDITY participation cap.
   - Excess risk/capital rejection (REJECTED_BY_RISK).
7. End-to-end integration with Stage 3 PaperExchange (execution matching, fills, position tracking).
8. End-to-end integration with Stage 2 ReplayClock and RegimeEvaluator.
"""

import time
import pytest
from decimal import Decimal

from oms_project.candidate_intent import (
    CandidateIntent,
    CandidateIntentState,
    IntentType,
    MarketAdaptationProfile,
    ProfileTransitionManager,
    Stage4DecisionEngine,
    CandidateIntentTransitionError,
    map_market_regime_to_profile,
)
from oms_project.paper_exchange import PaperExchange, AdverseExecutionProfile
from oms_project.deterministic_replay import ReplayClock, RegimeEvaluator, MarketRegime


def test_candidate_intent_lifecycle_and_audit_trail():
    """Verifies complete valid lifecycle from CANDIDATE -> RISK_APPROVED -> SIZED -> DISPATCHED with full audit trail."""
    intent = CandidateIntent(
        strategy_id="TREND_001",
        symbol="INFY",
        intent_type=IntentType.ENTRY_LONG,
        target_exposure=10.0,
        time_horizon="INTRADAY",
        max_slippage=0.002,
        rationale=["MOMENTUM_BREAKOUT"],
        regime_compatibility=["TRENDING", "NORMAL"],
        reference_price=1500.0,
    )

    assert intent.state == CandidateIntentState.CANDIDATE
    assert len(intent.audit_trail) == 1
    assert intent.audit_trail[0]["to_state"] == "CANDIDATE"

    # 1. Regime gate approval
    intent.transition(CandidateIntentState.RISK_APPROVED, "Regime gate approved under TRENDING")
    assert intent.state == CandidateIntentState.RISK_APPROVED
    assert len(intent.audit_trail) == 2

    # 2. Sizing
    intent.sized_qty = 10.0
    intent.transition(CandidateIntentState.SIZED, "Sized to 10.0 units")
    assert intent.state == CandidateIntentState.SIZED
    assert len(intent.audit_trail) == 3

    # 3. Dispatched
    intent.transition(
        CandidateIntentState.DISPATCHED,
        "Dispatched to paper exchange",
        {"order_id": "ORD_12345"},
    )
    assert intent.state == CandidateIntentState.DISPATCHED
    assert len(intent.audit_trail) == 4

    # Verify audit trail sequence
    trail_states = [entry["to_state"] for entry in intent.audit_trail]
    assert trail_states == ["CANDIDATE", "RISK_APPROVED", "SIZED", "DISPATCHED"]


def test_candidate_intent_illegal_transition_rejection():
    """Verifies that skipping states (e.g. CANDIDATE -> DISPATCHED) raises CandidateIntentTransitionError."""
    intent = CandidateIntent(
        strategy_id="STRAT_001",
        symbol="TCS",
        intent_type=IntentType.ENTRY_LONG,
        target_exposure=5.0,
    )

    # Cannot skip directly from CANDIDATE to DISPATCHED or SIZED
    with pytest.raises(CandidateIntentTransitionError):
        intent.transition(CandidateIntentState.DISPATCHED, "Illegal direct jump")

    with pytest.raises(CandidateIntentTransitionError):
        intent.transition(CandidateIntentState.SIZED, "Illegal jump without risk approval")

    # Move to REJECTED_BY_REGIME
    intent.transition(CandidateIntentState.REJECTED_BY_REGIME, "Regime unsuitable")
    assert intent.state == CandidateIntentState.REJECTED_BY_REGIME

    # Terminal states cannot transition further
    with pytest.raises(CandidateIntentTransitionError):
        intent.transition(CandidateIntentState.RISK_APPROVED, "Cannot revive rejected intent")


def test_profile_transition_confirmation_threshold():
    """Verifies confirmation threshold: single fluctuations do not alter profile until confirmed."""
    manager = ProfileTransitionManager(
        initial_profile=MarketAdaptationProfile.NORMAL,
        cooldown_seconds=60.0,
        confirmation_threshold=3,
    )

    now = 1000.0
    # First observation of TRENDING: does not flip yet
    prof, changed = manager.propose_profile(MarketAdaptationProfile.TRENDING, timestamp=now)
    assert prof == MarketAdaptationProfile.NORMAL
    assert not changed

    # Second observation of TRENDING: still pending
    prof, changed = manager.propose_profile(MarketAdaptationProfile.TRENDING, timestamp=now + 5)
    assert prof == MarketAdaptationProfile.NORMAL
    assert not changed

    # Interruption by CHOPPY resets counter
    prof, changed = manager.propose_profile(MarketAdaptationProfile.CHOPPY, timestamp=now + 10)
    assert prof == MarketAdaptationProfile.NORMAL
    assert not changed

    # 3 consecutive proposals of TRENDING now triggers transition
    manager.propose_profile(MarketAdaptationProfile.TRENDING, timestamp=now + 15)
    manager.propose_profile(MarketAdaptationProfile.TRENDING, timestamp=now + 20)
    prof, changed = manager.propose_profile(MarketAdaptationProfile.TRENDING, timestamp=now + 25)

    assert prof == MarketAdaptationProfile.TRENDING
    assert changed
    assert manager.current_profile == MarketAdaptationProfile.TRENDING


def test_profile_transition_emergency_fail_closed_escalation():
    """Verifies that critical risk profiles (DEGRADED_DATA, HIGH_VOLATILITY) escalate immediately without delay."""
    manager = ProfileTransitionManager(
        initial_profile=MarketAdaptationProfile.NORMAL,
        cooldown_seconds=60.0,
        confirmation_threshold=3,
    )

    now = 1000.0
    # Immediate transition to DEGRADED_DATA on single proposal
    prof, changed = manager.propose_profile(MarketAdaptationProfile.DEGRADED_DATA, timestamp=now)
    assert prof == MarketAdaptationProfile.DEGRADED_DATA
    assert changed

    # Immediate transition to HIGH_VOLATILITY
    prof, changed = manager.propose_profile(MarketAdaptationProfile.HIGH_VOLATILITY, timestamp=now + 10)
    assert prof == MarketAdaptationProfile.HIGH_VOLATILITY
    assert changed


def test_profile_transition_hysteresis_cooldown():
    """Verifies hysteresis cooldown: de-escalation from adverse states is blocked until cooldown period elapses."""
    manager = ProfileTransitionManager(
        initial_profile=MarketAdaptationProfile.NORMAL,
        cooldown_seconds=60.0,
        confirmation_threshold=3,
    )

    t0 = 1000.0
    # Escalate to HIGH_VOLATILITY
    manager.propose_profile(MarketAdaptationProfile.HIGH_VOLATILITY, timestamp=t0)
    assert manager.current_profile == MarketAdaptationProfile.HIGH_VOLATILITY

    # At t0 + 20s (cooldown is 60s), proposing NORMAL multiple times is suppressed
    for i in range(5):
        prof, changed = manager.propose_profile(MarketAdaptationProfile.NORMAL, timestamp=t0 + 20 + i)
        assert prof == MarketAdaptationProfile.HIGH_VOLATILITY
        assert not changed

    # At t0 + 65s (cooldown elapsed), proposing NORMAL 3 times now succeeds
    t_after_cooldown = t0 + 65.0
    manager.propose_profile(MarketAdaptationProfile.NORMAL, timestamp=t_after_cooldown)
    manager.propose_profile(MarketAdaptationProfile.NORMAL, timestamp=t_after_cooldown + 1)
    prof, changed = manager.propose_profile(MarketAdaptationProfile.NORMAL, timestamp=t_after_cooldown + 2)

    assert prof == MarketAdaptationProfile.NORMAL
    assert changed


def test_fail_closed_under_degraded_data():
    """Verifies fail-closed control: DEGRADED_DATA strictly blocks new entries while allowing REDUCE_ONLY."""
    manager = ProfileTransitionManager(initial_profile=MarketAdaptationProfile.DEGRADED_DATA)
    engine = Stage4DecisionEngine(transition_manager=manager)

    # 1. New entry intent is rejected
    entry_intent = CandidateIntent(
        strategy_id="STRAT_01",
        symbol="RELIANCE",
        intent_type=IntentType.ENTRY_LONG,
        target_exposure=10.0,
        regime_compatibility=["DEGRADED_DATA", "NORMAL"],
    )
    res_entry = engine.process_candidate_intent(entry_intent, current_price=2500.0)
    assert res_entry.state == CandidateIntentState.REJECTED_BY_REGIME
    assert "DEGRADED_DATA regime mandates NO_TRADE" in (res_entry.rejection_reason or "")

    # 2. Reduce-only exit intent is accepted and processed
    exit_intent = CandidateIntent(
        strategy_id="STRAT_01",
        symbol="RELIANCE",
        intent_type=IntentType.EXIT_LONG,
        target_exposure=10.0,
        reduce_only=True,
    )
    res_exit = engine.process_candidate_intent(
        exit_intent,
        current_price=2500.0,
        portfolio_positions={"RELIANCE": 10.0},
    )
    assert res_exit.state == CandidateIntentState.DISPATCHED
    assert res_exit.sized_qty == 10.0


def test_strategy_regime_gating():
    """Verifies that strategies are gated against incompatible market regimes."""
    manager = ProfileTransitionManager(initial_profile=MarketAdaptationProfile.CHOPPY)
    engine = Stage4DecisionEngine(transition_manager=manager)

    # Trend strategy in CHOPPY market -> REJECTED_BY_REGIME
    trend_intent = CandidateIntent(
        strategy_id="TREND_PULLBACK",
        symbol="INFY",
        intent_type=IntentType.ENTRY_LONG,
        target_exposure=10.0,
        regime_compatibility=["TRENDING"],
    )
    res_trend = engine.process_candidate_intent(trend_intent, current_price=1500.0)
    assert res_trend.state == CandidateIntentState.REJECTED_BY_REGIME
    assert "STRATEGY_INCOMPATIBLE" in (res_trend.rejection_reason or "")

    # Mean reversion strategy in CHOPPY market -> APPROVED & DISPATCHED
    mr_intent = CandidateIntent(
        strategy_id="RANGE_MEAN_REV",
        symbol="INFY",
        intent_type=IntentType.ENTRY_LONG,
        target_exposure=10.0,
        regime_compatibility=["CHOPPY"],
    )
    res_mr = engine.process_candidate_intent(mr_intent, current_price=1500.0)
    assert res_mr.state == CandidateIntentState.DISPATCHED
    assert res_mr.sized_qty == 10.0


def test_dynamic_risk_sizing_volatility_and_liquidity():
    """Verifies risk-adaptive sizing under HIGH_VOLATILITY and LOW_LIQUIDITY profiles."""
    # 1. HIGH_VOLATILITY: size scaled down by 50%
    manager_vol = ProfileTransitionManager(initial_profile=MarketAdaptationProfile.HIGH_VOLATILITY)
    engine_vol = Stage4DecisionEngine(
        transition_manager=manager_vol,
        volatility_sizing_scalar=0.5,
    )
    intent_vol = CandidateIntent(
        strategy_id="VOL_ADAPTIVE",
        symbol="HDFCBANK",
        intent_type=IntentType.ENTRY_LONG,
        target_exposure=20.0,
        regime_compatibility=["HIGH_VOLATILITY"],
    )
    res_vol = engine_vol.process_candidate_intent(intent_vol, current_price=1600.0)
    assert res_vol.state == CandidateIntentState.DISPATCHED
    assert res_vol.sized_qty == 10.0 # 20.0 * 0.5

    # 2. LOW_LIQUIDITY: size capped to low_liquidity_cap_qty (25.0)
    manager_liq = ProfileTransitionManager(initial_profile=MarketAdaptationProfile.LOW_LIQUIDITY)
    engine_liq = Stage4DecisionEngine(
        transition_manager=manager_liq,
        low_liquidity_cap_qty=25.0,
    )
    intent_liq = CandidateIntent(
        strategy_id="LIQ_ADAPTIVE",
        symbol="SMALLCAP",
        intent_type=IntentType.ENTRY_LONG,
        target_exposure=100.0,
        regime_compatibility=["LOW_LIQUIDITY"],
    )
    res_liq = engine_liq.process_candidate_intent(intent_liq, current_price=100.0)
    assert res_liq.state == CandidateIntentState.DISPATCHED
    assert res_liq.sized_qty == 25.0 # capped at 25.0


def test_risk_rejection_capital_and_portfolio_limits():
    """Verifies that intents exceeding risk and capital limits are rejected with REJECTED_BY_RISK."""
    manager = ProfileTransitionManager(initial_profile=MarketAdaptationProfile.NORMAL)
    engine = Stage4DecisionEngine(
        transition_manager=manager,
        max_capital_per_trade=50000.0,
        max_portfolio_exposure=100000.0,
    )

    # 1. Single trade value 60,000 exceeds max_capital_per_trade 50,000
    big_intent = CandidateIntent(
        strategy_id="BIG_TRADE",
        symbol="NIFTY",
        intent_type=IntentType.ENTRY_LONG,
        target_exposure=30.0,
        regime_compatibility=["NORMAL"],
    )
    res_big = engine.process_candidate_intent(big_intent, current_price=2000.0) # 30 * 2000 = 60,000
    assert res_big.state == CandidateIntentState.REJECTED_BY_RISK
    assert "CAPITAL_LIMIT_EXCEEDED" in (res_big.rejection_reason or "")

    # 2. Insufficient cash
    intent_cash = CandidateIntent(
        strategy_id="CASH_STRAT",
        symbol="NIFTY",
        intent_type=IntentType.ENTRY_LONG,
        target_exposure=10.0,
        regime_compatibility=["NORMAL"],
    )
    res_cash = engine.process_candidate_intent(
        intent_cash,
        current_price=2000.0,
        available_cash=15000.0, # Required 20,000 > 15,000
    )
    assert res_cash.state == CandidateIntentState.REJECTED_BY_RISK
    assert "INSUFFICIENT_CASH" in (res_cash.rejection_reason or "")

    # 3. Reduce-only with no open position
    intent_empty_exit = CandidateIntent(
        strategy_id="EXIT_STRAT",
        symbol="NIFTY",
        intent_type=IntentType.EXIT_LONG,
        target_exposure=10.0,
        reduce_only=True,
    )
    res_empty_exit = engine.process_candidate_intent(
        intent_empty_exit,
        current_price=2000.0,
        portfolio_positions={},
    )
    assert res_empty_exit.state == CandidateIntentState.REJECTED_BY_RISK
    assert "REDUCE_ONLY_REJECTED" in (res_empty_exit.rejection_reason or "")


def test_stage4_e2e_integration_with_paper_exchange():
    """Verifies complete end-to-end integration: CandidateIntent -> Engine -> Stage 3 PaperExchange fill."""
    paper_exch = PaperExchange(initial_cash=100000.0)
    manager = ProfileTransitionManager(initial_profile=MarketAdaptationProfile.TRENDING)
    engine = Stage4DecisionEngine(
        transition_manager=manager,
        paper_exchange=paper_exch,
    )

    intent = CandidateIntent(
        strategy_id="STRAT_E2E",
        symbol="RELIANCE",
        intent_type=IntentType.ENTRY_LONG,
        target_exposure=10.0,
        regime_compatibility=["TRENDING"],
    )

    res = engine.process_candidate_intent(intent, current_price=2000.0)
    assert res.state == CandidateIntentState.DISPATCHED
    assert res.dispatched_order_id is not None

    # Verify execution inside PaperExchange
    assert len(paper_exch.execution_history) == 1
    fill = paper_exch.execution_history[0]
    assert fill["symbol"] == "RELIANCE"
    assert fill["qty"] == 10.0
    assert fill["side"] == "BUY"
    assert paper_exch.positions["RELIANCE"] == 10.0


def test_stage4_replay_clock_and_regime_evaluator_integration():
    """Verifies integration with Stage 2 ReplayClock and RegimeEvaluator for dynamic profile updates."""
    evaluator = RegimeEvaluator(volatility_threshold=0.05, trend_threshold_pct=0.005)
    manager = ProfileTransitionManager(initial_profile=MarketAdaptationProfile.NORMAL)
    engine = Stage4DecisionEngine(
        transition_manager=manager,
        regime_evaluator=evaluator,
    )

    # 9:30 AM IST (regular session)
    clock = ReplayClock(initial_time=1704081600.0)
    clock.start()

    # Generate trending price history
    history = [
        {"timestamp": 1704081600.0 + i * 60, "price": 100.0 + (i * 0.5), "volume": 100.0}
        for i in range(25)
    ]
    current_tick = {"timestamp": 1704081600.0 + 25 * 60, "price": 112.5, "volume": 100.0}

    # Propose profile based on evaluation
    prof, regime = engine.update_market_regime(clock, history, current_tick)
    assert regime == MarketRegime.BULLISH_TREND
    # After multiple ticks, confirmed into TRENDING
    for _ in range(3):
        prof, regime = engine.update_market_regime(clock, history, current_tick)
    assert prof == MarketAdaptationProfile.TRENDING
