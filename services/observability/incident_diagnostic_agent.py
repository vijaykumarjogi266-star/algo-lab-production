"""
Algo Lab — Autonomous SRE & Incident Diagnostic Agent.

Continuously monitors daemon runtime logs, system telemetry, and database states
to detect anomalies, classify failure modes, produce structured post-mortem reports,
and dispatch actionable mitigation alerts without human intervention.
"""

import os
import sys
import re
import json
import shutil
import sqlite3
import logging
from enum import Enum
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from pydantic import BaseModel, Field

# Ensure project root in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from services.observability.webhook_dispatcher import WebhookDispatcher

logger = logging.getLogger("SREIncidentDiagnosticAgent")


class IncidentSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentCategory(str, Enum):
    NETWORK = "NETWORK"
    BROKER_API = "BROKER_API"
    DATABASE = "DATABASE"
    SYSTEM_RESOURCE = "SYSTEM_RESOURCE"
    RISK_BREACH = "RISK_BREACH"
    STRATEGY_RUNTIME = "STRATEGY_RUNTIME"
    UNKNOWN = "UNKNOWN"


class DiagnosticSnapshot(BaseModel):
    timestamp_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    disk_free_gb: float
    disk_total_gb: float
    disk_percent_used: float
    memory_available_mb: Optional[float] = None
    memory_total_mb: Optional[float] = None
    cpu_load_avg_1m: Optional[float] = None
    database_integrity: str = "UNKNOWN"
    active_process_detected: bool = False


class IncidentReport(BaseModel):
    incident_id: str
    timestamp_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    severity: IncidentSeverity
    category: IncidentCategory
    summary: str
    error_signature: str
    root_cause_analysis: str
    affected_components: List[str] = Field(default_factory=list)
    raw_tracebacks: List[str] = Field(default_factory=list)
    recommended_mitigation: str
    snapshot: DiagnosticSnapshot


class SREIncidentDiagnosticAgent:
    """Autonomous Incident Diagnostic Engine for Algo Lab."""

    def __init__(
        self,
        project_root: Optional[str] = None,
        dispatcher: Optional[WebhookDispatcher] = None,
    ):
        self.project_root = project_root or PROJECT_ROOT
        self.data_dir = os.path.join(self.project_root, "data")
        self.incidents_dir = os.path.join(self.data_dir, "incidents")
        self.dispatcher = dispatcher or WebhookDispatcher()
        os.makedirs(self.incidents_dir, exist_ok=True)

    def collect_system_snapshot(self, db_path: Optional[str] = None) -> DiagnosticSnapshot:
        """Capture host disk, memory, CPU load, and SQLite integrity."""
        # 1. Disk usage
        disk_path = self.data_dir if os.path.exists(self.data_dir) else "/"
        total, used, free = shutil.disk_usage(disk_path)
        disk_total_gb = round(total / (1024**3), 2)
        disk_free_gb = round(free / (1024**3), 2)
        disk_percent_used = round((used / total) * 100, 2)

        # 2. Linux Memory Info via /proc/meminfo
        mem_avail_mb = None
        mem_total_mb = None
        if os.path.exists("/proc/meminfo"):
            try:
                with open("/proc/meminfo", "r", encoding="utf-8") as f:
                    mem_dict = {}
                    for line in f:
                        parts = line.split(":")
                        if len(parts) == 2:
                            mem_dict[parts[0].strip()] = parts[1].strip()
                    if "MemAvailable" in mem_dict:
                        mem_avail_kb = float(mem_dict["MemAvailable"].split()[0])
                        mem_avail_mb = round(mem_avail_kb / 1024, 2)
                    if "MemTotal" in mem_dict:
                        mem_tot_kb = float(mem_dict["MemTotal"].split()[0])
                        mem_total_mb = round(mem_tot_kb / 1024, 2)
            except Exception as e:
                logger.debug(f"Unable to read /proc/meminfo: {e}")

        # 3. CPU Load average
        cpu_load = None
        try:
            loads = os.getloadavg()
            cpu_load = round(loads[0], 2)
        except Exception:
            pass

        # 4. Database Integrity
        target_db = db_path or os.path.join(self.data_dir, "paper_trading.db")
        db_status = "FILE_NOT_FOUND"
        if os.path.exists(target_db):
            try:
                conn = sqlite3.connect(target_db, timeout=2.0)
                cur = conn.cursor()
                cur.execute("PRAGMA integrity_check;")
                res = cur.fetchone()
                db_status = str(res[0]) if res else "UNKNOWN"
                conn.close()
            except Exception as e:
                db_status = f"ERROR: {e}"

        return DiagnosticSnapshot(
            disk_free_gb=disk_free_gb,
            disk_total_gb=disk_total_gb,
            disk_percent_used=disk_percent_used,
            memory_available_mb=mem_avail_mb,
            memory_total_mb=mem_total_mb,
            cpu_load_avg_1m=cpu_load,
            database_integrity=db_status,
            active_process_detected=True,
        )

    def extract_tracebacks_from_text(self, text: str) -> List[str]:
        """Extract multi-line Python tracebacks and error blocks from log content."""
        tracebacks = []
        tb_pattern = re.compile(
            r"(Traceback \(most recent call last\):(?:\n(?: {2,}|\t)[^\n]+)*\n(?:[A-Za-z_][A-Za-z0-9_.]*(?::[^\n]*)?))",
            re.MULTILINE,
        )
        for match in tb_pattern.finditer(text):
            tracebacks.append(match.group(1).strip())
        return tracebacks

    def classify_error(self, error_text: str) -> Tuple[IncidentCategory, IncidentSeverity, str, str]:
        """Categorize error and determine severity, signature, and mitigation recommendation."""
        upper = error_text.upper()

        # Database locks / corruptions
        if "SQLITE3.OPERATIONALERROR: DATABASE IS LOCKED" in upper or "BUSY" in upper:
            return (
                IncidentCategory.DATABASE,
                IncidentSeverity.HIGH,
                "SqliteLockContention",
                "Enable WAL journal mode (PRAGMA journal_mode=WAL) and increase connection timeout to 10.0s.",
            )
        if "CORRUPT" in upper or "NOT A DATABASE" in upper or "DISK I/O ERROR" in upper:
            return (
                IncidentCategory.DATABASE,
                IncidentSeverity.CRITICAL,
                "DatabaseCorruption",
                "Automated recovery required: Restore latest snapshot from data/backups/ and restart service.",
            )

        # Rate limiting / 429
        if "429" in upper or "TOO MANY REQUESTS" in upper or "RATE LIMIT" in upper:
            return (
                IncidentCategory.BROKER_API,
                IncidentSeverity.HIGH,
                "BrokerApiRateLimitExceeded",
                "Back off request burst, introduce exponential backoff jitter, and check API token rate quota.",
            )

        # Broker token expiration / auth failure
        if "UNAUTHORIZED" in upper or "INVALID_TOKEN" in upper or "TOKEN EXPIRED" in upper or "401" in upper:
            return (
                IncidentCategory.BROKER_API,
                IncidentSeverity.CRITICAL,
                "BrokerAuthenticationFailure",
                "Broker session key or TOTP expired. Trigger automated token refresh via BrokerPreflightAgent.",
            )

        # Network timeouts / DNS failures
        if "TIMEOUT" in upper or "NAMERESOLUTIONERROR" in upper or "MAX RETRIES EXCEEDED" in upper or "CONNECTIONREFUSED" in upper:
            return (
                IncidentCategory.NETWORK,
                IncidentSeverity.HIGH,
                "NetworkEgressOrTimeoutError",
                "WAN or broker endpoint unreachable. Engage circuit breaker, freeze new orders, maintain protective exits.",
            )

        # Out of memory / memory pressure
        if "MEMORYERROR" in upper or "OUT OF MEMORY" in upper or "KILLED" in upper:
            return (
                IncidentCategory.SYSTEM_RESOURCE,
                IncidentSeverity.CRITICAL,
                "ProcessOutOfMemory",
                "OOM killer or memory leak. Enforce dataframe pruning, clear historical tick buffers, and inspect memory allocation.",
            )

        # Risk breach / killswitch trip
        if "KILLSWITCH" in upper or "DRAWDOWN" in upper or "MAX LOSS" in upper:
            return (
                IncidentCategory.RISK_BREACH,
                IncidentSeverity.HIGH,
                "RiskDrawdownKillswitchEngaged",
                "Daily risk cap exceeded. Maintain hard trading halt until explicit authorized manual reset.",
            )

        # Default fallback
        first_line = error_text.splitlines()[-1] if error_text.splitlines() else "UnknownError"
        sig = re.sub(r"[^A-Za-z0-9_]", "", first_line.split(":")[0]) or "UnhandledRuntimeError"
        return (
            IncidentCategory.STRATEGY_RUNTIME,
            IncidentSeverity.MEDIUM,
            sig,
            "Inspect runtime stack trace, check symbol parameters, and verify data schema contract.",
        )

    def scan_log_file(self, log_path: str, max_lines: int = 500) -> List[IncidentReport]:
        """Scan a log file for errors and tracebacks and produce incident reports."""
        if not os.path.exists(log_path):
            return []

        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                recent_lines = lines[-max_lines:]
                log_chunk = "".join(recent_lines)
        except Exception as e:
            logger.error(f"Failed to read log {log_path}: {e}")
            return []

        tracebacks = self.extract_tracebacks_from_text(log_chunk)
        incidents = []
        snapshot = self.collect_system_snapshot()

        if tracebacks:
            for tb in tracebacks:
                cat, sev, sig, mitigation = self.classify_error(tb)
                inc_id = f"INC-{int(datetime.now(timezone.utc).timestamp())}-{sig[:12]}"
                summary = f"Detected {sig} in {os.path.basename(log_path)}"
                report = IncidentReport(
                    incident_id=inc_id,
                    severity=sev,
                    category=cat,
                    summary=summary,
                    error_signature=sig,
                    root_cause_analysis=f"Autonomous classification identified root cause as {cat.value}: {sig}.",
                    affected_components=[os.path.basename(log_path), "AlgoLabDaemon"],
                    raw_tracebacks=[tb],
                    recommended_mitigation=mitigation,
                    snapshot=snapshot,
                )
                incidents.append(report)
        else:
            # Check for critical keywords in recent log lines
            critical_lines = [l for l in recent_lines if any(k in l for k in ("CRITICAL:", "ERROR:", "[WATCHDOG] CRITICAL", "fatal"))]
            if critical_lines:
                combined_err = "\n".join(critical_lines[-5:])
                cat, sev, sig, mitigation = self.classify_error(combined_err)
                inc_id = f"INC-{int(datetime.now(timezone.utc).timestamp())}-{sig[:12]}"
                report = IncidentReport(
                    incident_id=inc_id,
                    severity=sev,
                    category=cat,
                    summary=f"Detected runtime error pattern in {os.path.basename(log_path)}",
                    error_signature=sig,
                    root_cause_analysis=f"Log matched critical pattern without full traceback: {critical_lines[-1].strip()}",
                    affected_components=[os.path.basename(log_path)],
                    raw_tracebacks=[combined_err],
                    recommended_mitigation=mitigation,
                    snapshot=snapshot,
                )
                incidents.append(report)

        return incidents

    def save_incident_report(self, report: IncidentReport) -> Tuple[str, str]:
        """Save incident report as JSON and Markdown post-mortem."""
        json_path = os.path.join(self.incidents_dir, f"{report.incident_id}.json")
        md_path = os.path.join(self.incidents_dir, f"{report.incident_id}.md")

        # 1. JSON
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report.model_dump(), f, indent=2)

        # 2. Markdown Post-Mortem
        md_content = f"""# Incident Diagnostic Report: {report.incident_id}

**Timestamp (UTC):** {report.timestamp_utc}  
**Severity:** `{report.severity.value}` | **Category:** `{report.category.value}`  
**Signature:** `{report.error_signature}`  

## 1. Summary
{report.summary}

## 2. Root Cause Analysis
{report.root_cause_analysis}

## 3. Recommended Remediation
> **Action:** {report.recommended_mitigation}

## 4. System Telemetry Snapshot
* **Disk Usage:** {report.snapshot.disk_free_gb} GB free of {report.snapshot.disk_total_gb} GB ({report.snapshot.disk_percent_used}% used)
* **Memory Available:** {report.snapshot.memory_available_mb or 'N/A'} MB
* **1m CPU Load:** {report.snapshot.cpu_load_avg_1m or 'N/A'}
* **Database Integrity:** `{report.snapshot.database_integrity}`

## 5. Traceback & Error Context
```text
{report.raw_tracebacks[0] if report.raw_tracebacks else 'No traceback captured.'}
```
"""
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        logger.info(f"Saved incident reports to {json_path} and {md_path}")
        return json_path, md_path

    def dispatch_incident_alert(self, report: IncidentReport) -> bool:
        """Send high-priority alert via WebhookDispatcher."""
        title = f"Algo Lab Incident [{report.severity.value}]: {report.error_signature}"
        msg = f"{report.summary}\n\n**Action Required:**\n{report.recommended_mitigation}"
        fields = {
            "Incident ID": report.incident_id,
            "Category": report.category.value,
            "Severity": report.severity.value,
            "DB Integrity": report.snapshot.database_integrity,
            "Disk Free": f"{report.snapshot.disk_free_gb} GB",
        }
        return self.dispatcher.notify(title=title, message=msg, level=report.severity.value, fields=fields)

    def run_comprehensive_audit(self, notify: bool = True) -> List[IncidentReport]:
        """Inspect all logs and database to detect any active incident."""
        log_files = [
            os.path.join(self.data_dir, "paper_trading_live.log"),
            os.path.join(self.data_dir, "watchdog.log"),
        ]
        all_incidents: List[IncidentReport] = []
        for log_f in log_files:
            if os.path.exists(log_f):
                incs = self.scan_log_file(log_f)
                all_incidents.extend(incs)

        # Database health standalone check
        snapshot = self.collect_system_snapshot()
        if snapshot.database_integrity not in ("ok", "FILE_NOT_FOUND"):
            inc_id = f"INC-{int(datetime.now(timezone.utc).timestamp())}-DBIntegrityFail"
            db_inc = IncidentReport(
                incident_id=inc_id,
                severity=IncidentSeverity.CRITICAL,
                category=IncidentCategory.DATABASE,
                summary=f"SQLite database integrity check failed: {snapshot.database_integrity}",
                error_signature="DatabaseIntegrityFailure",
                root_cause_analysis="SQLite PRAGMA integrity_check returned non-ok status.",
                affected_components=["paper_trading.db"],
                recommended_mitigation="Restore latest snapshot from data/backups/ immediately.",
                snapshot=snapshot,
            )
            all_incidents.append(db_inc)

        for inc in all_incidents:
            self.save_incident_report(inc)
            if notify:
                self.dispatch_incident_alert(inc)

        return all_incidents


if __name__ == "__main__":
    agent = SREIncidentDiagnosticAgent()
    print("Running SRE Incident Diagnostic Audit...")
    incidents = agent.run_comprehensive_audit(notify=False)
    print(f"Audit completed. Found {len(incidents)} active incident(s).")
    snapshot = agent.collect_system_snapshot()
    print(f"System Snapshot: Disk Free: {snapshot.disk_free_gb}GB | Memory Avail: {snapshot.memory_available_mb}MB | DB Integrity: {snapshot.database_integrity}")
