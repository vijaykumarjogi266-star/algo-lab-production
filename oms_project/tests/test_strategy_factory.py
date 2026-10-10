"""
Unit & Integration Tests for QUANT-OS Stage 4 — The Strategy Factory (Project STRAT-FACTORY)
Verifies Parameterized Strategy Blueprints, Schema Validation, Time Machine Fast-Tests,
Indian Statutory Friction Accounting, Sim-Lock Security, CIO Manager Allocation, and Factory API Endpoints.
"""

import os
import pytest
from fastapi.testclient import TestClient

from oms_project.schemas import OrderSide, OrderState
from oms_project.strategies.mean_reversion.mean_reversion_strat import MeanReversionStrategy
from oms_project.strategies.trend_following.trend_following_strat import TrendFollowingStrategy
from oms_project.strategy_factory import StrategyFactory, FastTestEngine, StrategyConfig
from oms_project.telemetry_api import app, ADMIN_BEARER_TOKEN, get_gateway, get_cio_manager

client = TestClient(app)


def test_strategy_factory_instantiation():
    """Verifies that StrategyFactory creates parameterized strategy instances from JSON configs."""
    mr_config = {
        "strategy_id": "STRAT_MR_TEST_001",
        "strategy_type": "mean_reversion",
        "symbol": "TATASTEEL",
        "parameters": {"window": 15, "threshold": 2.0},
        "risk_limits": {"max_qty": 25.0, "stop_loss_pct": 0.015},
    }
    mr_strat = StrategyFactory.instantiate(mr_config)
    assert isinstance(mr_strat, MeanReversionStrategy)
    assert mr_strat.strategy_id == "STRAT_MR_TEST_001"
    assert mr_strat.symbol == "TATASTEEL"
    assert mr_strat.window_size == 15
    assert mr_strat.std_dev_threshold == 2.0
    assert mr_strat.order_qty == 25.0

    tf_config = {
        "strategy_id": "STRAT_TF_TEST_001",
        "strategy_type": "trend_following",
        "symbol": "INFY",
        "parameters": {"short_window": 8, "long_window": 30},
        "risk_limits": {"max_qty": 12.0, "stop_loss_pct": 0.03},
    }
    tf_strat = StrategyFactory.instantiate(tf_config)
    assert isinstance(tf_strat, TrendFollowingStrategy)
    assert tf_strat.strategy_id == "STRAT_TF_TEST_001"
    assert tf_strat.symbol == "INFY"
    assert tf_strat.short_window == 8
    assert tf_strat.long_window == 30
    assert tf_strat.order_qty == 12.0


def test_blueprints_metadata_registry():
    """Verifies available blueprints registry metadata schema."""
    blueprints = StrategyFactory.get_registered_blueprints()
    assert "mean_reversion" in blueprints
    assert "trend_following" in blueprints
    assert "parameters_schema" in blueprints["mean_reversion"]
    assert "parameters_schema" in blueprints["trend_following"]


def test_fast_test_engine_execution_and_statutory_friction():
    """Runs a Fast-Test backtest simulation and verifies statutory cost accounting and zero variance."""
    config = {
        "strategy_id": "STRAT_FAST_TEST_SIM",
        "strategy_type": "mean_reversion",
        "symbol": "RELIANCE",
        "parameters": {"window": 10, "threshold": 1.2},
        "risk_limits": {"max_qty": 10.0},
    }

    res = FastTestEngine.run_fast_test(config, initial_capital=100000.0, slippage_bps=1.0)
    assert res["strategy_id"] == "STRAT_FAST_TEST_SIM"
    assert res["initial_capital"] == 100000.0
    assert "net_pnl" in res
    assert "max_drawdown_pct" in res
    assert "statutory_friction" in res

    f = res["statutory_friction"]
    assert f["brokerage"] >= 0.0
    assert f["stt"] >= 0.0
    assert f["exchange_txn_fee"] >= 0.0
    assert f["sebi_turnover_fee"] >= 0.0
    assert f["gst"] >= 0.0
    assert f["total_friction"] >= 0.0
    assert res["reconciliation_status"] == "MATCH"
    assert res["reconciliation_variance"] == 0.0


def test_sim_lock_security_guard(monkeypatch):
    """Verifies that Sim-Lock blocks fast-tests if ALLOW_LIVE_TRADING is set to True."""
    monkeypatch.setenv("ALLOW_LIVE_TRADING", "True")
    config = {"strategy_id": "STRAT_TEST", "strategy_type": "mean_reversion"}
    from oms_project.gateway import SafetyViolationError
    with pytest.raises(SafetyViolationError, match="CRITICAL: ALLOW_LIVE_TRADING must be 'false'"):
        FastTestEngine.run_fast_test(config)


def test_factory_telemetry_api_blueprints():
    """Tests GET /api/v1/factory/blueprints endpoint."""
    resp = client.get("/api/v1/factory/blueprints")
    assert resp.status_code == 200
    data = resp.json()
    assert "blueprints" in data
    assert "mean_reversion" in data["blueprints"]


def test_factory_telemetry_api_fast_test():
    """Tests POST /api/v1/factory/fast-test endpoint."""
    config = {
        "strategy_id": "STRAT_API_TEST",
        "strategy_type": "trend_following",
        "symbol": "RELIANCE",
        "parameters": {"short_window": 3, "long_window": 10},
        "risk_limits": {"max_qty": 5.0},
    }
    resp = client.post("/api/v1/factory/fast-test", json={"config": config, "initial_capital": 100000.0})
    assert resp.status_code == 200
    data = resp.json()
    assert data["strategy_id"] == "STRAT_API_TEST"
    assert "net_pnl" in data
    assert data["reconciliation_status"] == "MATCH"


def test_factory_telemetry_api_deploy_and_hot_reload():
    """Tests POST /api/v1/factory/deploy and POST /api/v1/factory/hot-reload workflow."""
    headers = {"Authorization": f"Bearer {ADMIN_BEARER_TOKEN}"}
    config = {
        "strategy_id": "STRAT_DEPLOY_001",
        "strategy_type": "mean_reversion",
        "symbol": "RELIANCE",
        "parameters": {"window": 20, "threshold": 1.5},
        "risk_limits": {"max_qty": 10.0},
        "allocation": {"initial_capital": 150000.0},
    }

    # 1. Deploy
    dep_resp = client.post("/api/v1/factory/deploy", json={"config": config}, headers=headers)
    assert dep_resp.status_code == 200
    dep_data = dep_resp.json()
    assert dep_data["success"] is True
    assert dep_data["strategy_id"] == "STRAT_DEPLOY_001"

    # Verify deployed strategies list
    list_resp = client.get("/api/v1/factory/deployed")
    assert list_resp.status_code == 200
    assert "STRAT_DEPLOY_001" in list_resp.json()["deployed_strategies"]

    # 2. Hot-Reload Parameters
    reload_resp = client.post(
        "/api/v1/factory/hot-reload",
        json={"strategy_id": "STRAT_DEPLOY_001", "parameters": {"window": 25, "threshold": 1.8}},
        headers=headers,
    )
    assert reload_resp.status_code == 200
    reload_data = reload_resp.json()
    assert reload_data["success"] is True
    assert reload_data["updated_parameters"]["window"] == 25
    assert reload_data["updated_parameters"]["threshold"] == 1.8
