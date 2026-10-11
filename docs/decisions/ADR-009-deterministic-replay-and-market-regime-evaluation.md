# ADR-009: Deterministic Historical Replay and Market-Regime Evaluation

## Context
In Stage 1 (ADR-008), immutable cryptographic provenance and fail-closed quality validation were established for all historical datasets.
In Stage 2 of the Algo Lab Master Plan, the system requires a deterministic simulation engine that guarantees zero future-data leakage (strict look-ahead protection), synchronizes multi-symbol universes in timestamp order, classifies market regimes, and records execution metrics into durable reports.

## Decision
1. **Replay Clock & Monotonicity**:
   - `ReplayClock` acts as the authoritative simulation clock.
   - It advances monotonically: any attempt to move backwards raises `ReplayClockMonotonicityError`.
   - It integrates with `NSECalendarService` to enforce regular trading hours (09:15 - 15:30 IST) and detect opening/closing volatility windows.
2. **Fail-Closed Look-Ahead Guard**:
   - `BoundedEventStream` maintains the historical event stream.
   - Any query or peek requesting timestamps strictly greater than `clock.current_time` raises `LookAheadBiasError`.
3. **Multi-Symbol Synchronization**:
   - Events across all universe symbols are strictly ordered by `(timestamp, symbol)`.
   - Replay steps advance monotonically in time, processing all symbols at $T$ before advancing to $T+1$.
4. **Market Regime Classification**:
   - Dynamic classification evaluates price action, rolling volatility, volume, and session times to identify `BULLISH_TREND`, `BEARISH_TREND`, `RANGE_BOUND`, `HIGH_VOLATILITY`, `LOW_VOLATILITY`, `LOW_LIQUIDITY`, `OPENING_CLOSING_VOLATILITY`, and `DEGRADED_DATA`.
   - Strategies can specify `allowed_regimes`, gating entry orders during unfavorable regimes.
5. **Durable Replay Execution Reports**:
   - Every completed replay run computes net P&L, drawdown, turnover, fees, slippage, and regime breakdowns.
   - The report is durably stored in the `replay_execution_reports` SQLite table, linking the run to its verified dataset and configuration.

## Consequences
- Guarantees 100% reproducible backtests with bit-for-bit mathematical identity across runs.
- Prevents look-ahead contamination in alpha strategies and decision engines.
- Connects historical simulation directly with virtual accounting and reconciliation.
