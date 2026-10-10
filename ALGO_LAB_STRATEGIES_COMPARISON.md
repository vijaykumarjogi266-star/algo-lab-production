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
| CFI: Golden Cross | ₹3,712.79 | 0.73% | 40.00% | 1.15 | 6.86% | 80 | ₹6,491.75 |
| CFI: 5-8-13 Fibonacci EMA | ₹6,765.38 | 1.32% | 34.09% | 1.10 | 7.95% | 220 | ₹16,840.33 |
| CFI: Simple ADX Trend | ₹-9,078.50 | -1.89% | 30.77% | 0.39 | 10.27% | 52 | ₹3,027.56 |
| Prabhu: 8/20 EMA Pullback | ₹-5,666.98 | -1.16% | 20.00% | 0.75 | 11.84% | 30 | ₹4,303.97 |
| Prabhu: High-Volume PDH Follow-Through | ₹-10,955.76 | -2.29% | 17.14% | 0.62 | 10.96% | 35 | ₹3,866.62 |
