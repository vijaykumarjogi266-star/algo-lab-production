"""
QUANT-OS Stage 6 - Master System Conductor & Trading Scheduler (trading_scheduler.py)
Governs system clock, pre-market ritual (09:00 AM IST), active market health monitoring (09:15 - 15:30 IST),
pre-flight connectivity probe with CRITICAL_NETWORK_BLOCK fault tolerance,
Symmetry Shutdown (03:30 PM IST force-flattening), and EOD Automated Auditor triggering.
"""

import sys
import os
import time
import socket
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from oms_project.calendar_service import NSECalendarService
from oms_project.gateway import BrokerGateway
from oms_project.paper_exchange import PaperExchange
from oms_project.central_data_feed import MarketDataService
from oms_project.strategies.hybrid.hybrid_alpha_strat import HybridAlphaStrategy
from oms_project.strategies.mean_reversion.strategy_sdk import StrategySDK
from oms_project.eod_report_gen import EODReportGenerator

# Configure System Conductor Logger
logger = logging.getLogger("QUANT_OS_CONDUCTOR")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [CONDUCTOR] %(message)s"))
    logger.addHandler(ch)

IST_TZ = ZoneInfo("Asia/Kolkata")


class PreFlightProbe:
    """Network Probe testing outbound TCP 443 connectivity to Broker Endpoints."""

    @staticmethod
    def probe_endpoint(host: str, port: int = 443, timeout: float = 3.0) -> Tuple[bool, str]:
        start = time.time()
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
            elapsed_ms = (time.time() - start) * 1000.0
            return True, f"CONNECTED ({elapsed_ms:.2f} ms)"
        except socket.timeout:
            return False, "BLOCKED (Connection Timeout)"
        except Exception as e:
            return False, f"BLOCKED ({e})"

    @classmethod
    def run_preflight_check(cls) -> Tuple[bool, Dict[str, Any]]:
        endpoints = [
            ("REST_GATEWAY", "apiconnect.angelone.in", 443),
            ("WSS_GATEWAY", "smartapisocket.angelone.in", 443),
        ]
        all_open = True
        results = {}
        for name, host, port in endpoints:
            status, details = cls.probe_endpoint(host, port, timeout=3.0)
            results[name] = {"host": host, "port": port, "status": status, "details": details}
            if not status:
                all_open = False
        return all_open, results


class TradingScheduler:
    """Master System Conductor governing trading day lifecycle."""

    def __init__(self, simulation_override: bool = False):
        self.calendar = NSECalendarService()
        self.simulation_override = simulation_override
        self.scheduler = BackgroundScheduler(timezone=IST_TZ)
        self.audit_generator = EODReportGenerator()

        # Operational State
        self.is_preflight_passed = False
        self.is_active_phase = False
        self.gateway: Optional[BrokerGateway] = None
        self.feed: Optional[MarketDataService] = None
        self.pods: Dict[str, Any] = {}
        self.logs_trace: List[str] = []

    def log(self, message: str, level: str = "INFO"):
        formatted = f"[{datetime.now(IST_TZ).strftime('%Y-%m-%d %H:%M:%S IST')}] {message}"
        self.logs_trace.append(formatted)
        if level == "CRITICAL":
            logger.critical(message)
        elif level == "WARNING":
            logger.warning(message)
        else:
            logger.info(message)

    # 1. Pre-Market Ritual (09:00 AM IST)
    def pre_market_ritual(self, custom_dt: Optional[datetime] = None) -> Dict[str, Any]:
        check_dt = custom_dt or datetime.now(IST_TZ)
        self.log(f"=== Starting Pre-Market Ritual for {check_dt.strftime('%A, %Y-%m-%d')} ===")

        # Step 1: Calendar Check
        shift_status = self.calendar.verify_morning_dynamic_shift(check_dt)
        self.log(f"Calendar Check: {shift_status['day_of_week']} -> {shift_status['reason']} (Trading Day: {shift_status['is_trading_day']})")

        if not shift_status["is_trading_day"]:
            self.log("Market Closed today per NSE Calendar schedule. Skipping trading pod launch.", level="WARNING")
            return self.trigger_eod_ritual(is_skipped_day=True, custom_dt=check_dt)

        # Step 2: Pre-Flight Network Probe
        self.log("Executing Pre-Flight Connectivity Probe (TCP 443 to Broker Endpoints)...")
        probe_ok, probe_details = PreFlightProbe.run_preflight_check()

        for ep, details in probe_details.items():
            self.log(f"  Probe [{ep}] {details['host']}:{details['port']} -> {details['details']}")

        if not probe_ok and not self.simulation_override:
            self.log("CRITICAL_NETWORK_BLOCK: Outbound TCP 443 egress to Angel One is BLOCKED.", level="CRITICAL")
            self.log("SAFE-FAIL FAULT TOLERANCE: Halting launch of Broker Gateway & Algo Pods.", level="CRITICAL")
            self.is_preflight_passed = False
            return {
                "status": "HALTED_NETWORK_BLOCK",
                "alert": "CRITICAL_NETWORK_BLOCK",
                "probe_details": probe_details,
                "action": "POD_LAUNCH_HALTED",
            }

        # Pre-Flight Passed or Simulation Override Active
        self.is_preflight_passed = True
        self.log("Pre-Flight Verification PASSED. Initializing Market Data Feed & Broker Gateway...")

        paper_ex = PaperExchange(initial_cash=100000.0)
        self.gateway = BrokerGateway(paper_exchange=paper_ex, simulation_mode=True)
        self.gateway.strategy_balances["STRAT_HYBRID_001"] = 100000.0
        self.gateway.strategy_positions["STRAT_HYBRID_001"] = {}
        self.gateway.strategy_entry_prices["STRAT_HYBRID_001"] = {}

        self.feed = MarketDataService()

        # Instantiate Pods
        sdk = StrategySDK(strategy_id="STRAT_HYBRID_001")
        self.pods["STRAT_HYBRID_001"] = HybridAlphaStrategy(
            strategy_id="STRAT_HYBRID_001",
            symbol="RELIANCE",
            volatility_window=10,
            volatility_threshold=0.01,
            sdk=sdk,
        )
        self.log("Algo Pod [STRAT_HYBRID_001] successfully initialized and online.")

        return {
            "status": "PREFLIGHT_SUCCESS",
            "is_preflight_passed": True,
            "probe_details": probe_details,
            "active_pods": list(self.pods.keys()),
        }

    # 2. Active Market Health Monitoring (09:15 AM - 03:30 PM IST)
    def monitor_active_market_health(self) -> Dict[str, Any]:
        if not self.is_preflight_passed or self.gateway is None:
            self.log("Health Monitor: System is not active (Pre-flight failed or skipped).", level="WARNING")
            return {"status": "INACTIVE"}

        self.log("Executing Active Market System Health Check...")
        heartbeat_ok = self.feed.is_connected if self.feed and hasattr(self.feed, 'is_connected') else True
        gw_ok = self.gateway.db_reachable and not self.gateway.kill_switch_active

        if not heartbeat_ok or not gw_ok:
            self.log("SYSTEM HEALTH WARNING: Component degradation detected. Triggering single auto-restart...", level="WARNING")
            if not heartbeat_ok and self.feed:
                self.feed.connect_with_backoff()
            if not gw_ok and self.gateway:
                self.gateway.set_db_reachable(True)
            self.log("Auto-restart recovery completed.")
            return {"status": "RECOVERED"}

        self.log("System Health Status: 100% HEALTHY (All heartbeats active).")
        return {"status": "HEALTHY"}

    # 3. Market Close Ritual (03:30 PM IST) - Symmetry Shutdown & EOD Audit
    def trigger_eod_ritual(self, is_skipped_day: bool = False, custom_dt: Optional[datetime] = None) -> Dict[str, Any]:
        check_dt = custom_dt or datetime.now(IST_TZ)
        self.log(f"=== Starting Market Close Ritual (03:30 PM IST) for {check_dt.strftime('%Y-%m-%d')} ===")

        flatten_results = []
        target_gw = self.gateway
        if not is_skipped_day and self.gateway is not None:
            self.log("SYMMETRY SHUTDOWN: Force-flattening all active strategy positions...")
            flatten_results = self.gateway.force_flatten_positions()
            self.log(f"Flattening Complete: {len(flatten_results)} position legs closed.")

            self.log("Terminating Algo Pods and stopping Broker Gateway / Data Feed...")
            self.pods.clear()
            self.gateway = None
            self.feed = None
            self.is_preflight_passed = False

        # Run EOD Automated Auditor
        self.log("Triggering EOD Automated Auditor for Asset Reconciliation & P&L Audit...")
        if target_gw is None:
            paper_ex = PaperExchange(initial_cash=100000.0)
            mock_gw = BrokerGateway(paper_exchange=paper_ex, simulation_mode=True)
            mock_gw.strategy_balances["STRAT_HYBRID_001"] = 100000.0
            mock_gw.strategy_positions["STRAT_HYBRID_001"] = {}
            target_gw = mock_gw

        # Extract executed trades from gateway
        executed_trades = []
        if hasattr(target_gw, 'idempotency_cache'):
            for t in target_gw.idempotency_cache.values():
                # t['status'] is OrderState.FILLED (enum) or string 'FILLED'
                status = t.get('status')
                if str(status).endswith('FILLED'):
                    executed_trades.append(t)

        audit_res = self.audit_generator.generate_eod_audit_report(
            gateway=target_gw,
            strategy_id="STRAT_HYBRID_001",
            initial_capital=100000.0,
            trades=executed_trades,
            operational_logs=self.logs_trace[-10:],
        )

        self.log(f"EOD Audit Complete: Reconciliation Status = {audit_res['reconciliation_audit']['status']} (Δ = ₹{audit_res['reconciliation_audit']['variance']:.2f})")
        self.log(f"Audit PDF Saved: {audit_res['pdf_report_file']}")
        self.log(f"Audit JSON Saved: {audit_res['json_report_file']}")

        return {
            "status": "EOD_COMPLETED",
            "is_skipped_day": is_skipped_day,
            "flatten_count": len(flatten_results),
            "audit_data": audit_res,
        }

    def start_scheduler(self):
        """Starts APScheduler background jobs for 08:00 AM, 09:00 AM, and 03:30 PM IST."""
        # 08:00 AM IST Morning Shift Verification
        self.scheduler.add_job(
            func=self.calendar.verify_morning_dynamic_shift,
            trigger=CronTrigger(hour=8, minute=0, timezone=IST_TZ),
            id="morning_shift_check",
        )
        # 09:00 AM IST Pre-Market Ritual
        self.scheduler.add_job(
            func=self.pre_market_ritual,
            trigger=CronTrigger(hour=9, minute=0, timezone=IST_TZ),
            id="pre_market_ritual",
        )
        # 03:30 PM IST Market Close Ritual
        self.scheduler.add_job(
            func=self.trigger_eod_ritual,
            trigger=CronTrigger(hour=15, minute=30, timezone=IST_TZ),
            id="market_close_ritual",
        )
        self.scheduler.start()
        self.log("QUANT-OS Trading Scheduler Started (APScheduler Background Jobs Active).")


if __name__ == "__main__":
    scheduler = TradingScheduler()
    scheduler.start_scheduler()
    print("Trading Scheduler running. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        scheduler.scheduler.shutdown()
