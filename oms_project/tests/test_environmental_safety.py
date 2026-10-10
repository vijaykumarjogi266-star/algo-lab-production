import os
import pytest
from oms_project.gateway import BrokerGateway, SafetyViolationError

def test_missing_trading_mode(monkeypatch):
    monkeypatch.delenv("TRADING_MODE", raising=False)
    with pytest.raises(SafetyViolationError, match="TRADING_MODE must be READ_ONLY"):
        BrokerGateway()

def test_invalid_trading_mode(monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "LIVE")
    with pytest.raises(SafetyViolationError, match="TRADING_MODE must be READ_ONLY"):
        BrokerGateway()

def test_missing_allow_live_trading(monkeypatch):
    monkeypatch.delenv("ALLOW_LIVE_TRADING", raising=False)
    with pytest.raises(SafetyViolationError, match="ALLOW_LIVE_TRADING must be 'false'"):
        BrokerGateway()

def test_invalid_real_money_risk(monkeypatch):
    monkeypatch.setenv("REAL_MONEY_RISK_PAISE", "100")
    with pytest.raises(SafetyViolationError, match="REAL_MONEY_RISK_PAISE must be '0'"):
        BrokerGateway()

def test_execute_external_unconditionally_blocked(monkeypatch):
    gw = BrokerGateway()
    
    # 1. Calling with safe environment
    with pytest.raises(PermissionError, match="permanently disabled in Algo Lab"):
        gw.execute_external_broker_api_call("/test", {})

    # 2. Attempts to bypass via configuration variations remain rejected
    monkeypatch.setenv("ALLOW_REAL_BROKER_EXECUTION", "true")
    with pytest.raises(PermissionError, match="permanently disabled in Algo Lab"):
        gw.execute_external_broker_api_call("/test", {})

    monkeypatch.setenv("ALLOW_REAL_BROKER_EXECUTION", "True")
    with pytest.raises(PermissionError, match="permanently disabled in Algo Lab"):
        gw.execute_external_broker_api_call("/test", {})
        
    monkeypatch.setenv("ALLOW_REAL_BROKER_EXECUTION", "1")
    monkeypatch.setenv("ORDER_SUBMISSION_ENABLED", "true")
    monkeypatch.setenv("TRADING_MODE", "LIVE")
    # Even if they attempt to bypass, it must raise PermissionError
    with pytest.raises(PermissionError, match="permanently disabled in Algo Lab"):
        gw.execute_external_broker_api_call("/test", {})

    gw.simulation_mode = False
    with pytest.raises(PermissionError, match="permanently disabled in Algo Lab"):
        gw.execute_external_broker_api_call("/test", {})
