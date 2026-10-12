#!/usr/bin/env python3
"""
Algo Lab Backtest Stress Testing & Drawdown Sensitivity CLI Runner.
Executes multi-regime stress testing, slippage sensitivity analysis, and tail-risk drawdown
profiling across active strategies using 5-year historical daily datasets (2021–2026).
Saves audit evidence to data/processed/strategy_stress_testing_sensitivity_report.json.
"""

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys
import polars as pl

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from services.backtest_engine.stress_testing_engine import (
    StressTestingEngine,
    ACTIVE_STRATEGIES,
)
from services.scanner.universe_manager import Nifty50UniverseManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("StressTestingRunner")


def load_cached_datasets(cache_dir: Path, symbols: list) -> dict:
    """Loads cached 5-year constituent parquets from cache directory."""
    datasets = {}
    print(f"\n📂 Loading 5-Year Historical Daily Datasets from: {cache_dir}")
    for sym in symbols:
        p = cache_dir / f"{sym}_NS_5y_1d.parquet"
        if p.exists():
            df = pl.read_parquet(p)
            datasets[sym] = df
        else:
            # Fallback to alternate naming if present
            alt_p = cache_dir / f"{sym}_NS_60d_1d.parquet"
            if alt_p.exists():
                datasets[sym] = pl.read_parquet(alt_p)

    print(f"✅ Loaded {len(datasets)} constituent parquets successfully.")
    return datasets


def main():
    parser = argparse.ArgumentParser(description="Algo Lab Backtest Stress Testing & Drawdown Sensitivity")
    parser.add_argument(
        "--strategies",
        nargs="+",
        default=[s[0] for s in ACTIVE_STRATEGIES],
        help="Strategies to stress test (default: all)",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=100000.0,
        help="Initial capital in INR (default: 100,000.0)",
    )
    args = parser.parse_args()

    cache_dir = BASE_DIR / "data" / "cache"
    universe_mgr = Nifty50UniverseManager()
    symbols = universe_mgr.get_symbols()
    sector_map = universe_mgr.get_sector_map()

    datasets = load_cached_datasets(cache_dir, symbols)
    if not datasets:
        print("[ERROR] No cached parquets found in data/cache. Cannot run stress testing.")
        sys.exit(1)

    print("\n" + "=" * 105)
    print(" 🛡️  ALGO LAB ACTIVE STRATEGIES STRESS TESTING & DRAWDOWN SENSITIVITY ENGINE")
    print(f"    Constituents: {len(datasets)} liquid leaders | Capital: ₹{args.capital:,.2f} | Execution: Delivery / CNC")
    print(f"    Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
    print("=" * 105)

    engine = StressTestingEngine(
        datasets=datasets,
        sector_map=sector_map,
        initial_capital=args.capital,
    )

    full_report = engine.execute_comprehensive_stress_test(strategies=args.strategies)

    # Display Institutional Tear Sheets per Strategy
    for strat_code in args.strategies:
        strat_info = full_report["strategies"].get(strat_code)
        if not strat_info:
            continue

        s_name = strat_info["strategy_name"]
        print("\n" + "#" * 105)
        print(f" STRATEGY: {s_name} [{strat_code}]")
        print("#" * 105)

        # 1. Market Regime Breakdown
        print("\n 🌐 1. HISTORICAL MARKET REGIME STRESS BREAKDOWN")
        print("-" * 105)
        print(f" {'Regime Window':<28} | {'Trades':>6} | {'Win %':>7} | {'Profit Factor':>13} | {'Net P&L (₹)':>12} | {'Return %':>9} | {'Max DD %':>9} | {'Taleb Safety':<12}")
        print("-" * 105)
        for r in strat_info["regime_stress_testing"]:
            print(
                f" {r['regime_id']:<28} | {r['total_trades']:>6d} | "
                f"{r['win_rate_pct']:>6.1f}% | {r['profit_factor']:>13.2f} | "
                f"₹{r['net_pnl_inr']:>11.2f} | {r['net_return_pct']:>8.2f}% | "
                f"{r['max_drawdown_pct']:>8.2f}% | {r['taleb_compliance']:<12}"
            )

        # 2. Slippage & Friction Sensitivity Matrix
        print("\n ⚡ 2. SLIPPAGE & FRICTION SENSITIVITY MATRIX")
        print("-" * 105)
        print(f" {'Slippage Model':<35} | {'Trades':>6} | {'Win %':>7} | {'Net P&L (₹)':>12} | {'Max DD %':>9} | {'Total Friction':>14} | {'Slippage Drag':>13}")
        print("-" * 105)
        for s in strat_info["slippage_friction_sensitivity"]:
            print(
                f" {s['model_description']:<35} | {s['total_trades']:>6d} | "
                f"{s['win_rate_pct']:>6.1f}% | ₹{s['net_pnl_inr']:>11.2f} | "
                f"{s['max_drawdown_pct']:>8.2f}% | ₹{s['total_friction_inr']:>13.2f} | "
                f"₹{s['slippage_drag_inr']:>12.2f}"
            )
        print(f" ⚠️ Breakeven Slippage Tolerance: {strat_info['breakeven_slippage_tolerance_bps']}")

        # 3. Drawdown & Tail Risk Profiling
        dd = strat_info["drawdown_metrics"]
        print("\n 📉 3. DRAWDOWN & TAIL RISK PROFILE")
        print("-" * 105)
        print(f" • Max Peak-to-Trough Drawdown:   {dd['max_drawdown_pct']:.2f}%")
        print(f" • Max Consecutive Loss Streak:    {dd['max_consecutive_losses']} trades")
        print(f" • Avg Winning Trade Return:       {dd['avg_win_return_pct']:+.2f}%")
        print(f" • Avg Losing Trade Return:        {dd['avg_loss_return_pct']:+.2f}%")
        print(f" • Capital Recovery Factor:        {dd['recovery_factor']:.2f}")
        print(f" • Calmar Ratio:                   {dd['calmar_ratio']:.2f}")
        print(f" • Taleb Capital Antifragility:    {dd['taleb_certification']}")

    # Save to JSON
    out_dir = BASE_DIR / "data" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "strategy_stress_testing_sensitivity_report.json"
    with open(out_path, "w") as f:
        json.dump(full_report, f, indent=2)

    print("\n" + "=" * 105)
    print(f"✅ Stress testing complete. Structured audit report saved to: {out_path}")
    print("=" * 105 + "\n")


if __name__ == "__main__":
    main()
