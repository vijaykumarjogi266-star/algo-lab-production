
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

## Deterministic Historical Replay & Market-Regime Evaluation (Stage 2)
- Built `ReplayClock` with monotonic time advancement and Indian market calendar / session awareness (09:15-15:30 IST).
- Enforced strict look-ahead protection with `BoundedEventStream` and `LookAheadBiasError` for zero future-data leakage.
- Multi-symbol synchronization strictly ordered by `(timestamp, symbol)`.
- Dynamic market regime detection classifying trend, range, volatility, liquidity, session window, and degraded data.
- Regime-aware gating blocking new entries during non-permitted market conditions.
- Durable `replay_execution_reports` persisting P&L, drawdown, turnover, fees, slippage, and regime breakdown.

## Internal Paper Exchange & Execution Realism (Stage 3)
- Implemented `OrderType` (`MARKET`, `LIMIT`) with order book resting state and matching mechanics.
- `PaperExchange` incorporates `AdverseExecutionProfile` modeling:
  - Bid/ask spread expansion (`base_spread_bps`).
  - Linear/quadratic slippage factors proportional to trade size and participation rate.
  - Indian equity fee schedules (bps turnover + fixed per-order ticket fees).
  - Liquidity caps enforcing maximum participation of bar/tick volume.
  - Partial fill (`PARTIAL`) and no-fill/rejection (`NO_FILL`) modes simulating adverse liquidity.
  - Unfunded reduce-only rejection safeguards.
- Intraday session close handler (`on_session_close`) auto-cancelling open resting orders.
- Sensitivity matrix generation evaluating trade outcomes across multi-dimensional spread and slippage grids.
- Gateway level risk reservation release on exchange-level rejections to eliminate phantom capital reservation.

## Decision Engine, Candidate Intents & Market Adaptability (Stage 4)
- Formalized `CandidateIntent` lifecycle (`CANDIDATE` -> `RISK_APPROVED` -> `SIZED` -> `DISPATCHED`).
- Complete separation between alpha strategies (proposing candidate intents) and execution routing.
- Immutable transition audit trails with timestamps, rationales, and metadata.
- `ProfileTransitionManager` managing adaptation profiles (`TRENDING`, `CHOPPY`, `HIGH_VOLATILITY`, `LOW_LIQUIDITY`, `DEGRADED_DATA`, `NORMAL`):
  - Confirmation threshold preventing whipsaws from temporary market noise.
  - Emergency fail-closed escalation into `DEGRADED_DATA` and `HIGH_VOLATILITY`.
  - Hysteresis cooldown suppressing premature de-escalation from adverse regimes.
- Adaptive risk sizing: volatility downscaling, liquidity participation caps, and fail-closed `DEGRADED_DATA` entry blocks.
- End-to-end integration across Stage 2 ReplayClock/RegimeEvaluator and Stage 3 PaperExchange.
