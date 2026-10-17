# ADR-001: Permanent Paper-Only Execution Policy & Live Money Prohibition

## Status
- **Status:** Accepted
- **Date:** 2026-10-14
- **Author:** Lead Systems Architect (@vijaykumarjogi266-star)
- **Deciders:** Institutional Quantitative Systems Committee / Lead Systems Architect

## Context
Algo Lab is designed for rigorous quantitative research, strategy backtesting, and forward paper-trading validation within the Indian capital markets ecosystem (NSE/BSE). In automated quantitative systems, unintended live order execution poses severe operational, financial, and regulatory risks:
1. **Accidental Capital Loss:** Defective algorithm logic, configuration errors, or runaway execution loops could issue unintentional orders into live financial markets.
2. **Credential & Network Exposure:** The transmission and handling of live broker authentication secrets (e.g., API keys, trade PINs, TOTP tokens) introduce credential leakage vulnerabilities.
3. **Regulatory Non-Compliance:** Unregistered algorithmic execution on Indian stock exchanges breaches SEBI regulations governing algorithmic trading infrastructure.
4. **Research Drift:** Allowing live trading paths inside a research and forward-simulation codebase contaminates execution models, complicates testing, and creates dual-purpose compromises.

A permanent, immutable architectural mechanism is required to guarantee that under no circumstance can the platform transmit orders to live market broker endpoints or deploy real capital.

## Decision
We permanently freeze all live trading capabilities and establish a multi-tier, fail-closed paper-only execution firewall across the entire codebase.

### 1. Canonical Immutable Constants in `src/version.py`
In [`src/version.py`](file:///home/ubuntu/algolab/src/version.py), the execution policy and safety flags are declared as typed, immutable constants:
```python
PAPER_ONLY_EXECUTION_POLICY: Final[bool] = True
LIVE_TRADING_ENABLED: Final[bool] = False
REAL_BROKER_EXECUTION_ENABLED: Final[bool] = False
```
These constants are the single authoritative source of truth. Under no circumstance may they be dynamically overridden or redefined.

### 2. Mandatory Fail-Closed Startup Invariant Enforcement
All entry points—including the FastAPI backend application ([`apps/api/main.py`](file:///home/ubuntu/algolab/apps/api/main.py)), the live market daemon ([`live_market_daemon.py`](file:///home/ubuntu/algolab/live_market_daemon.py)), background workers, and simulation runners—must invoke [`enforce_canonical_invariants()`](file:///home/ubuntu/algolab/src/version.py#L37) during initialization:
```python
def enforce_canonical_invariants() -> None:
    if LIVE_TRADING_ENABLED:
        raise RuntimeError("CRITICAL INVARIANT BREACH: LIVE_TRADING_ENABLED is True.")
    if REAL_BROKER_EXECUTION_ENABLED:
        raise RuntimeError("CRITICAL INVARIANT BREACH: REAL_BROKER_EXECUTION_ENABLED is True.")
```
If either invariant evaluates to `True`, the process terminates immediately with a critical exit code.

### 3. Application Configuration Fail-Closed Validation
In [`apps/api/core/config.py`](file:///home/ubuntu/algolab/apps/api/core/config.py), environment variable parsers reject any `.env` or system environment setting attempting to set `LIVE_TRADING_ENABLED=true` or `REAL_BROKER_EXECUTION_ENABLED=true`. The settings validator raises a `ValueError` during container or process startup.

### 4. AST Static Analysis Security Firewall
Automated verification tests ([`tests/unit/test_architecture_boundaries.py`](file:///home/ubuntu/algolab/tests/unit/test_architecture_boundaries.py) and [`scripts/verify_safety_invariants.py`](file:///home/ubuntu/algolab/scripts/verify_safety_invariants.py)) parse the Abstract Syntax Tree (AST) of the repository to ensure:
- No strategy, quant module, AI assistant, or API route imports live broker SDK execution functions (`place_order`, `modify_order`, `cancel_order`).
- Live order execution endpoints are strictly unreachable and unreferenced.

### 5. Automated CI/CD Safety Guard
The canonical release gate ([`Makefile`](file:///home/ubuntu/algolab/Makefile#L27)) executes `make safety-check` before any test or build action. Any violation blocks continuous integration pipelines.

## Non-Negotiable Safety Invariant Compliance
- **Does this decision preserve `LIVE_TRADING_ENABLED = False`?**  
  **Yes.** `LIVE_TRADING_ENABLED` is permanently frozen to `False` in [`src/version.py`](file:///home/ubuntu/algolab/src/version.py#L19). Process startup fails closed if modified.
- **Does it maintain independent risk engine authority?**  
  **Yes.** Paper execution order dispatching can only be triggered after authorization from the independent risk engine; direct order submission by strategies is architecturally prohibited.
- **Does it prevent synthetic data substitution in production paper paths?**  
  **Yes.** Production paper sessions require validated market snapshots and reject synthetic fallbacks at the data governance boundary.

## Consequences

### Positive
- **Complete Capital Risk Elimination:** Zero possibility of unintentional real-money orders, eliminating financial liability.
- **Regulatory Peace of Mind:** Guarantees strict compliance with Indian exchange and regulatory mandates by disallowing automated live execution.
- **Deterministic Testing:** All order matching follows internal paper simulation contracts ([`services/paper-engine/`](file:///home/ubuntu/algolab/services/paper-engine/) and [`services/backtest-engine/execution_contract.py`](file:///home/ubuntu/algolab/services/backtest-engine/execution_contract.py)) with realistic statutory fees.
- **Defense in Depth:** Enforced simultaneously via language typing (`Final[bool]`), runtime assertions, environment parsing, AST static analysis, and CI gates.

### Negative / Trade-offs
- **Simulation Only:** Platform users seeking direct broker API routing must maintain separate, non-integrated execution gateways outside the Algo Lab research boundary.
- **Rigid Configuration:** Any accidental commit modifying safety constants will instantly break local builds and CI pipelines.

## Compliance & Verification Evidence
- **Link to relevant tests:**
  - [`tests/unit/test_architecture_boundaries.py#L29-L57`](file:///home/ubuntu/algolab/tests/unit/test_architecture_boundaries.py#L29-L57) (`test_safety_flags_frozen`, `test_strategies_cannot_import_live_broker`)
  - [`tests/unit/test_health.py`](file:///home/ubuntu/algolab/tests/unit/test_health.py)
  - [`scripts/verify_safety_invariants.py`](file:///home/ubuntu/algolab/scripts/verify_safety_invariants.py)
- **Verification command:**
  ```bash
  make safety-check
  # or
  .venv/bin/python3 scripts/verify_safety_invariants.py
  ```
