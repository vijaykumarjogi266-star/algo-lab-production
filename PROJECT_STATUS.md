# Project Status

- **Proposed Canonical Root**: `/home/ubuntu/algolab`
- **Test Evidence**: Full OMS suite run, resulting in 60 passed and 9 failed tests. T15 suite passed (7/7).
- **Verified OMS Components**: `OrderLedgerDB`, `executions_ledger`, `BrokerGateway`, `capital_reservations`, `CapitalReservationService`. T15 and T06/T08/T09 components are present and confirmed functioning in isolation.
- **Reported but Unverified Components**: T18, T19, T20 (Safe Shutdown), Full End-to-End Reconciliation.
- **Present Broker Integrations**: Angel One, KiteConnect (Zerodha), PaperExchange (Mock).
- **P&L/Capital/Reconciliation**: Subsystems exist but test failures indicate recent regressions in reconciliation match statuses.
- **Known Gaps**: See `BASELINE_GAP_REGISTER.md`. Timeouts (GAP-03), Shutdown (GAP-05), Full Reconciliation (GAP-07) and Fee Model (GAP-08).
- **Explicit Trading Mode**: READ_ONLY
- **Explicit Setting**: ORDER_SUBMISSION_ENABLED=false

## Safety Rules
All future work must occur only in the canonical repository.
Before changing code, inspect the existing implementation and tests.
Do not create another Algo Lab root.
Do not overwrite an entire file without reading it.
Do not merge modules from another repository without a documented comparison, test plan, Git branch, and rollback plan.
Every completed task must update CHANGELOG.md, PROJECT_STATUS.md, BASELINE_GAP_REGISTER.md, and test evidence.

## T15 Regression Repair Status
- Canonical root verified.
- All required OMS tests passing (69/69).
- Verified safety controls for T15 concurrency and idempotency.
- Trading remains READ_ONLY.
- Order submission remains disabled.
Commit: c6c48782bfd39ba053bc94c2132bc9b79ca2b8d4
