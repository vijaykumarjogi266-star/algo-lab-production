
# Changelog
All notable changes to Algo Lab will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-10-14 — Institutional Hardening & Paper-Only Remediation
### Added
- **Single Source of Truth:** Created `src/version.py` tracking canonical version (`0.3.0`), lifecycle state (`forward-paper-validation`), and non-negotiable safety invariants.
- **CI/CD Quality Gate:** Added canonical `Makefile` with `make release-check` enforcing typechecks, static security scan (Bandit), secret scans, dependency locks, and SBOM generation.
- **API Security & RBAC:** Implemented granular roles (`viewer`, `researcher`, `operator`, `risk_admin`, `system_admin`), constant-time token comparison, key hashing at rest, and hardened Content Security Policy.
- **Data Governance:** Implemented typed dataset manifest schema (`services/data_governance/manifest.py`) enforcing SHA256 checksums, exchange timestamp boundaries, and rejection of synthetic fallback data.
- **Execution Simulator Contract:** Formalized execution simulator contract (`services/backtest-engine/execution_contract.py`) making all slippage, fees, and queueing assumptions explicit.
- **Architectural Boundary Enforcement:** Added architecture firewall test (`tests/unit/test_architecture_boundaries.py`) proving strategies and AI modules cannot route real orders or bypass the independent risk engine.
- **Backup & Restore Operations:** Added automated encrypted backup/restore tooling with integrity verification (`scripts/backup_restore.py`).
- **Free AI Model Inference:** Integrated zero-key free AI inference with automatic fallback for CLI guidance and code review.

### Changed
- Aligned semantic version `0.3.0` across `pyproject.toml`, API responses, Docker configurations, and documentation.
- Hardened `apps/api/core/config.py` and `live_market_daemon.py` with explicit fail-closed runtime checks on `LIVE_TRADING_ENABLED` and `REAL_BROKER_EXECUTION_ENABLED`.
- Updated `services/backtest-engine/statutory_cost_model.py` and `live_market_daemon.py` for exact Indian delivery statutory tax attribution (STT, Stamp Duty, DP charges, GST).

## [0.2.0] - 2026-10-12
### Added
- Paper Engine: Implemented `ClockProtocol` with `SystemClock` and deterministic `FrozenClock` in `services/paper-engine/trailing_stop_engine.py` to eliminate wall-clock coupling in test suites.
- Daemon Lifecycle: Wired mandatory 15:15 IST intraday auto-square-off directly into `LiveAlgoLabDaemon.step()` (`EOD_TRADE_EXECUTION` phase) to ensure no paper MIS positions leak past market close.
- Scanner & Universe: Integrated `DeepMultiIntervalScanner` across 5m, 15m, 1h, and 1d timeframes with Nifty 100 constituent tracking and regime confluence classification.
- Quantitative Validation: Built stress-testing matrix and drawdown sensitivity curves in `services/backtest-engine/stress_testing_engine.py`.
- Regression Suite: Verified 201/201 deterministic tests passing (175 OMS/Decision tests + 26 Unit/Scanner/Stress/Backtest tests).
- Stage 4: Implemented `CandidateIntent` lifecycle (`CANDIDATE` -> `RISK_APPROVED` -> `SIZED` -> `DISPATCHED`) with immutable audit trails in `oms_project/candidate_intent.py`.
- Stage 4: Built `ProfileTransitionManager` with confirmation thresholds, emergency fail-closed escalations (`DEGRADED_DATA`, `HIGH_VOLATILITY`), and hysteresis cooldown to prevent whipsawing.
- Stage 4: Implemented `Stage4DecisionEngine` with dynamic risk sizing (volatility scaling, liquidity caps, cash checks) and end-to-end integration into `PaperExchange`.
- Stage 4: Added dedicated test suite `oms_project/tests/test_stage4_decision_engine.py` (11 tests passing, full test suite at 160 tests).
- Stage 3: Enhanced `PaperExchange` with `AdverseExecutionProfile` modeling bid/ask limit books, queue priority matching, non-linear slippage, fee schedules, liquidity caps, partial/no-fill modes, EOD session-end auto-cancellations, and sensitivity matrix generation.
- Stage 3: Updated `BrokerGateway` to support `OrderType.LIMIT` with resting state and release reserved capital on exchange rejection.
- Stage 3: Added dedicated test suite `oms_project/tests/test_paper_exchange_realism.py` (8 tests passing, regression suite at 149 tests).
- Stage 2: Implemented `ReplayClock` with monotonic clock advancement and session awareness (`Asia/Kolkata` trading hours).
- Stage 2: Built `BoundedEventStream` and `LookAheadBiasError` enforcing strict look-ahead protection with multi-symbol synchronization.
- Stage 2: Added `RegimeEvaluator` classifying market regimes (trend, range, volatility, liquidity, session window, degraded data) and gating decisions.
- Stage 2: Built `ReplayExecutionEngine` persisting durable simulation metrics into `replay_execution_reports` table with bit-for-bit determinism.
- Stage 2: Added comprehensive test suite in `oms_project/tests/test_deterministic_replay.py` (8 tests passing, regression suite at 141 tests).
- Stage 1: Implemented `HistoricalDataRegistry` and `DataValidator` enforcing immutable dataset provenance, cryptographic SHA256 checksums, and fail-closed replay boundaries.
- Stage 1: Added schema tables `dataset_registry`, `dataset_quality_reports`, and `replay_runs` to SQLite database.
- Stage 1: Integrated tamper-detection into `HistoricalReplayEngine.load_verified_dataset`, automatically quarantining corrupted files and preventing replay.
- Stage 1: Added comprehensive validation suite in `oms_project/tests/test_data_integrity.py` asserting checksum enforcement, duplicate/out-of-order detection, timezone validation, and restart survival.
- GAP-07 (T28/T30): Built deterministic ReconciliationService to safely halt entries if external broker evidence conflicts with internal ledgers, preserving internal truth.
- GAP-08: Implemented fully deterministic, Decimal-based virtual paper portfolio accounting layer (cash ledger, lots, fees, realized/unrealized P&L) isolated inside the OMS sandbox.
- GAP-03: Hardened handling for order submission and cancellation timeouts (T05 and T10), preserving capital reservation, risk exposure, and implementing durable broker uncertainty records.
- Implemented Intraday Decision Engine with strict safety boundaries and market regime classifications.

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
