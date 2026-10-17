#!/usr/bin/env python3
"""
Algo Lab — SRE Incident Diagnostic Agent CLI Runner.
Usage:
    python3 run_incident_diagnostic_agent.py [--no-notify] [--log-file PATH]
"""

import sys
import argparse
from services.observability.incident_diagnostic_agent import SREIncidentDiagnosticAgent


def main():
    parser = argparse.ArgumentParser(description="Algo Lab Autonomous SRE Incident Diagnostic Agent")
    parser.add_argument("--no-notify", action="store_true", help="Suppress webhook notifications")
    parser.add_argument("--log-file", type=str, help="Specific log file path to diagnose")
    args = parser.parse_args()

    agent = SREIncidentDiagnosticAgent()
    print("=" * 65)
    print("ALGO LAB — AUTONOMOUS SRE INCIDENT DIAGNOSTIC AGENT")
    print("=" * 65)

    if args.log_file:
        print(f"Scanning target log file: {args.log_file}")
        incidents = agent.scan_log_file(args.log_file)
        for inc in incidents:
            agent.save_incident_report(inc)
            if not args.no_notify:
                agent.dispatch_incident_alert(inc)
    else:
        print("Running full audit across all daemon logs and database...")
        incidents = agent.run_comprehensive_audit(notify=not args.no_notify)

    snapshot = agent.collect_system_snapshot()
    print(f"\nSystem Telemetry Snapshot:")
    print(f"  • Disk Free:     {snapshot.disk_free_gb} GB ({snapshot.disk_percent_used}% used)")
    print(f"  • Memory Avail:  {snapshot.memory_available_mb or 'N/A'} MB")
    print(f"  • CPU Load (1m): {snapshot.cpu_load_avg_1m or 'N/A'}")
    print(f"  • DB Integrity:  {snapshot.database_integrity}")

    print(f"\nAudit Summary: {len(incidents)} active incident(s) diagnosed.")
    for inc in incidents:
        print(f"\n[{inc.severity.value}] Incident: {inc.incident_id}")
        print(f"  Category:   {inc.category.value}")
        print(f"  Signature:  {inc.error_signature}")
        print(f"  Mitigation: {inc.recommended_mitigation}")

    print("=" * 65)
    sys.exit(1 if any(i.severity.value in ("CRITICAL", "HIGH") for i in incidents) else 0)


if __name__ == "__main__":
    main()
