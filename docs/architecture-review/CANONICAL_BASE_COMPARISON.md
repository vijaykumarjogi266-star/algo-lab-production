# Canonical Base Comparison: AlgoLab vs Terminix

## Overview
This document evaluates Candidate A (`/home/ubuntu/algolab`) and Candidate B (`/home/ubuntu/termux-ai-sandbox`) as potential canonical bases for the Algo Lab project.

## Candidate A (AlgoLab - Current Canonical)
**Maturity:**
- Git Branch: `stage7-research-evaluation`
- Latest Commit: `Thu Sep 24 14:49:12 2026`
- State: Dirty (many uncommitted and untracked files).
- Test Count: 69 OMS tests evaluated. 60 Passed, 9 Failed.
- Safety Characteristics: Implements `OrderLedgerDB`, duplicate execution protection (T08), out-of-order execution (T09), partial fills (T06), and concurrent risk reservation (T15).
- Identified failing tests: Relate to idempotency attacks, risk exhaustion boundaries, deterministic precision, and portfolio P&L snapshots.

## Candidate B (Terminix / Termux Algo Lab)
**Maturity:**
- Git Branch: `main`
- Latest Commit: `Thu Sep 17 15:56:35 2026`
- State: Dirty (modified factory/orchestrator files, untracked isolation upgrades).
- Test Count: 333 tests evaluated in `algopro/tests`. 322 Passed, 11 Failed.
- Safety Characteristics: Contains quantitative indicators, evaluation metrics, and a legacy paper engine.
- Identified failing tests: `test_paper_runner.py` suite fails entirely due to a hardcoded "CERTIFICATION BLOCKED" intercept that checks git integrity and accounting.
- Direct broker / secret risks: Heavily reliant on direct broker calls without central OMS gating, insecure credential files, and disjointed SQLite state.
