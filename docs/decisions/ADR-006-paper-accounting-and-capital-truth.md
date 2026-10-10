# ADR 006: Paper Accounting and Capital Truth

## Status
Accepted

## Context
Algo Lab requires a durable, restart-safe accounting layer to act as the ultimate truth for capital and P&L. Without this, paper trading is susceptible to floating point errors, state drift, and race conditions. We need absolute determinism around cash, positions, and lots to fulfill Phase 3 constraints and enable reliable reconciliation (T28/T30).

## Decision
1. **Decimal Types**: All money, price, fee, quantity, exposure, and P&L calculations strictly use `Decimal`.
2. **Persistence**: Accounting ledgers (cash, positions, lots) are stored in `sqlite3` using `TEXT` to guarantee 100% precision with no floating-point coercion on disk.
3. **Idempotency & Execution Application**: `AccountingService` intercepts verified state-machine transitions and execution reports. It updates cash and positions synchronously. `sqlite3.IntegrityError` guarantees duplicate fills (e.g., from webhook retry) are ignored.
4. **FIFO Lot Matching**: Partial closes resolve against oldest lots.
5. **Separation of Risk vs Capital**: Active reservations do not subtract from the `cash_ledger` directly; they are subtracted at read-time to calculate `available_capital`.
6. **₹100,000 Starting Capital**: Enforced via a `PAPER_DEFAULT` account initialization check that creates exactly one `OPENING_BALANCE` of `100000.00` INR exactly once.

## Consequences
- Guaranteed zero fractional penny drift.
- Restart-safe and exactly-once processing for executions.
- Read queries require parsing `TEXT` to `Decimal`, which has minor overhead but is perfectly precise.
- Opens path to full reconciliation since cash bounds are absolute.
