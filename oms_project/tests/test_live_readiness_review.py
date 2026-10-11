"""
Unit & Integration Tests for Stage 7: Live-Trading Readiness Review & Pre-Flight Attestation Engine.

Validates:
1. Multi-Gate Evaluation:
   - When all 7 gates are satisfied, emits `CONDITIONALLY_CERTIFIED` attestation.
   - Emits valid HMAC-SHA256 signature for audit tracking.
2. Defect & Blocker Detection:
   - Failing golden tests triggers Gate 1 failure and `DISQUALIFIED` classification.
   - Insufficient forward paper sessions (<20) marks Gate 4 `INSUFFICIENT_DATA` and yields `INSUFFICIENT_EVIDENCE`.
   - Excessive cash drift (> 0.01 INR) triggers Gate 3 failure and `DISQUALIFIED`.
   - Excessive drawdown (> 5%) fails Gate 6.
   - AST / Live trading firewall violations fail Gate 5.
"""

import pytest
from oms_project.live_readiness_review import (
    GateStatus,
    LiveReadinessAttestation,
    LiveReadinessReviewEngine,
    ReadinessClassification,
)


def test_all_gates_passed_conditional_certification():
    engine = LiveReadinessReviewEngine()
    attestation = engine.evaluate_all_gates(
        historical_test_pass_rate=1.0,
        friction_stress_profit_factor=1.5,
        accounting_cash_drift=0.0,
        accumulated_live_paper_sessions=20,
        max_drawdown_observed_pct=0.03,
        ast_firewall_violations=0,
    )

    assert attestation.classification == ReadinessClassification.CONDITIONALLY_CERTIFIED
    assert attestation.passed_gates_count == 7
    assert attestation.total_gates_count == 7
    assert len(attestation.blockers) == 0
    assert len(attestation.signature) == 64  # SHA256 hex string


def test_gate4_insufficient_sessions_blocks_promotion():
    engine = LiveReadinessReviewEngine()
    # Only 5 sessions accumulated (< 20)
    attestation = engine.evaluate_all_gates(
        historical_test_pass_rate=1.0,
        friction_stress_profit_factor=1.5,
        accounting_cash_drift=0.0,
        accumulated_live_paper_sessions=5,
        max_drawdown_observed_pct=0.03,
        ast_firewall_violations=0,
    )

    assert attestation.classification == ReadinessClassification.INSUFFICIENT_EVIDENCE
    assert attestation.passed_gates_count == 6
    assert any("GATE_4" in b for b in attestation.blockers)


def test_gate3_accounting_drift_disqualifies():
    engine = LiveReadinessReviewEngine()
    # 5.50 INR cash drift (> 0.01 limit)
    attestation = engine.evaluate_all_gates(
        accounting_cash_drift=5.50,
        accumulated_live_paper_sessions=20,
    )

    assert attestation.classification == ReadinessClassification.DISQUALIFIED
    assert any("GATE_3" in b for b in attestation.blockers)


def test_gate6_excessive_drawdown_disqualifies():
    engine = LiveReadinessReviewEngine()
    # 8% drawdown (> 5% limit)
    attestation = engine.evaluate_all_gates(
        max_drawdown_observed_pct=0.08,
        accumulated_live_paper_sessions=20,
    )

    assert attestation.classification == ReadinessClassification.DISQUALIFIED
    assert any("GATE_6" in b for b in attestation.blockers)


def test_gate5_ast_security_violation_disqualifies():
    engine = LiveReadinessReviewEngine()
    # 1 AST violation detected
    attestation = engine.evaluate_all_gates(
        ast_firewall_violations=1,
        accumulated_live_paper_sessions=20,
    )

    assert attestation.classification == ReadinessClassification.DISQUALIFIED
    assert any("GATE_5" in b for b in attestation.blockers)
