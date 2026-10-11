# ADR 008: Historical Data Integrity, Checksum Verification, and Immutable Provenance

## Status
Accepted

## Context
In the Algo Lab Master Plan (Stage 1), every backtest, replay, and simulation must be strictly traceable to an immutable, validated local dataset. Without cryptographic verification, silent dataset alterations, duplicate timestamps, out-of-order ticks, or timezone mistakes could corrupt quantitative evaluations, lead to forward-looking bias, or hide data collection regressions.

## Decision
1. **Durable Dataset Registry**: Added `dataset_registry`, `dataset_quality_reports`, and `replay_runs` schema tables in SQLite.
2. **Cryptographic Checksums**: Every registered dataset requires an immutable SHA256 digest computed at ingestion.
3. **Fail-Closed Verification**: `verify_integrity(dataset_id)` recomputes the SHA256 checksum against disk content before any replay. If the checksum mismatches, the dataset status transitions immediately to `QUARANTINED` and execution is blocked with `ChecksumMismatchError`.
4. **Data Quality Validations**:
   - Duplicate timestamps per symbol are rejected.
   - Out-of-order timestamps are strictly rejected.
   - Non-positive prices and negative volumes are rejected.
   - Timezones are strictly validated against the standard IANA timezone database.
   - Market session boundaries and gaps are audited and reported.
5. **Replay Run Provenance**: Every replay run generates a durable `replay_run_id` cryptographically bound to `dataset_id`, `dataset_checksum`, and a deterministic `configuration_hash`.

## Consequences
- Guaranteed reproducibility of historical simulations.
- Tamper-evident protection across restarts.
- Zero future-data leakage through strict timestamp order enforcement.
