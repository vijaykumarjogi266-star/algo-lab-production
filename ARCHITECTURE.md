
## Repository Safety Rules
All future work must occur only in the canonical repository.
Before changing code, inspect the existing implementation and tests.
Do not create another Algo Lab root.
Do not overwrite an entire file without reading it.
Do not merge modules from another repository without a documented comparison, test plan, Git branch, and rollback plan.
Every completed task must update CHANGELOG.md, PROJECT_STATUS.md, BASELINE_GAP_REGISTER.md, and test evidence.
- Shutdown Recovery: Ensures graceful pause, reduce-only blocks, and persistence via shutdown_sessions

## Reconciliation (GAP-07 Updates)
- Added continuous checks for fee mismatches and order status mismatches.
- Hardened the material entry block to dynamically cover INVESTIGATING states and clear only upon acceptable terminal resolution.

## Historical Data Integrity & Provenance (Stage 1)
- Built `HistoricalDataRegistry` backed by SQLite tables `dataset_registry`, `dataset_quality_reports`, and `replay_runs`.
- Cryptographic SHA256 checksums calculated upon registration and re-verified before any replay invocation.
- Tamper detection triggers automatic dataset quarantine (`QUARANTINED`) and blocks replay via `ChecksumMismatchError`.
- Integrated `DataValidator` enforcing monotonic timestamps, duplicate detection, valid prices/volumes, and IANA timezone validation.
- Every replay execution is immutably linked to dataset ID, dataset version, checksum, and configuration hash.
