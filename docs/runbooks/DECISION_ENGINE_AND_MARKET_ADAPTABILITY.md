# Runbook: Decision Engine & Market Adaptability Operations

## 1. Overview
This runbook covers operational monitoring, policy management, and verification of the Stage 4 Decision Engine and Candidate Intent Lifecycle (`oms_project/candidate_intent.py`).

## 2. Architecture & Components
- **CandidateIntent**: Strategy proposal containing intent type, target exposure, time horizon, max slippage, and regime compatibility.
- **Stage4DecisionEngine**: Orchestrates regime gating, dynamic risk sizing, and order dispatching.
- **ProfileTransitionManager**: Manages adaptation profiles (`TRENDING`, `CHOPPY`, `HIGH_VOLATILITY`, `LOW_LIQUIDITY`, `DEGRADED_DATA`, `NORMAL`) with confirmation threshold and hysteresis cooldown.

## 3. Operational Invariants
1. **Never Emit Direct Orders from Alpha Code**:
   Strategies must only instantiate `CandidateIntent` models. All execution routing must pass through `Stage4DecisionEngine.process_candidate_intent()`.
2. **Fail-Closed on Degraded Market Data**:
   Whenever the market data stream detects gaps, stale timestamps, or anomalies, the profile transitions immediately to `DEGRADED_DATA`. All new entries are rejected (`REJECTED_BY_REGIME`). Only `reduce_only=True` orders are permitted.
3. **Anti-Whipsaw Hysteresis**:
   When recovering from `HIGH_VOLATILITY` or `DEGRADED_DATA`, the engine enforces a minimum cooldown period (60s) and a confirmation threshold (3 consecutive observations) before restoring normal sizing.

## 4. Operational Commands
### Running Verification Suite
```bash
PYTHONPATH=. pytest oms_project/tests/test_stage4_decision_engine.py -v
```

### Inspecting Intent Audit Trails
Each processed `CandidateIntent` retains an immutable audit trail in `intent.audit_trail`:
```python
for event in intent.audit_trail:
    print(f"[{event['timestamp']}] {event['from_state']} -> {event['to_state']}: {event['reason']}")
```

## 5. Troubleshooting & Diagnostics
- **Intent Rejected with REJECTED_BY_REGIME**:
  Inspect `intent.rejection_reason`. Verify whether the strategy's `regime_compatibility` contains the active market adaptation profile (`engine.active_profile`).
- **Intent Rejected with REJECTED_BY_RISK**:
  Check if `target_exposure` exceeds `max_capital_per_trade`, or if required cash exceeds available account cash.
- **Whipsawing Regime Changes**:
  If profile changes too frequently, increase `confirmation_threshold` or `cooldown_seconds` on `ProfileTransitionManager`.
