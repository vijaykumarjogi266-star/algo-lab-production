# Test Evidence: Stage 3 — Internal Paper Exchange & Execution Realism

## 1. Test Execution Metadata
- **Date**: 2026-10-11
- **Stage**: Stage 3 (Internal Paper Exchange and Execution Realism)
- **Branch**: `feat/stage3-paper-exchange-realism`
- **Environment**: Local Linux sandbox (zero network, local SQLite, deterministic execution)
- **Safety Flags**:
  - `TRADING_MODE=READ_ONLY`
  - `ORDER_SUBMISSION_ENABLED=false`
  - `ALLOW_LIVE_TRADING=false`
  - `ALLOW_REAL_BROKER_EXECUTION=false`

## 2. Dedicated Paper Exchange Realism Suite
Test file: `oms_project/tests/test_paper_exchange_realism.py`
Result: 8 passed in 0.05s

| Test Case | Scenario Verified | Status |
|:---|:---|:---|
| `test_resting_limit_orders_and_queue_matching` | Limit orders rest in book until market crosses; matching updates order state to FILLED | PASSED |
| `test_collar_boundary_enforcement_prevents_errant_pricing` | Gateway 2.0% price collar rejects errant limit orders with `REJECTED_PRICE_COLLAR_DEVIATION` | PASSED |
| `test_exchange_rejection_releases_risk_reservation` | Rejections by exchange release reserved capital immediately with no phantom reservation | PASSED |
| `test_adverse_execution_profile_slippage_and_fees` | Base spread, volume-based quadratic/linear slippage, bps fees, and fixed ticket fees applied accurately | PASSED |
| `test_partial_fill_and_no_fill_modes` | `PARTIAL` mode fills exact partial fraction; `NO_FILL` mode records rejection cleanly | PASSED |
| `test_liquidity_cap_enforcement` | Sizing exceeding `max_participation_rate` * available volume is capped or rejected | PASSED |
| `test_session_end_auto_cancellation` | EOD session close cancels all open resting orders | PASSED |
| `test_sensitivity_matrix_generation` | Multi-dimensional grid analysis across spreads and slippage factors computes expected prices and fees | PASSED |

## 3. Full Regression Test Run
Command:
```bash
PYTHONPATH=. .venv/bin/pytest oms_project/tests/ -q
```
Outcome:
```text
======================= 149 passed, 2 warnings in 9.83s ========================
```
Zero failures, zero regressions across OMS, Risk, Accounting, Reconciliation, Deterministic Replay, and Paper Exchange modules.
