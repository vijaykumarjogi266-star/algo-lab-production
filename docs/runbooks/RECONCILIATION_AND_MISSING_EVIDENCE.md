# Runbook: Reconciliation and Missing Evidence

When the internal state deviates from the external broker:
1. `ReconciliationService` compares internal `positions`, `cash_ledger`, and `order_ledger` to an ingested `ReconciliationSnapshot`.
2. Material deviations log a `reconciliation_break` tied to a specific `reconciliation_run`.
3. The OMS safely halts all new risk by throwing `RECONCILIATION_HOLD_NEW_ENTRIES_BLOCKED`.
4. The system administrator or reconciliation microservice must inspect the log and invoke `resolve_break(break_id, evidence, rationale)` before trading can continue.
5. Internal ledgers MUST NEVER be silently overwritten. Any required fixes involve new accounting entries (e.g. `ADJUSTMENT` in `cash_ledger`).

## Follow-Up Additions
- **Fee Discrepancies**: Handled by FEE_MISMATCH break type. Compares external fee against cash_ledger FEE entry.
- **Order Status**: order states are cross-checked. A material mismatch blocks new entries until resolved or marked false positive.
- **Entry Blocking**: Re-evaluated dynamically on restart based on current breaks in the DB.
