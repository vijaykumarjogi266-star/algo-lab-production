# ADR-010: Internal Paper Exchange and Execution Realism

## Context
In Stage 2 (ADR-009), deterministic historical replay with look-ahead protection and market regime evaluation was completed.
In Stage 3 of the Algo Lab Master Plan, the system requires an internal paper exchange and execution realism engine to test adverse trading conditions (partial fills, no fills, slippage, spread crossing, fee schedules, liquidity constraints, resting limit orders, and session-close lifecycle) without broker submission.

## Decision
1. **Order Typing & Matching**:
   - Supported order types: `MARKET` and `LIMIT`.
   - `MARKET` orders execute immediately against the current market price with spread and slippage adjustments.
   - `LIMIT` orders are checked against the reference market price:
     - For BUY: marketable only if `market_price <= limit_price`.
     - For SELL: marketable only if `market_price >= limit_price`.
     - Unmarketable limit orders enter the internal resting order book (`resting_orders`) in `LIVE` state and are matched dynamically on subsequent market ticks via `on_market_tick`.
2. **Reduce-Only Protection**:
   - `reduce_only` orders require an active opposing position and strictly reject attempts to open new positions or overshoot existing positions (`REJECTED_REDUCE_ONLY_NO_LONG_POSITION`, `REJECTED_REDUCE_ONLY_NO_SHORT_POSITION`, `REJECTED_REDUCE_ONLY_EXCEEDS_POSITION`).
3. **Adverse Execution Realism Model**:
   - Parameterized via `AdverseExecutionProfile`:
     - `fill_mode`: `FULL`, `PARTIAL`, `NO_FILL`.
     - `slippage_bps`, `spread_bps`, `fee_rate_bps`.
     - `liquidity_cap_qty` and `max_participation_pct`.
     - Simulated rejections (e.g., `EXCHANGE_CIRCUIT_LIMIT_BREACHED`) and simulated network timeouts (`simulate_timeout=True`).
4. **Lifecycle & Capital Accounting**:
   - Releasing risk reservation on exchange rejections.
   - Auto-cancellation of all resting limit orders upon session close (`session_close`) with reason `CANCELLED_EOD_SESSION_CLOSE`.
   - Resting orders survive restart in SQLite with state `LIVE`.
5. **Cost & Slippage Sensitivity Matrix**:
   - `generate_sensitivity_report` models execution drag across multidimensional matrices of slippage and spread levels.

## Consequences
- Enables rigorous testing of realistic market friction and adverse exchange events without external broker risk.
- Reconciles virtual positions, cash, and fees with mathematical precision.
