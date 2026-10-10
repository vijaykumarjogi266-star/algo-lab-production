# Intraday Decision Engine Operations

## Strategy Disablement
Strategies can be explicitly set to `StrategyStatus.DISABLED` in the `StrategyRegistry` initialization. This prevents them from generating anything other than a `NO_TRADE` decision, regardless of market regime.

## Kill Switch Activation
If `kill_switch_active=True` is passed within the `SystemContext` to the `DecisionEngine.evaluate()` method, the system instantly bypasses all internal evaluations and returns `HALT_ALL`. This propagates downstream to prevent any new exposure from being assumed.

## Handling Stale Market Data
If a market snapshot's `data_freshness_seconds` exceeds 60, the Market Regime classifier identifies it as `DATA_UNAVAILABLE`. The `DecisionGate` then overrides any underlying strategy decision, issuing `HALT_NEW_ENTRIES` citing `MARKET_DATA_INVALID_OR_STALE`.

## End-Of-Day Behavior
The Session Policy enforces three phases at the end of the day:
1. **Entry Cutoff**: Stops all new entries (`NO_TRADE`).
2. **Mandatory Exit Cutoff**: Prevents new entries, permitting only `REDUCE_ONLY_INTENT` or `EXIT_ALL_INTENT`.
3. **Hard Cutoff**: Forces `EXIT_ALL_INTENT`.

## Reviewing Decision Rationale
The resulting `StrategyDecision` explicitly retains the causal link for its output. Inspect `decision.rationale` and `decision.blocking_reasons` to evaluate exactly why a `NO_TRADE` or `WAIT` was emitted (e.g., `["WAITING_FOR_VWAP_RECLAIM"]`, `["UNSAFE_REGIME_HIGH_VOLATILITY"]`).
