"""
Unit & Integration Tests for QUANT-OS Stage 5 — Wave 2: The Auto-Tuner (Autonomous Optimization & Verification)
Verifies Pre-Deployment Simulation Proofs, Parameter Sweeps, Recommendation Verdicts, and Auto-Tuner Telemetry API Endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from oms_project.auto_tuner import AutoTuner, TuningVerificationResult
from oms_project.telemetry_api import app

client = TestClient(app)


def test_auto_tuner_verify_insight_recommendation():
    """Verifies that AutoTuner runs Time Machine backtest comparison between baseline and candidate config."""
    tuner = AutoTuner()
    base_config = {
        "strategy_id": "STRAT_TUNER_TEST",
        "strategy_type": "mean_reversion",
        "symbol": "RELIANCE",
        "parameters": {"window": 10, "threshold": 1.0},
        "risk_limits": {"max_qty": 10.0},
    }
    insight = {
        "insight_id": "INS_TEST_001",
        "strategy_id": "STRAT_TUNER_TEST",
        "category": "REGIME_LOSS",
        "severity": "HIGH",
        "headline": "Morning Loss Concentration",
        "message": "Concentrated morning losses detected.",
        "recommendation": "Suggest increasing threshold.",
        "confidence_score": 0.85,
    }

    res = tuner.verify_insight_recommendation(insight, base_config, initial_capital=100000.0)

    assert isinstance(res, TuningVerificationResult)
    assert res.strategy_id == "STRAT_TUNER_TEST"
    assert res.verdict in ("APPROVED_FOR_PROMOTION", "REJECTED_SUBOPTIMAL")
    assert "explanation" in res.model_dump()
    assert res.candidate_config["parameters"]["threshold"] == 1.5


def test_auto_tuner_auto_optimize_strategy():
    """Verifies that AutoTuner sweeps parameter grid and identifies top candidate configurations."""
    tuner = AutoTuner()
    base_config = {
        "strategy_id": "STRAT_GRID_TEST",
        "strategy_type": "mean_reversion",
        "symbol": "RELIANCE",
        "parameters": {"window": 10, "threshold": 1.5},
        "risk_limits": {"max_qty": 10.0},
    }

    res = tuner.auto_optimize_strategy(base_config, initial_capital=100000.0)

    assert res["strategy_id"] == "STRAT_GRID_TEST"
    assert res["total_grid_evaluations"] == 12  # 4 windows x 3 thresholds
    assert len(res["top_3_candidates"]) == 3
    assert res["best_candidate"] is not None


def test_auto_tuner_api_endpoints():
    """Tests POST /api/v1/tuner/verify-suggestion and POST /api/v1/tuner/auto-optimize API endpoints."""
    base_config = {
        "strategy_id": "STRAT_API_TUNER",
        "strategy_type": "mean_reversion",
        "symbol": "RELIANCE",
        "parameters": {"window": 10, "threshold": 1.2},
        "risk_limits": {"max_qty": 5.0},
    }
    insight = {
        "insight_id": "INS_API_001",
        "strategy_id": "STRAT_API_TUNER",
        "category": "SLIPPAGE_TOXICITY",
        "severity": "HIGH",
        "headline": "Toxic Slippage Detected",
        "message": "High slippage on fills.",
        "recommendation": "Reduce quantity.",
        "confidence_score": 0.88,
    }

    # 1. Verify suggestion endpoint
    v_resp = client.post("/api/v1/tuner/verify-suggestion", json={"insight": insight, "base_config": base_config})
    assert v_resp.status_code == 200
    v_data = v_resp.json()
    assert "verdict" in v_data
    assert "explanation" in v_data

    # 2. Auto-optimize endpoint
    o_resp = client.post("/api/v1/tuner/auto-optimize", json={"base_config": base_config})
    assert o_resp.status_code == 200
    o_data = o_resp.json()
    assert o_data["strategy_id"] == "STRAT_API_TUNER"
    assert len(o_data["top_3_candidates"]) == 3
