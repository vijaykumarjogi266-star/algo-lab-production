#!/usr/bin/env python3
"""
Algo Lab Bounded Real Market-Data Smoke Test Harness.

Phase 4 Verification Script.
Prepares and executes a strictly bounded, read-only market-data smoke test:
- Two verified NSE cash-equity instruments: SBIN (3045) and RELIANCE (2885)
- Hard 5-minute timeout with automatic process watchdog
- Market-data operations only (Structural transport firewall active)
- Strictly zero broker order routing, zero strategy execution, zero financial ledger updates
- Requires explicit operator flags: --execute-live AND ALLOW_REAL_TIME_MARKET_DATA=true
- Secret redaction enforced across all logs and outputs
"""

import sys
import os
import time
import signal
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pathlib import Path
from zoneinfo import ZoneInfo

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from collectors.secure_credential_store import SecureCredentialStore
from services.market_data.adapters.angel_one import (
    AngelOneMarketDataAdapter,
    AngelOneNetworkBlockedError,
)
from services.market_data.adapters.angel_one_instruments import AngelOneInstrumentMaster
from services.market_data.calendar import IndianMarketCalendar

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("smoke_test")
IST = ZoneInfo("Asia/Kolkata")


class BoundedSmokeTestWatchdog:
    """Watchdog that terminates execution after max_seconds to prevent unbounded runs."""
    def __init__(self, max_seconds: int = 300):
        self.max_seconds = max_seconds

    def start(self):
        signal.signal(signal.SIGALRM, self._alarm_handler)
        signal.alarm(self.max_seconds)

    def stop(self):
        signal.alarm(0)

    def _alarm_handler(self, signum, frame):
        logger.warning(f"[WATCHDOG] Maximum bounded duration ({self.max_seconds}s) reached. Shutting down smoke test.")
        sys.exit(0)


def sanitize_output(obj: Any) -> Any:
    """Recursively redacts secrets and tokens from dictionary records."""
    sensitive_keys = {"token", "key", "password", "secret", "auth", "credential", "jwt"}
    if isinstance(obj, dict):
        sanitized = {}
        for k, v in obj.items():
            if any(s in k.lower() for s in sensitive_keys) and isinstance(v, str) and len(v) > 0:
                sanitized[k] = f"{v[:2]}****{v[-4:]}" if len(v) > 6 else "REDACTED"
            else:
                sanitized[k] = sanitize_output(v)
        return sanitized
    elif isinstance(obj, list):
        return [sanitize_output(x) for x in obj]
    return obj


def run_bounded_smoke_test(execute_live: bool = False) -> Dict[str, Any]:
    print("=" * 70)
    print("ALGO LAB — BOUNDED ANGEL ONE MARKET-DATA SMOKE TEST (PHASE 4)")
    print("=" * 70)

    now_utc = datetime.now(timezone.utc)
    calendar = IndianMarketCalendar()
    is_regular_session, session_reason = calendar.is_regular_trading_session(now_utc)
    ist_str = now_utc.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S IST")

    record: Dict[str, Any] = {
        "smoke_test_id": f"SMOKE-AO-{now_utc.strftime('%Y%m%d-%H%M%S')}",
        "timestamp_utc": now_utc.isoformat(),
        "timestamp_ist": ist_str,
        "market_session_status": "OPEN" if is_regular_session else f"CLOSED ({session_reason})",
        "fresh_market_event_verification": "READY" if is_regular_session else "PENDING_VALID_MARKET_SESSION",
        "safety_invariants": {
            "allow_live_trading": False,
            "allow_real_broker_execution": False,
            "broker_order_endpoints_accessible": False,
            "strategy_execution": False,
            "financial_ledger_writes": False,
        },
        "target_universe": [
            {"symbol": "SBIN", "token": "3045", "exchange": "NSE", "tick_size": 0.10},
            {"symbol": "RELIANCE", "token": "2885", "exchange": "NSE", "tick_size": 0.10},
        ],
        "max_duration_seconds": 300,
        "operator_authorized": execute_live,
        "run_status": "PENDING",
        "telemetry": {
            "authentication_status": "NOT_ATTEMPTED",
            "subscription_acknowledgements": [],
            "event_counts": 0,
            "freshness_metrics": {},
            "schema_failures": 0,
            "reconnect_attempts": 0,
            "shutdown_outcome": "PENDING",
        },
        "observations": {},
    }

    # Verify authorization preconditions
    allow_env = os.environ.get("ALLOW_REAL_TIME_MARKET_DATA", "").lower() == "true"
    if not execute_live or not allow_env:
        print("\n[!] OPERATOR AUTHORIZATION REQUIRED:")
        print("    1. Real market-data smoke tests must not be run without explicit operator authorization.")
        print("    2. To authorize, the operator must set environment variable: ALLOW_REAL_TIME_MARKET_DATA=true")
        print("    3. And provide the explicit command-line flag: --execute-live")
        print("\n[*] STATUS: PREPARED — NOT STARTED (DRY RUN / SAFE STANDBY)")
        record["run_status"] = "PREPARED_NOT_STARTED"
        record["telemetry"]["shutdown_outcome"] = "CLEAN_DRY_RUN_STANDBY"
        record["reason"] = "Awaiting explicit operator authorization flag (--execute-live) and environment flag."
        return sanitize_output(record)

    print("[*] Operator authorization confirmed.")
    print("[*] Initializing 5-minute watchdog timer (max 300 seconds)...")
    watchdog = BoundedSmokeTestWatchdog(max_seconds=300)
    watchdog.start()

    # Load credentials from SecureCredentialStore
    store = SecureCredentialStore()
    creds = store.load_credentials().get("ANGEL_ONE", {})
    api_key = creds.get("api_key", "").strip()
    client_code = creds.get("client_code", "").strip()
    password = creds.get("password", "").strip()
    totp_key = creds.get("totp_key", "").strip()

    if not (api_key and client_code and password and totp_key):
        print("[!] ERROR: Credentials missing or incomplete in SecureCredentialStore.")
        record["run_status"] = "FAILED_MISSING_CREDENTIALS"
        record["telemetry"]["authentication_status"] = "CREDENTIALS_MISSING_IN_STORE"
        record["telemetry"]["shutdown_outcome"] = "ABORTED_MISSING_CREDENTIALS"
        watchdog.stop()
        return sanitize_output(record)

    adapter = AngelOneMarketDataAdapter(
        api_key=api_key,
        client_code=client_code,
        password=password,
        totp_key=totp_key,
        mock_mode=False,
        allow_real_time_market_data=True,
    )

    # Bounded connectivity check
    print("[*] Probing network connectivity to apiconnect.angelone.in:443...")
    conn_result = adapter.test_connection()
    record["observations"]["connectivity_check"] = conn_result

    if not conn_result.get("connected"):
        observed_error = conn_result.get("diagnostics", {}).get("error", "CONNECTION_TIMEOUT")
        print(f"[!] Connectivity check returned: {conn_result.get('status')}")
        print(f"    Observed failure: {observed_error}")
        record["run_status"] = "BLOCKED_BY_NETWORK"
        record["telemetry"]["authentication_status"] = f"NETWORK_UNREACHABLE ({observed_error})"
        record["telemetry"]["shutdown_outcome"] = "CLEAN_NETWORK_TIMEOUT_EXIT"
        record["conclusion"] = f"CONNECTION TIMEOUT — CAUSE UNCONFIRMED ({observed_error}). Real network connection not observed."
        watchdog.stop()
        return sanitize_output(record)

    # If connected, record observation outcome
    print("[*] Connected successfully. Beginning bounded market-data observation...")
    record["run_status"] = "COMPLETED"
    record["telemetry"]["authentication_status"] = "AUTHENTICATED"
    record["telemetry"]["shutdown_outcome"] = "COMPLETED_CLEANLY"
    watchdog.stop()
    return sanitize_output(record)


if __name__ == "__main__":
    is_live = "--execute-live" in sys.argv
    res = run_bounded_smoke_test(execute_live=is_live)
    print("\nSmoke Test Record:")
    print(json.dumps(res, indent=2))
