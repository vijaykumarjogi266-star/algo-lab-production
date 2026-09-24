"""
Algo Lab Stage 25 Phase 25C — Continuous Forward Equity Paper-Trading Gate Tracker

Manages and evaluates the 1-Month Continuous Forward Equity Paper-Trading Gate.

Gate Qualification Criteria:
1. Actual forward passage of calendar time (at least 30 continuous calendar days = 1 calendar month).
2. At least 20 valid NSE trading sessions within the qualifying period.
3. Actual collected forward market data and actual paper-trading execution.
4. Historical replay, replayed data, accelerated simulation, or synthetic fixtures MUST NOT satisfy the gate (classified as SESSION_EXCLUDED).

Session State Model:
- SESSION_OBSERVED: Forward market data observed.
- SESSION_VALID: Passed freshness & integrity checks.
- SESSION_PAPER_COMPLETE: Forward paper trading session successfully executed and logged.
- SESSION_INVALID: Failed data quality, freshness, or schema checks.
- SESSION_EXCLUDED: Replayed historical data or synthetic test fixture; excluded from forward gate.
"""

import os
import sys
import json
import hashlib
from enum import Enum
from datetime import datetime, timezone, timedelta

DEFAULT_PAPER_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "paper", "logs")
FORWARD_GATE_LOG_DIR = os.environ.get("ALGOLAB_FORWARD_GATE_LOG_DIR") or DEFAULT_PAPER_LOG_DIR
REQUIRED_MIN_CALENDAR_DAYS = 30
REQUIRED_MIN_TRADING_SESSIONS = 20


class ForwardSessionState(str, Enum):
    SESSION_OBSERVED = "SESSION_OBSERVED"
    SESSION_VALID = "SESSION_VALID"
    SESSION_PAPER_COMPLETE = "SESSION_PAPER_COMPLETE"
    SESSION_INVALID = "SESSION_INVALID"
    SESSION_EXCLUDED = "SESSION_EXCLUDED"


class ForwardGateTracker:
    """Tracks and evaluates the continuous forward paper-trading gate."""

    def __init__(self, log_dir: str = FORWARD_GATE_LOG_DIR):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self.gate_log_file = os.path.join(self.log_dir, "forward_gate_sessions.jsonl")

    def record_session_observation(
        self,
        session_id: str,
        session_date: str,  # YYYY-MM-DD
        status: ForwardSessionState | str,
        is_replayed: bool = False,
        is_historical: bool = False,
        is_synthetic: bool = False,
        metadata: dict = None,
    ) -> dict:
        """
        Records a forward paper session observation.
        If is_replayed, is_historical, or is_synthetic is True, state becomes SESSION_EXCLUDED.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        state = status.value if isinstance(status, Enum) else status

        if is_replayed or is_historical or is_synthetic:
            state = ForwardSessionState.SESSION_EXCLUDED.value
            exclusion_reason = "Historical replay or synthetic fixture excluded from forward gate qualification."
        else:
            exclusion_reason = None

        record = {
            "session_id": session_id,
            "session_date": session_date,
            "state": state,
            "is_replayed": is_replayed,
            "is_historical": is_historical,
            "is_synthetic": is_synthetic,
            "exclusion_reason": exclusion_reason,
            "recorded_at": now_iso,
            "metadata": metadata or {},
        }

        try:
            with open(self.gate_log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to log forward gate session: {e}\n")

        return record

    def load_gate_history() -> list:
        """Loads all recorded forward session entries from log."""
        gate_log_file = os.path.join(FORWARD_GATE_LOG_DIR, "forward_gate_sessions.jsonl")
        history = []
        if os.path.exists(gate_log_file):
            try:
                with open(gate_log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            history.append(json.loads(line))
            except Exception:
                pass
        return history

    def evaluate_forward_gate(
        self,
        current_date: datetime | str | None = None,
        custom_history: list = None,
    ) -> dict:
        """
        Evaluates current forward gate status against the 30-day and 20-session criteria.
        Returns INCOMPLETE if requirements are not met.
        """
        # Load history
        if custom_history is not None:
            history = custom_history
        else:
            history = []
            if os.path.exists(self.gate_log_file):
                with open(self.gate_log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            try:
                                history.append(json.loads(line.strip()))
                            except Exception:
                                pass

        # Filter valid forward sessions
        valid_sessions = []
        excluded_sessions = []

        for entry in history:
            state = entry.get("state")
            is_replayed = entry.get("is_replayed", False)
            is_historical = entry.get("is_historical", False)
            is_synthetic = entry.get("is_synthetic", False)

            if is_replayed or is_historical or is_synthetic or state == ForwardSessionState.SESSION_EXCLUDED.value:
                excluded_sessions.append(entry)
            elif state == ForwardSessionState.SESSION_PAPER_COMPLETE.value:
                valid_sessions.append(entry)

        if not valid_sessions:
            return {
                "gate_status": "INCOMPLETE",
                "reason": "No valid forward paper trading sessions recorded yet. Continuous forward gate is INCOMPLETE.",
                "elapsed_calendar_days": 0,
                "valid_trading_sessions": 0,
                "excluded_sessions_count": len(excluded_sessions),
                "required_min_calendar_days": REQUIRED_MIN_CALENDAR_DAYS,
                "required_min_trading_sessions": REQUIRED_MIN_TRADING_SESSIONS,
                "is_simulated": True,
            }

        # Parse unique session dates
        valid_dates = sorted(list(set(entry["session_date"] for entry in valid_sessions if "session_date" in entry)))
        valid_session_count = len(valid_dates)

        if len(valid_dates) > 0:
            start_date_obj = datetime.strptime(valid_dates[0], "%Y-%m-%d").date()
            end_date_obj = datetime.strptime(valid_dates[-1], "%Y-%m-%d").date()
            elapsed_days = (end_date_obj - start_date_obj).days + 1
        else:
            elapsed_days = 0
            start_date_obj = None
            end_date_obj = None

        # Qualification check
        calendar_qualified = elapsed_days >= REQUIRED_MIN_CALENDAR_DAYS
        sessions_qualified = valid_session_count >= REQUIRED_MIN_TRADING_SESSIONS

        if calendar_qualified and sessions_qualified:
            gate_status = "PASS"
            reason = f"Gate PASSED: {elapsed_days} continuous calendar days and {valid_session_count} valid NSE trading sessions completed."
        else:
            gate_status = "INCOMPLETE"
            reason = (
                f"Gate INCOMPLETE: Elapsed calendar days {elapsed_days}/{REQUIRED_MIN_CALENDAR_DAYS}, "
                f"valid trading sessions {valid_session_count}/{REQUIRED_MIN_TRADING_SESSIONS}."
            )

        return {
            "gate_status": gate_status,
            "reason": reason,
            "elapsed_calendar_days": elapsed_days,
            "valid_trading_sessions": valid_session_count,
            "excluded_sessions_count": len(excluded_sessions),
            "start_date": valid_dates[0] if valid_dates else None,
            "latest_date": valid_dates[-1] if valid_dates else None,
            "required_min_calendar_days": REQUIRED_MIN_CALENDAR_DAYS,
            "required_min_trading_sessions": REQUIRED_MIN_TRADING_SESSIONS,
            "is_simulated": True,
        }
