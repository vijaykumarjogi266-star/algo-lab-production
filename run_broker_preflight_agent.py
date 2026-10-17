#!/usr/bin/env python3
"""
Algo Lab — Broker Preflight Readiness CLI Runner.
Usage:
    python3 run_broker_preflight_agent.py [--no-notify] [--strict]
"""

import sys
import argparse
from services.observability.preflight_agent import BrokerPreflightAgent


def main():
    parser = argparse.ArgumentParser(description="Algo Lab Broker Preflight Readiness Audit")
    parser.add_argument("--no-notify", action="store_true", help="Suppress webhook notifications")
    parser.add_argument("--strict", action="store_true", help="Exit with non-zero code on any warning")
    args = parser.parse_args()

    agent = BrokerPreflightAgent()
    print("=" * 65)
    print("ALGO LAB — BROKER PREFLIGHT & OPERATIONAL READINESS AGENT")
    print("=" * 65)

    report = agent.run_preflight_audit(notify=not args.no_notify)

    print(f"\nReport ID: {report.report_id}")
    print(f"Timestamp: {report.timestamp_ist}")
    print(f"Verdict:   {report.overall_verdict}")
    print(f"Failures:  {report.critical_failures_count} critical | {report.warnings_count} warnings\n")

    for c in report.checks:
        badge = "PASS" if c.status.value == "PASSED" else c.status.value
        lat = f"({c.latency_ms:.1f}ms)" if c.latency_ms is not None else ""
        print(f"[{badge:<7}] {c.name:<32} {lat:<10} {c.details}")

    print("=" * 65)
    if report.overall_verdict == "NO_GO":
        print("ACTION: PREFLIGHT FAILED. Trading daemon launch BLOCKED.")
        sys.exit(1)
    elif report.overall_verdict == "GO_WITH_WARNINGS" and args.strict:
        print("ACTION: Preflight passed with warnings, but --strict mode enforced.")
        sys.exit(2)
    else:
        print("ACTION: PREFLIGHT CLEARED. System ready for session.")
        sys.exit(0)


if __name__ == "__main__":
    main()
