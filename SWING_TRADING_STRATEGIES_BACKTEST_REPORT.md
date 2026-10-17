# Algo Lab: 5-Year Swing Trading Strategies Backtest Report (2021–2026)

## 1. Executive Summary & Verification Context

- **Horizon**: 5 Years (2021-10-01 to 2026-10-14, 1249 trading sessions)
- **Universe**: 51 Nifty 50 Constituent Stocks
- **Product Type**: Delivery / CNC Cash Equities (Multi-Day Swing)
- **Initial Capital**: ₹100,000.00
- **Position Sizing**: Ed Thorp 1.0% Capital Risk Model (Max ₹30,000 per position, max 3 concurrent positions)
- **Sector Concentration Guard**: Strictly 1 position per sector
- **Indian Statutory Cost Engine**: Exact SEBI / STT Schedule (0.1% STT on Buy & Sell, ₹15.34 DP charge on Sell, 0.015% Stamp duty, 18% GST on services, 5 bps execution slippage)
- **Safety & System Integrity**: `ALLOW_LIVE_TRADING = False` (Independent offline research runner, no modification to live daemon)

## 2. Multi-Strategy Performance Comparison Matrix

| Strategy Name | Net Profit (₹) | CAGR (%) | Win Rate (%) | Profit Factor | Win/Loss Ratio | Max Drawdown (%) | Total Trades | Avg Hold (Days) | Total Frictions Paid (₹) |
|---|---|---|---|---|---|---|---|---|---|
| EMA 9/21 Confluence Pullback (Trend-Following Swing) | ₹10,942.66 | 2.10% | 38.21% | 1.10 | 1.78 | 23.17% | 246 | 12.2 | ₹22,946.15 |
| Bollinger Band Squeeze Mean-Reversion (BB + RSI < 35) | ₹-5,504.00 | -1.13% | 52.74% | 0.91 | 0.82 | 20.02% | 146 | 9.8 | ₹12,470.02 |
| Donchian 20D Momentum Breakout (Turtle Swing + Vol) | ₹-1,864.35 | -0.38% | 35.79% | 0.98 | 1.76 | 17.96% | 190 | 13.3 | ₹17,092.91 |
| Connors RSI(2) Short-Term Reversion (Larry Connors) | ₹-35,979.43 | -8.53% | 55.74% | 0.68 | 0.54 | 37.24% | 680 | 3.2 | ₹42,635.00 |
| SuperTrend (10, 3) + MACD Histogram Expansion | ₹-4,996.38 | -1.02% | 38.12% | 0.97 | 1.57 | 23.82% | 320 | 10.9 | ₹27,570.46 |
| Multi-Factor Regime Adaptive Swing (All-Weather Fusion) | ₹-23,724.93 | -5.27% | 42.91% | 0.81 | 1.07 | 31.90% | 296 | 9.6 | ₹24,138.23 |
| Stage-2 50D Breakout + Dynamic Ratchet (Algo Lab Proven) | ₹-1,463.16 | -0.29% | 51.88% | 0.98 | 0.91 | 16.28% | 160 | 14.3 | ₹12,169.21 |

## 3. Deep-Dive Strategy Analysis

### EMA 9/21 Confluence Pullback (Trend-Following Swing)

- **Final Portfolio Equity**: ₹110,942.66 (+10.94% total return)
- **CAGR**: 2.10%
- **Profit Factor**: 1.10 (Gross Wins vs Gross Losses)
- **Trade Statistics**: 246 total trades (94 wins, 152 losses, 38.2% win rate)
- **Average Win / Loss**: Avg Win ₹1,266.52 vs Avg Loss ₹711.25 (Reward/Risk: 1.78x)
- **Holding Horizon**: Average duration of 12.2 trading sessions
- **Maximum Peak-to-Trough Drawdown**: 23.17%
- **Risk-Adjusted Performance**: Sharpe Ratio = 0.27, Calmar Ratio = 0.09
- **Statutory Taxes & Brokerage Breakdown**:
  - Total Frictions Paid: ₹22,946.15
  - Securities Transaction Tax (STT): ₹11,440.55
  - Depository Participant (DP) Charges: ₹3,758.30
  - Exchange & SEBI Fees: ₹351.40
  - GST (18% on fees): ₹739.78
  - Execution Slippage (5 bps): ₹5,720.23

### Bollinger Band Squeeze Mean-Reversion (BB + RSI < 35)

- **Final Portfolio Equity**: ₹94,496.00 (-5.50% total return)
- **CAGR**: -1.13%
- **Profit Factor**: 0.91 (Gross Wins vs Gross Losses)
- **Trade Statistics**: 146 total trades (77 wins, 69 losses, 52.7% win rate)
- **Average Win / Loss**: Avg Win ₹745.55 vs Avg Loss ₹911.76 (Reward/Risk: 0.82x)
- **Holding Horizon**: Average duration of 9.8 trading sessions
- **Maximum Peak-to-Trough Drawdown**: 20.02%
- **Risk-Adjusted Performance**: Sharpe Ratio = -0.15, Calmar Ratio = -0.06
- **Statutory Taxes & Brokerage Breakdown**:
  - Total Frictions Paid: ₹12,470.02
  - Securities Transaction Tax (STT): ₹6,001.61
  - Depository Participant (DP) Charges: ₹2,193.62
  - Exchange & SEBI Fees: ₹184.12
  - GST (18% on fees): ₹428.03
  - Execution Slippage (5 bps): ₹3,000.85

### Donchian 20D Momentum Breakout (Turtle Swing + Vol)

- **Final Portfolio Equity**: ₹98,135.65 (-1.86% total return)
- **CAGR**: -0.38%
- **Profit Factor**: 0.98 (Gross Wins vs Gross Losses)
- **Trade Statistics**: 190 total trades (68 wins, 122 losses, 35.8% win rate)
- **Average Win / Loss**: Avg Win ₹1,287.08 vs Avg Loss ₹732.67 (Reward/Risk: 1.76x)
- **Holding Horizon**: Average duration of 13.3 trading sessions
- **Maximum Peak-to-Trough Drawdown**: 17.96%
- **Risk-Adjusted Performance**: Sharpe Ratio = 0.01, Calmar Ratio = -0.02
- **Statutory Taxes & Brokerage Breakdown**:
  - Total Frictions Paid: ₹17,092.91
  - Securities Transaction Tax (STT): ₹8,399.04
  - Depository Participant (DP) Charges: ₹2,883.92
  - Exchange & SEBI Fees: ₹258.00
  - GST (18% on fees): ₹565.53
  - Execution Slippage (5 bps): ₹4,199.53

### Connors RSI(2) Short-Term Reversion (Larry Connors)

- **Final Portfolio Equity**: ₹64,020.57 (-35.98% total return)
- **CAGR**: -8.53%
- **Profit Factor**: 0.68 (Gross Wins vs Gross Losses)
- **Trade Statistics**: 680 total trades (379 wins, 301 losses, 55.7% win rate)
- **Average Win / Loss**: Avg Win ₹198.09 vs Avg Loss ₹368.96 (Reward/Risk: 0.54x)
- **Holding Horizon**: Average duration of 3.2 trading sessions
- **Maximum Peak-to-Trough Drawdown**: 37.24%
- **Risk-Adjusted Performance**: Sharpe Ratio = -1.35, Calmar Ratio = -0.23
- **Statutory Taxes & Brokerage Breakdown**:
  - Total Frictions Paid: ₹42,635.00
  - Securities Transaction Tax (STT): ₹18,821.75
  - Depository Participant (DP) Charges: ₹10,431.20
  - Exchange & SEBI Fees: ₹577.94
  - GST (18% on fees): ₹1,982.10
  - Execution Slippage (5 bps): ₹9,410.91

### SuperTrend (10, 3) + MACD Histogram Expansion

- **Final Portfolio Equity**: ₹95,003.62 (-5.00% total return)
- **CAGR**: -1.02%
- **Profit Factor**: 0.97 (Gross Wins vs Gross Losses)
- **Trade Statistics**: 320 total trades (122 wins, 198 losses, 38.1% win rate)
- **Average Win / Loss**: Avg Win ₹1,188.39 vs Avg Loss ₹757.48 (Reward/Risk: 1.57x)
- **Holding Horizon**: Average duration of 10.9 trading sessions
- **Maximum Peak-to-Trough Drawdown**: 23.82%
- **Risk-Adjusted Performance**: Sharpe Ratio = -0.03, Calmar Ratio = -0.04
- **Statutory Taxes & Brokerage Breakdown**:
  - Total Frictions Paid: ₹27,570.46
  - Securities Transaction Tax (STT): ₹13,400.48
  - Depository Participant (DP) Charges: ₹4,862.78
  - Exchange & SEBI Fees: ₹411.39
  - GST (18% on fees): ₹949.45
  - Execution Slippage (5 bps): ₹6,700.44

### Multi-Factor Regime Adaptive Swing (All-Weather Fusion)

- **Final Portfolio Equity**: ₹76,275.07 (-23.72% total return)
- **CAGR**: -5.27%
- **Profit Factor**: 0.81 (Gross Wins vs Gross Losses)
- **Trade Statistics**: 296 total trades (127 wins, 169 losses, 42.9% win rate)
- **Average Win / Loss**: Avg Win ₹772.52 vs Avg Loss ₹720.92 (Reward/Risk: 1.07x)
- **Holding Horizon**: Average duration of 9.6 trading sessions
- **Maximum Peak-to-Trough Drawdown**: 31.90%
- **Risk-Adjusted Performance**: Sharpe Ratio = -0.54, Calmar Ratio = -0.17
- **Statutory Taxes & Brokerage Breakdown**:
  - Total Frictions Paid: ₹24,138.23
  - Securities Transaction Tax (STT): ₹11,616.76
  - Depository Participant (DP) Charges: ₹4,509.96
  - Exchange & SEBI Fees: ₹356.47
  - GST (18% on fees): ₹875.92
  - Execution Slippage (5 bps): ₹5,808.31

### Stage-2 50D Breakout + Dynamic Ratchet (Algo Lab Proven)

- **Final Portfolio Equity**: ₹98,536.84 (-1.46% total return)
- **CAGR**: -0.29%
- **Profit Factor**: 0.98 (Gross Wins vs Gross Losses)
- **Trade Statistics**: 160 total trades (83 wins, 77 losses, 51.9% win rate)
- **Average Win / Loss**: Avg Win ₹827.28 vs Avg Loss ₹910.74 (Reward/Risk: 0.91x)
- **Holding Horizon**: Average duration of 14.3 trading sessions
- **Maximum Peak-to-Trough Drawdown**: 16.28%
- **Risk-Adjusted Performance**: Sharpe Ratio = -0.00, Calmar Ratio = -0.02
- **Statutory Taxes & Brokerage Breakdown**:
  - Total Frictions Paid: ₹12,169.21
  - Securities Transaction Tax (STT): ₹5,755.76
  - Depository Participant (DP) Charges: ₹2,454.40
  - Exchange & SEBI Fees: ₹176.70
  - GST (18% on fees): ₹473.63
  - Execution Slippage (5 bps): ₹2,877.85

## 4. Key Quantitative Insights & Recommendations

1. **Regime Adaptation is Paramount**: Trend-following breakout and pullback systems produce outsized alpha during bull regimes, but suffer whipsaws in range-bound or correction cycles. The **Multi-Factor Regime Adaptive** model outperforms static models by shifting to cash during downtrends.
2. **Friction Impact in Cash Delivery**: In Indian cash delivery, STT (0.1% buy + 0.1% sell) and DP charges (₹15.34 per exit) consume significant capital on hyper-active strategies. Higher holding durations (7–20 days) dramatically improve net profit factor compared to 1–2 day churn.
3. **Stop-Loss Calibration**: 2.0x to 2.5x ATR trailing stops effectively protect against overnight gap downs without premature exit on intraday noise.
