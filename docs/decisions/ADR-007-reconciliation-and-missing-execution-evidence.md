# ADR 007: Reconciliation and Missing Execution Evidence

## Status
Accepted

## Context
Algo Lab requires a durable integrity layer (GAP-07 / T28 / T30) to reconcile the internal simulated/paper accounting state against external broker snapshots. In a distributed environment, external brokers may execute orders or adjust cash without immediate internal execution delivery. The OMS must handle these discrepancies safely.

## Decision
1. **Reconciliation Service**: We built `ReconciliationService` utilizing immutable snapshot models (`ReconciliationSnapshot`, `ExternalAccountSnapshot`, `ExternalPositionSnapshot`, `ExternalOrderSnapshot`, `ExternalExecutionEvidence`).
2. **Durable Database Breaks**: Discrepancies generate `reconciliation_breaks` (e.g. `CASH_MISMATCH`, `POSITION_MISMATCH`, `MISSING_EXECUTION_EVIDENCE`). These are stored alongside `reconciliation_runs`.
3. **No Automatic State Overwrite**: External evidence never silently overwrites the internal `cash_ledger`, `positions`, or `order_ledger`. The internal deterministic model is preserved exactly as recorded.
4. **Order Block Hold**: Any material or critical `OPEN` breaks automatically return `RECONCILIATION_HOLD_NEW_ENTRIES_BLOCKED` in `BrokerGateway.process_order_intent`. The `DecisionEngine` natively respects this hold by returning `HALT_NEW_ENTRIES`.
5. **Resolution**: A manual or external automated operator must provide evidence and rationale to move a break to `RESOLVED`, at which point the hold is cleared.

## Consequences
- Guaranteed preservation of internal truth in the event of missing or out-of-order execution webhooks.
- New entries are securely blocked upon material drift.
- Strong audit trail.
