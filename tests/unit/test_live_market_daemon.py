import pytest
import live_market_daemon

def test_live_trading_blocks_execution(monkeypatch):
    monkeypatch.setattr(live_market_daemon, 'ALLOW_LIVE_TRADING', True)
    with pytest.raises(RuntimeError, match="ALLOW_LIVE_TRADING is set to True"):
        live_market_daemon.enforce_safety_invariants()

def test_real_broker_blocks_execution(monkeypatch):
    monkeypatch.setattr(live_market_daemon, 'ALLOW_REAL_BROKER_EXECUTION', True)
    with pytest.raises(RuntimeError, match="ALLOW_REAL_BROKER_EXECUTION is set to True"):
        live_market_daemon.enforce_safety_invariants()
