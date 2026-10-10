# ADR 005: Safe Shutdown and Recovery

## Context
When terminating the trading system, all new entries must stop immediately but existing submissions, partial executions, delayed fills, and uncertainties (T05/T10) must be handled gracefully to prevent capital loss.

## Decisions
1. **Shutdown state model**: `ShutdownState` enum added with `RUNNING`, `SHUTDOWN_REQUESTED`, `DRAINING`, `RECOVERY_REQUIRED`, `RECOVERING`, `RECONCILIATION_REQUIRED`, `STOPPED`, `FAILED_SAFE`.
2. **New-entry block policy**: Any intent lacking `reduce_only=True` is blocked with `SHUTDOWN_NEW_ENTRIES_BLOCKED` when shutdown is requested.
3. **Execution-ingestion policy**: Fills are always accepted, ensuring ledger and positions remain authoritative.
4. **Reduce-only policy**: `reduce_only=True` intents are allowed, but strictly verified to reduce net open exposure.
5. **Restart/recovery policy**: Shutdown state is persisted in `shutdown_sessions` and recovered on reboot.

