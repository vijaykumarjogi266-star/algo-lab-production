# Intraday Decision Engine Architecture

## Overview
The Intraday Decision Engine is a completely decoupled, pure-function evaluation layer. It acts as the brain of the trading system, transforming raw market bars, snapshots, technical indicators, and price action assessments into a strictly bounded `StrategyDecision`. 

It inherently distrusts market conditions, defaulting to `NO_TRADE` or `WAIT` unless explicit combinations of trend, structure, volatility, and liquidity are met.

## Inputs
- `MarketSnapshot`: Real-time quote and volume snapshot.
- `MarketBar`: Historical OHLCV bars.
- `TechnicalSignalSet`: Pure indicator values (EMA, SMA, VWAP, RSI, ATR, etc.).
- `PriceActionSignalSet`: Structural classification (higher highs, breakout status).
- `AccountContext`: Details about the trading strategy being evaluated and available capital.
- `SystemContext`: Global limits (kill switch, reconciliation broken status, OMS health).

## Outputs
Returns a single `StrategyDecision` which specifies:
- `DecisionType`: `NO_TRADE`, `WAIT`, `CREATE_ORDER_INTENT`, `REDUCE_ONLY_INTENT`, `EXIT_ALL_INTENT`, `HALT_NEW_ENTRIES`, `HALT_ALL`.
- `Rationale`: List of active conditions driving the decision.

## Market Regimes
- **BULLISH_TREND**: Price > VWAP, Fast MA > Slow MA, Higher Highs/Lows.
- **BEARISH_TREND**: Price < VWAP, Fast MA < Slow MA, Lower Highs/Lows.
- **RANGE_BOUND**: Mixed structure, compressed MAs.
- **HIGH_VOLATILITY**: ATR percentage exceeds defined threshold.
- **LOW_LIQUIDITY**: Relative volume below minimums.
- **DATA_UNAVAILABLE**: Stale snapshots.
- **UNCERTAIN**: Incomplete history or contradictory structure.

## Strategy Policy
Strategies are declarative objects (`BullishTrendPullbackStrategy`, `BearishTrendPullbackStrategy`, etc.) that restrict execution strictly to their declared `permitted_modes`. They cannot violate overarching gating constraints.

## Decision Gate Precedence
1. `HALT_ALL` (Kill switch, degraded OMS)
2. `EXIT_ALL_INTENT` (Hard EOD cutoff)
3. `HALT_NEW_ENTRIES` (Broken reconciliation, stale market data)
4. `NO_TRADE` (Opening exclusion window, entry cutoff reached)
5. `REDUCE_ONLY_INTENT` (Mandatory exit window)
6. Strategy-specific decisions (`CREATE_ORDER_INTENT`, `WAIT`, `NO_TRADE`).

## Non-Goals
- Does **not** directly interface with any broker API.
- Does **not** modify OrderLedgerDB or mutate risk reservations.
- Does **not** generate real execution events.
