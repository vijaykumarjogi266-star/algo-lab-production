"""Unit Tests for Integrated Session Orchestrator (Work Package C)."""

import time
from services.common.health import ComponentOperationalState
from services.market_data.runner import DataSourceType
from services.orchestrator.session_orchestrator import SessionOrchestrator, SessionPhase


def test_session_orchestrator_lifecycle():
    orchestrator = SessionOrchestrator(
        session_name="Unit_Test_Orchestration",
        strategy_id="VWAP_REVERSION",
        universe=["SBIN", "RELIANCE"],
        initial_capital=500_000.0,
        source_type=DataSourceType.SIMULATED_MOCK,
        allow_diagnostic_simulation=True,
    )

    # 1. Pre-market initialization
    orchestrator.initialize_session()
    assert orchestrator.phase == SessionPhase.PRE_MARKET
    assert orchestrator.session is not None

    # 2. Market open
    orchestrator.start_market_session()
    assert orchestrator.phase == SessionPhase.MARKET_OPEN
    time.sleep(0.2)

    # 3. Intraday active
    orchestrator.transition_to_intraday()
    assert orchestrator.phase == SessionPhase.INTRADAY
    time.sleep(0.2)

    # 4. Market close & EOD reconciliation
    report = orchestrator.close_market_session()

    assert orchestrator.phase == SessionPhase.SHUTDOWN
    assert report.reconciliation_passed is True
    assert report.initial_capital == 500_000.0

    # 5. Check health observability
    health_sys = orchestrator.get_system_health()
    assert health_sys["phase"] == "SHUTDOWN"
    assert "DATA_FEED" in health_sys["subsystems"]
    assert "SESSION" in health_sys["subsystems"]
    assert "RECONCILIATION" in health_sys["subsystems"]
