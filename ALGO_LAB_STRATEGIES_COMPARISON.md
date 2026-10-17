# Algo Lab: 5-Year Multi-Strategy Backtest Comparison (2021-2026)

## Execution & Risk Parameters
- **Universe**: Nifty 50
- **Timeframe**: Daily (1d)
- **Risk Rule**: Ed Thorp 1% Capital Risk
- **Concentration**: Max 1 position per sector
- **Execution Model**: Indian Statutory Cost Model (0.1% STT, ₹15.34 DP, etc.)
- **Safety**: `ALLOW_LIVE_TRADING = False`

## Strategy Performance Comparison

| Strategy | Net Profit (₹) | CAGR (%) | Win Rate (%) | Profit Factor | Max Drawdown (%) | Total Trades | Total Frictions Paid (₹) |
|---|---|---|---|---|---|---|---|
| CFI: Golden Cross | ₹995.01 | 0.20% | 41.25% | 1.04 | 6.76% | 80 | ₹6,415.29 |
| CFI: 5-8-13 Fibonacci EMA | ₹9,200.54 | 1.78% | 34.09% | 1.13 | 8.79% | 220 | ₹16,828.14 |
| CFI: Simple ADX Trend | ₹-9,148.49 | -1.90% | 33.33% | 0.34 | 10.08% | 48 | ₹2,755.04 |
| Prabhu: 8/20 EMA Pullback | ₹-4,906.05 | -1.00% | 20.83% | 0.75 | 12.42% | 24 | ₹3,362.51 |
| Prabhu: High-Volume PDH Follow-Through | ₹-10,564.29 | -2.21% | 18.18% | 0.64 | 11.58% | 33 | ₹3,691.06 |
