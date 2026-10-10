# ADR-003: Intraday Autonomous Decision Boundary

## Context
The Algo Lab repository implements a strict separation of concerns to prevent catastrophic trade duplication, limit breaches, and runaway behavior. The OMS controls ledger state, cash, and risk. We need a secondary component to analyze market environments and determine trading actions safely.

## Decision
We are decoupling the autonomous trading logic into a completely side-effect-free `DecisionEngine`.
- **Pure Function Constraints**: The decision boundary relies solely on input MarketSnapshots and contexts. It does not hit the network or query internal databases. 
- **Intraday Scope**: The decision engine limits operations strictly to intraday execution. It guarantees safety via End-Of-Day cutoffs to eliminate overnight risk exposure.
- **Default Deny / No-Trade**: If technicals are incomplete, if price structure contradicts moving averages, or if volatility metrics expand beyond predefined limits, the engine will deterministically output `UNCERTAIN` regimes and `NO_TRADE` or `WAIT` decisions.

## Consequences
- **Testing**: Highly robust testing is easily achieved by mocking raw data arrays and advancing an injected clock.
- **Safety**: A logic bug in the Decision Engine cannot independently place a trade, loop indefinitely, or violate limits, because it still depends upon the `BrokerGateway` for execution.
- **Extensibility**: Complex regimes (Event Risk, Low Liquidity) natively block strategy execution without altering individual strategy code.
