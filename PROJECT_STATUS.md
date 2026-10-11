# Project Status

- **Proposed Canonical Root**: `/home/ubuntu/algolab` (canonical repository remains `/home/ubuntu/algolab`)
- **Verified OMS Suite Result**: `141 passed, 2 warnings`
- **Verified Components**: T06, T08, T09, T15, T05, T10, T18, T19, T20, Stage 1 Data Integrity, and Stage 2 Deterministic Replay are verified.
- **GAP-05 Status**: GAP-05 safe shutdown and recovery is resolved.
- **Shutdown Semantics**: Shutdown blocks new entries but preserves execution ingestion. Restart restores durable shutdown state and continues blocking entries until recovery/reconciliation requirements are met.
- **Trading Mode**:
  `TRADING_MODE=READ_ONLY`
  `ORDER_SUBMISSION_ENABLED=false`
  `ALLOW_LIVE_TRADING=false`
  `ALLOW_REAL_BROKER_EXECUTION=false`
- **Broker Safety**: No broker-connected paper or real trading is enabled.
- **Stage 1 (Historical Data Integrity & Provenance)**: RESOLVED. Cryptographic checksum verification, SQLite dataset registry, and fail-closed replay controls verified.
- **Stage 2 (Deterministic Historical Replay & Regime Evaluation)**: RESOLVED. ReplayClock, BoundedEventStream look-ahead protection, multi-symbol synchronization, regime classification, and durable replay reports verified.
- **Remaining P0 Work**: None. Core safety features, data integrity, and deterministic replay foundation complete.
- **Remaining Major Implementation Work**: Stage 3 (Internal Paper Exchange and Execution Realism).

## Safety Rules
All future work must occur only in the canonical repository.
Before changing code, inspect the existing implementation and tests.
Do not create another Algo Lab root.
Do not overwrite an entire file without reading it.
Do not merge modules from another repository without a documented comparison, test plan, Git branch, and rollback plan.
Every completed task must update CHANGELOG.md, PROJECT_STATUS.md, BASELINE_GAP_REGISTER.md, and test evidence.

## Decision Engine
- Intraday Market Regime and Strategy policy engine implemented.
- Fully separated boundary from execution/OMS logic.
- Safe by default; issues HALT and NO_TRADE upon uncertainty.

- **GAP-07 / T28 / T30**: RESOLVED. Fee, order status mismatches, restart persistence, and material entry blocks implemented and verified.
- **Stage 1 (Data Integrity & Provenance)**: RESOLVED. Immutable checksums, schema registry, and quarantine boundaries active.
