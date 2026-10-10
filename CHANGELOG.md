
## [Unreleased]
### Added
- GAP-07 (T28/T30): Built deterministic ReconciliationService to safely halt entries if external broker evidence conflicts with internal ledgers, preserving internal truth.
- GAP-08: Implemented fully deterministic, Decimal-based virtual paper portfolio accounting layer (cash ledger, lots, fees, realized/unrealized P&L) isolated inside the OMS sandbox.
- GAP-03: Hardened handling for order submission and cancellation timeouts (T05 and T10), preserving capital reservation, risk exposure, and implementing durable broker uncertainty records.
Implemented Intraday Decision Engine with strict safety boundaries and market regime classifications.

Regression repair after T15 concurrent reservation integration (Commit: c6c48782bfd39ba053bc94c2132bc9b79ca2b8d4)

# Changelog

## [Unreleased] - Algo Lab Hardening T15

### Added
- **Database Schema Additions**: Added `capital_reservations` table to `OrderLedgerDB` to durably store capital reservations with constraints on `(account_id, idempotency_key)`.
- **CapitalReservationService**: Created `oms_project/reservation_service.py` to handle concurrent risk reservation securely.
- **Concurrency Approach**: Utilized SQLite's native `BEGIN EXCLUSIVE` transaction isolation strategy to provide full serializability and block parallel processes from overselling or double-booking capital. Retries are implemented to handle momentary SQLite database locks seamlessly.
- **Idempotency Behavior**: Improved idempotency check to securely replay the original economic result (reservation outcome or cache hit) instead of blindly throwing a duplicate request error, solving race condition collisions when multiple threads attempt submission simultaneously.
- **Test Coverage**: Added `test_concurrent_risk_reservation.py` (T15 suite) asserting against concurrent oversubscription, same-key idempotency, different-key limits, failure rollbacks, partial fill reservation logic, and unknown state protection.

### Changed
- **Order-Lifecycle Integration**: `BrokerGateway` now hooks into the `CapitalReservationService` before generating an order or dispatching to the exchange. If the atomic check rejects the transaction, no submission path is traversed.
- **Schema**: Fixed missing foreign key constraints on `state_transitions` and verified strict database constraints.

### Limitations
- **Fee Configuration**: The initial risk reservation calculation doesn't explicitly deduct full dynamic fee variables yet; currently uses fixed `requested_notional`.
- **Database Scalability**: Relying on `BEGIN EXCLUSIVE` inside SQLite is extremely robust for single-node isolated backtesting and paper trading (fulfilling requirements), but will cause contention lock-timeouts if the concurrency load exceeds hundreds of transactions per second on the same file.
- GAP-05: Implemented Safe Shutdown and Recovery (Commit 28e4d16)

## [Unreleased]
### Added
- GAP-07 Follow-ups:
  - Fee mismatch reconciliation using `cash_ledger`.
  - Order status mismatch checks preventing state overriding without evidence.
  - Verification of restart persistence for material breaks.
  - Strict entry-block release mechanism relying on terminal break states.
