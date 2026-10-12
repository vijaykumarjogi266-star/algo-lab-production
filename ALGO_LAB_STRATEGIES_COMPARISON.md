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
| CFI: Golden Cross | ₹779.46 | 0.16% | 37.97% | 1.03 | 6.86% | 79 | ₹6,224.56 |
| CFI: 5-8-13 Fibonacci EMA | ₹-1,568.77 | -0.32% | 31.14% | 0.98 | 9.96% | 228 | ₹16,564.24 |
| CFI: Simple ADX Trend | ₹-8,671.49 | -1.80% | 26.42% | 0.45 | 10.22% | 53 | ₹2,990.74 |
| Prabhu: 8/20 EMA Pullback | ₹-6,564.54 | -1.35% | 20.59% | 0.74 | 12.14% | 34 | ₹5,041.39 |
| Prabhu: High-Volume PDH Follow-Through | ₹-10,853.79 | -2.27% | 17.14% | 0.63 | 10.85% | 35 | ₹3,707.96 |
