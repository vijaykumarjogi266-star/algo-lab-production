# Stage 2: Deterministic Historical Replay & Market-Regime Evaluation Results

## Execution Timestamp
2026-10-11T15:25:29Z

## Test Suite Summary
- Dedicated Module: `oms_project/tests/test_deterministic_replay.py` (8 passed)
- Full Regression: 141 passed, 2 warnings in 10.24s across all 27 test modules.

## Detailed Results by Requirement

| Requirement | Test Scenario | Status | Evidence |
|---|---|---|---|
| Replay Clock & Monotonicity | `test_replay_clock_monotonicity_and_session_awareness` | PASSED | Monotonic clock advances, backward movement raises `ReplayClockMonotonicityError`, NSE session hours (09:15-15:30) and opening/closing windows enforced |
| Look-Ahead Bias Guard | `test_strict_look_ahead_bias_prevention` | PASSED | Querying beyond current virtual timestamp or calling `peek_future()` raises `LookAheadBiasError` fail-closed |
| Multi-Symbol Synchronization | `test_multi_symbol_synchronization` | PASSED | Out-of-order multi-symbol universe sorted strictly by `(timestamp, symbol)` and advanced deterministically |
| Market Regime Classification | `test_market_regime_classification_across_regimes` | PASSED | Successfully classifies `OPENING_CLOSING_VOLATILITY`, `BULLISH_TREND`, `BEARISH_TREND`, `LOW_LIQUIDITY`, and `DEGRADED_DATA` |
| Regime-Aware Gating | `test_regime_aware_strategy_gating` | PASSED | Restricting mean reversion to `HIGH_VOLATILITY` blocks all orders during `RANGE_BOUND`; allowing permitted regimes executes trades with `MATCH` reconciliation |
| End-to-End Pipeline & Reports | `test_full_replay_pipeline_from_verified_dataset_to_durable_report` | PASSED | Full flow from verified dataset to durable `replay_execution_reports` SQLite row with net P&L, fees, slippage, and turnover |
| Bit-for-Bit Determinism | `test_determinism_proof_bit_for_bit_identical_runs` | PASSED | Repeated runs on identical inputs yield bit-identical metrics (P&L, drawdown, turnover, fees, fills) to 8 decimal places |
| Tamper Fail-Closed | `test_tampered_dataset_blocks_replay_execution` | PASSED | On-disk dataset mutation raises `ChecksumMismatchError` and quarantines dataset before simulation starts |
