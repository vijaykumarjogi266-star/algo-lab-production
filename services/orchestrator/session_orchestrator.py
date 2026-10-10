"""Integrated Session Orchestrator (Work Package C).

Binds:
SESSION CLOCK → MARKET DATA RUNNER → SCANNER → STRATEGY → RISK → PAPER EXECUTION → PERSISTENCE → EOD

Adheres to Requirements:
- Non-negotiable safety check: ALLOW_LIVE_TRADING = False, ALLOW_REAL_BROKER_EXECUTION = False
- Operational lifecycle: PRE-MARKET → MARKET OPEN → INTRADAY → MARKET CLOSE → EOD → SHUTDOWN
- Observability: Exposes SubsystemHealth across all 9 components:
  DATA_FEED, SESSION, SCANNER, STRATEGY, RISK, PAPER_EXECUTION, ACCOUNTING, PERSISTENCE, RECONCILIATION
- Health states: STARTING, RUNNING, DEGRADED, STOPPING, STOPPED, ERROR
- Safe failure handling: Feed disconnect detection, stale data protection, fail-closed solvency
- EOD reconciliation package integration
"""

import logging
import threading
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from apps.api.core.config import settings
from data.schemas.canonical_market_data import CanonicalMarketDataBar
from services.backtest_engine.execution_lifecycle import OrderSide
from services.common.health import ComponentName, ComponentOperationalState, SubsystemHealth
from services.market_data.adapters.market_event_schemas import MarketTickEvent
from services.market_data.runner import DataSourceType, RealTimeMarketDataRunner
from services.paper_engine.session import PaperSession, PaperTradingEngine, SessionStatus
from services.reconciliation.eod import EODReconciliationReport, EODReconciler
from services.risk_engine.contracts import HardRiskLimits
from services.risk_engine.engine import RiskEngine
from services.scanner.engine import MultiSymbolScannerEngine

logger = logging.getLogger(__name__)


class SessionPhase(str, Enum):
    PRE_MARKET = "PRE_MARKET"
    MARKET_OPEN = "MARKET_OPEN"
    INTRADAY = "INTRADAY"
    MARKET_CLOSE = "MARKET_CLOSE"
    EOD_RECONCILIATION = "EOD_RECONCILIATION"
    SHUTDOWN = "SHUTDOWN"


class SessionOrchestrator:
    """Thread-safe master controller binding all microservices into a single paper trading loop."""

    def __init__(
        self,
        session_name: str = "Realtime_Paper_Session_01",
        strategy_id: str = "MULTI_STRATEGY_EQUITY",
        universe: Optional[List[str]] = None,
        initial_capital: float = 1_000_000.0,
        source_type: DataSourceType = DataSourceType.SIMULATED_MOCK,
        bar_interval_seconds: int = 60,
        allow_diagnostic_simulation: bool = False,
    ):
        self._lock = threading.RLock()
        self.session_name = session_name
        self.strategy_id = strategy_id
        self.universe = [s.upper().strip() for s in (universe or ["SBIN", "RELIANCE", "TCS"])]
        self.initial_capital = initial_capital
        self.source_type = source_type
        self.bar_interval_seconds = bar_interval_seconds
        self.allow_diagnostic_simulation = allow_diagnostic_simulation

        # Operational phase
        self.phase = SessionPhase.PRE_MARKET

        # Core Components
        self.paper_engine = PaperTradingEngine(db_path=":memory:")
        self.session: Optional[PaperSession] = None

        self.runner = RealTimeMarketDataRunner(
            source_type=source_type,
            symbols=self.universe,
            bar_interval_seconds=bar_interval_seconds,
            allow_diagnostic_simulation=allow_diagnostic_simulation,
        )

        self.scanner = MultiSymbolScannerEngine(universe=self.universe)
        self.risk_engine = RiskEngine(limits=HardRiskLimits())
        self.reconciler = EODReconciler()

        # Component Observability Registry
        self.subsystem_health: Dict[ComponentName, SubsystemHealth] = {
            ComponentName.DATA_FEED: self.runner.health,
            ComponentName.SESSION: SubsystemHealth(component_name=ComponentName.SESSION),
            ComponentName.SCANNER: self.scanner.scanner_health,
            ComponentName.STRATEGY: self.scanner.strategy_health,
            ComponentName.RISK: SubsystemHealth(component_name=ComponentName.RISK),
            ComponentName.PAPER_EXECUTION: SubsystemHealth(component_name=ComponentName.PAPER_EXECUTION),
            ComponentName.ACCOUNTING: SubsystemHealth(component_name=ComponentName.ACCOUNTING),
            ComponentName.PERSISTENCE: SubsystemHealth(component_name=ComponentName.PERSISTENCE),
            ComponentName.RECONCILIATION: self.reconciler.health,
        }

        # Last EOD report
        self.last_eod_report: Optional[EODReconciliationReport] = None

    # =========================================================================
    # PRE-MARKET INITIALIZATION & WIREUP
    # =========================================================================

    def initialize_session(self):
        """PRE-MARKET: Enforces safety locks and wires up event handlers."""
        with self._lock:
            # 1. Non-Negotiable Safety Lock Verification
            if settings.ALLOW_LIVE_TRADING or settings.ALLOW_REAL_BROKER_EXECUTION:
                self.subsystem_health[ComponentName.SESSION].update_state(
                    ComponentOperationalState.ERROR,
                    "SAFETY LOCK BREACH DETECTED: ALLOW_LIVE_TRADING or ALLOW_REAL_BROKER_EXECUTION is True!",
                )
                raise PermissionError("SAFETY LOCK BREACH DETECTED: Execution halted fail-closed.")

            # 2. Create Paper Session
            self.session = self.paper_engine.create_session(
                name=self.session_name,
                strategy_id=self.strategy_id,
                universe=self.universe,
                initial_capital=self.initial_capital,
            )

            # 3. Wire Runner -> Scanner & Paper Portfolio Mark-to-Market
            self.runner.subscribe_ticks(self._on_tick)
            self.runner.subscribe_bars(self._on_bar)

            # 4. Wire Scanner Candidates -> Risk -> Paper Execution
            self.scanner.subscribe_candidates(self._on_candidate)

            # Update initial health states
            self.phase = SessionPhase.PRE_MARKET
            self.subsystem_health[ComponentName.SESSION].update_state(
                ComponentOperationalState.STARTING,
                f"Session '{self.session.session_id}' initialized in PRE_MARKET phase",
            )
            self.subsystem_health[ComponentName.RISK].update_state(
                ComponentOperationalState.RUNNING,
                "Independent Risk Engine active with 1.0x leverage lock",
            )
            self.subsystem_health[ComponentName.PAPER_EXECUTION].update_state(
                ComponentOperationalState.RUNNING,
                f"Paper Execution active with initial cash INR {self.initial_capital:,.2f}",
            )
            self.subsystem_health[ComponentName.ACCOUNTING].update_state(
                ComponentOperationalState.RUNNING,
                "Double-entry paper ledger online",
            )
            self.subsystem_health[ComponentName.PERSISTENCE].update_state(
                ComponentOperationalState.RUNNING,
                "SQLite session state persistence online",
            )

    # =========================================================================
    # LIFECYCLE EXECUTION METHODS
    # =========================================================================

    def start_market_session(self):
        """MARKET OPEN: Begins processing market stream data."""
        with self._lock:
            if not self.session:
                self.initialize_session()

            self.paper_engine.start_session(self.session.session_id)
            self.runner.start()
            self.phase = SessionPhase.MARKET_OPEN
            self.subsystem_health[ComponentName.SESSION].update_state(
                ComponentOperationalState.RUNNING,
                f"Market session '{self.session.session_id}' RUNNING",
            )

    def transition_to_intraday(self):
        """INTRADAY: Transition into active scanning and monitoring window."""
        with self._lock:
            self.phase = SessionPhase.INTRADAY
            self.subsystem_health[ComponentName.SESSION].update_state(
                ComponentOperationalState.RUNNING,
                "INTRADAY active processing mode",
            )

    def close_market_session(self) -> EODReconciliationReport:
        """MARKET CLOSE & EOD RECONCILIATION: Flushes bars, reconciles ledger, produces audit package."""
        with self._lock:
            self.phase = SessionPhase.MARKET_CLOSE
            self.subsystem_health[ComponentName.SESSION].update_state(
                ComponentOperationalState.STOPPING,
                "MARKET_CLOSE: Halting new setups & flushing bars...",
            )

            # Stop data runner
            self.runner.stop()

            # Stop paper session
            if self.session:
                self.paper_engine.stop_session(self.session.session_id)

            # EOD RECONCILIATION
            self.phase = SessionPhase.EOD_RECONCILIATION
            report = self.reconciler.reconcile_session(
                session=self.session,
                provenance=self.runner.provenance,
                pipeline_telemetry=self.runner.pipeline.get_pipeline_telemetry(),
                scanner_telemetry={
                    "bars_scanned": self.scanner.bars_scanned,
                    "candidates_generated": self.scanner.candidates_generated,
                },
            )
            self.last_eod_report = report

            # SHUTDOWN
            self.phase = SessionPhase.SHUTDOWN
            self.subsystem_health[ComponentName.SESSION].update_state(
                ComponentOperationalState.STOPPED,
                f"Session closed cleanly. EOD Reconciliation: {'PASSED' if report.reconciliation_passed else 'FAILED'}",
                metrics={"reconciliation_passed": report.reconciliation_passed, "evidence_hash": report.evidence_hash},
            )

            return report

    # =========================================================================
    # EVENT HANDLERS & INTEGRATED PIPELINE DISPATCH
    # =========================================================================

    def _on_tick(self, tick: MarketTickEvent):
        """Process incoming tick for position mark-to-market."""
        if not self.session or self.session.status != SessionStatus.RUNNING:
            return
        
        # Mark active paper positions to market
        self.session.portfolio.mark_to_market({tick.symbol: tick.last_traded_price})

    def _on_bar(self, bar: CanonicalMarketDataBar):
        """Process incoming canonical bar through multi-symbol scanner engine."""
        if not self.session or self.session.status != SessionStatus.RUNNING:
            return
        
        # Sync current open positions with scanner to prevent duplicate entries
        self.scanner.set_open_positions(list(self.session.portfolio.positions.keys()))
        self.scanner.process_bar(bar)

    def _on_candidate(self, candidate: Any):
        """
        Receives candidate proposal from scanner, evaluates against RiskEngine,
        and submits approved orders to PaperTradingEngine.
        """
        if not self.session or self.session.status != SessionStatus.RUNNING:
            return

        sym = candidate.symbol
        price = candidate.suggested_limit_price or 100.0
        stop_loss = candidate.suggested_stop_loss

        # Calculate proposed quantity (e.g. 5% max capital per trade)
        max_trade_val = self.session.portfolio.total_equity * 0.05
        proposed_qty = max(1, int(max_trade_val / price))

        # 1. Evaluate against independent RiskEngine
        risk_res = self.risk_engine.evaluate(
            symbol=sym,
            price=price,
            proposed_quantity=proposed_qty,
            stop_loss=stop_loss,
            current_portfolio_value=self.session.portfolio.total_equity,
            current_daily_loss_pct=0.0,
            current_drawdown_pct=self.session.portfolio.max_drawdown_pct,
            current_open_positions_count=len(self.session.portfolio.positions),
        )

        if not risk_res.is_approved:
            logger.info(f"Risk Engine REJECTED candidate for {sym}: {risk_res.rejection_reason}")
            return

        # 2. Route approved order to Paper Trading Engine
        side = OrderSide.BUY if candidate.action.value in ("ENTER_LONG", "BUY") else OrderSide.SELL
        try:
            self.paper_engine.submit_manual_order(
                session_id=self.session.session_id,
                symbol=sym,
                side=side,
                quantity=risk_res.approved_quantity,
                price=price,
                stop_loss=stop_loss,
                target_price=candidate.suggested_target_price,
            )
        except Exception as e:
            logger.error(f"Paper order execution exception for {sym}: {e}")

    # =========================================================================
    # SYSTEM HEALTH & TELEMETRY API
    # =========================================================================

    def get_system_health(self) -> Dict[str, Any]:
        """Returns deterministic operational health across all 9 major subsystems."""
        with self._lock:
            return {
                "session_name": self.session_name,
                "session_id": self.session.session_id if self.session else None,
                "phase": self.phase.value,
                "subsystems": {
                    name.value: health.model_dump(mode="json")
                    for name, health in self.subsystem_health.items()
                },
                "safety_locks": {
                    "allow_live_trading": settings.ALLOW_LIVE_TRADING,
                    "allow_real_broker_execution": settings.ALLOW_REAL_BROKER_EXECUTION,
                },
            }
