#!/usr/bin/env python3
"""
Runs the 5 strategies for comparative backtesting on the Nifty 50.
"""

import sys
import os
import json
from pathlib import Path
from decimal import Decimal
import pandas as pd
import polars as pl
import yfinance as yf

# Setup repository paths
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from services.backtest_engine.adaptive_market_engine import (
    AdaptiveMarketSurvivalBacktester,
    ProductType,
)
from services.scanner.universe_manager import Nifty50UniverseManager


def ensure_cached_datasets(
    cache_dir: Path,
    symbols: list,
    years: int = 5,
) -> dict:
    cache_dir.mkdir(parents=True, exist_ok=True)
    datasets = {}
    period_str = f"{years}y"

    for sym in symbols:
        ticker_sym = f"{sym}.NS"
        p = cache_dir / f"{sym}_NS_{period_str}_1d.parquet"

        if not p.exists():
            print(f"Downloading {ticker_sym} ...")
            df = yf.Ticker(ticker_sym).history(period=period_str, interval="1d", auto_adjust=True)
            if df.empty:
                continue
            df = df.reset_index()
            df = df[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
            df["Date"] = df["Date"].dt.tz_localize(None)
            df.columns = ["date", "open", "high", "low", "close", "volume"]
            pl_df = pl.from_pandas(df)
            pl_df.write_parquet(p)
        else:
            pl_df = pl.read_parquet(p)

        datasets[sym] = pl_df
    return datasets


def main():
    universe_mgr = Nifty50UniverseManager()
    symbols = universe_mgr.get_symbols()
    sector_map = universe_mgr.get_sector_map()

    cache_dir = BASE_DIR / "data" / "cache"
    datasets = ensure_cached_datasets(cache_dir, symbols=symbols, years=5)

    strategies = [
        ("STRATEGY_A", "CFI: Golden Cross"),
        ("STRATEGY_B", "CFI: 5-8-13 Fibonacci EMA"),
        ("STRATEGY_C", "CFI: Simple ADX Trend"),
        ("STRATEGY_D", "Prabhu: 8/20 EMA Pullback"),
        ("STRATEGY_E", "Prabhu: High-Volume PDH Follow-Through"),
    ]

    results_table = []
    
    for strat_code, strat_name in strategies:
        print(f"Running {strat_name}...")
        engine = AdaptiveMarketSurvivalBacktester(
            initial_capital=100000.0,
            max_capital_per_position=45000.0,
            max_concurrent_positions=2,
            risk_per_trade_pct=0.010,
            product=ProductType.DELIVERY,
            stop_loss_atr_multiplier=2.5,
            take_profit_risk_multiplier=3.5,
            sector_map=sector_map,
            strategy=strat_code
        )
        
        results = engine.run_backtest(datasets)
        
        meta = results["metadata"]
        perf = results["performance_metrics"]
        fric = results["friction_breakdown"]
        
        horizon_years = 5.0
        cagr = ((meta["final_equity_inr"] / meta["initial_capital_inr"]) ** (1.0 / horizon_years) - 1.0) * 100.0
        
        results_table.append({
            "Strategy": strat_name,
            "Net Profit (₹)": f"₹{meta['net_profit_inr']:,.2f}",
            "CAGR (%)": f"{cagr:.2f}%",
            "Win Rate (%)": f"{perf['win_rate_pct']:.2f}%",
            "Profit Factor": f"{perf['profit_factor']:.2f}",
            "Max Drawdown (%)": f"{perf['max_drawdown_pct']:.2f}%",
            "Total Trades": perf['total_trades'],
            "Total Frictions Paid (₹)": f"₹{fric['total_friction_inr']:,.2f}"
        })

    # Generate Markdown Report
    report_path = Path("/home/ubuntu/algolab/ALGO_LAB_STRATEGIES_COMPARISON.md")
    with open(report_path, "w") as f:
        f.write("# Algo Lab: 5-Year Multi-Strategy Backtest Comparison (2021-2026)\n\n")
        f.write("## Execution & Risk Parameters\n")
        f.write("- **Universe**: Nifty 50\n")
        f.write("- **Timeframe**: Daily (1d)\n")
        f.write("- **Risk Rule**: Ed Thorp 1% Capital Risk\n")
        f.write("- **Concentration**: Max 1 position per sector\n")
        f.write("- **Execution Model**: Indian Statutory Cost Model (0.1% STT, ₹15.34 DP, etc.)\n")
        f.write("- **Safety**: `ALLOW_LIVE_TRADING = False`\n\n")
        
        f.write("## Strategy Performance Comparison\n\n")
        
        headers = ["Strategy", "Net Profit (₹)", "CAGR (%)", "Win Rate (%)", "Profit Factor", "Max Drawdown (%)", "Total Trades", "Total Frictions Paid (₹)"]
        f.write("| " + " | ".join(headers) + " |\n")
        f.write("|" + "|".join(["---"] * len(headers)) + "|\n")
        
        for r in results_table:
            row = [str(r[h]) for h in headers]
            f.write("| " + " | ".join(row) + " |\n")
            
    print(f"Report generated at {report_path}")

if __name__ == "__main__":
    main()
