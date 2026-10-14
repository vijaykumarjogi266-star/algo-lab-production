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
| CFI: Golden Cross | ₹2,461.51 | 0.49% | 40.00% | 1.11 | 6.74% | 75 | ₹5,820.12 |
| CFI: 5-8-13 Fibonacci EMA | ₹668.15 | 0.13% | 30.72% | 1.01 | 10.09% | 153 | ₹10,883.58 |
| CFI: Simple ADX Trend | ₹-9,963.18 | -2.08% | 26.09% | 0.32 | 10.47% | 46 | ₹2,513.01 |
| Prabhu: 8/20 EMA Pullback | ₹-5,208.69 | -1.06% | 21.43% | 0.75 | 12.08% | 28 | ₹4,114.93 |
| Prabhu: High-Volume PDH Follow-Through | ₹-1,769.45 | -0.36% | 23.53% | 0.93 | 10.08% | 34 | ₹3,642.88 |
