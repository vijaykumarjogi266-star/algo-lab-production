# Paper Account and P&L Operations

## Overview
Algo Lab utilizes an isolated internal paper-trading account instantiated strictly at `₹100,000` capital. The ledger tracks everything in precise Decimal format and prevents floating-point inaccuracies.

## Invariants
- `TRADING_MODE=READ_ONLY` strictly observed.
- Capital reservations (T15) deduct from equity to determine `available_capital`, but do not immediately emit cash ledger events. Cash events are strictly generated upon confirmed `EXECUTION`.
- Restart logic retrieves the state from SQLite `paper_accounts`, `cash_ledger`, `positions`, and `position_lots` precisely.

## Mark-to-Market
- Realized P&L is locked when lots are closed FIFO.
- Unrealized P&L updates based on `BrokerGateway.set_market_price()` without mutating cash balances.
