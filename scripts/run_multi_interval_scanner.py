#!/usr/bin/env python3
"""
Algo Lab Deep Multi-Interval Scanner & Regime Evaluation Runner.
Scans across multiple timeframes (5m, 15m, 1h, daily) across NIFTY 100 / F&O universe.
Evaluates trend, volatility squeeze/expansion, breakout setups, and multi-timeframe confluence.
Saves structured output to data/multi_interval_scan_results.json.
"""

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from services.scanner.nifty100_universe import Nifty100UniverseManager
from services.scanner.universe_manager import AUTHORITATIVE_NIFTY_50_CONSTITUENTS
from services.scanner.deep_multi_interval_scanner import DeepMultiIntervalScanner

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MultiIntervalScannerRunner")


def main():
    parser = argparse.ArgumentParser(description="Algo Lab Deep Multi-Interval Scanner & Regime Evaluation")
    parser.add_argument(
        "--universe",
        choices=["nifty100", "fo", "nifty50"],
        default="nifty100",
        help="Universe to scan (default: nifty100)",
    )
    parser.add_argument(
        "--intervals",
        nargs="+",
        default=["5m", "15m", "1h", "1d"],
        help="Timeframe intervals to scan (default: 5m 15m 1h 1d)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of symbols scanned (useful for quick verification)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=5,
        help="Top setups to print per interval",
    )
    args = parser.parse_args()

    # Load Universe
    if args.universe == "nifty50":
        symbols = [item["symbol"] for item in AUTHORITATIVE_NIFTY_50_CONSTITUENTS]
        sector_map = {item["symbol"]: item["sector"] for item in AUTHORITATIVE_NIFTY_50_CONSTITUENTS}
    else:
        mgr = Nifty100UniverseManager()
        symbols = mgr.get_symbols()
        sector_map = mgr.get_sector_map()

    if args.limit:
        symbols = symbols[:args.limit]

    print("\n" + "=" * 100)
    print(" 🛰️  ALGO LAB INSTITUTIONAL MULTI-INTERVAL SCANNER & REGIME EVALUATION")
    print(f"    Universe: {args.universe.upper()} ({len(symbols)} constituents) | Intervals: {', '.join(args.intervals)}")
    print(f"    Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
    print("=" * 100)

    scanner = DeepMultiIntervalScanner(universe_symbols=symbols, sector_map=sector_map)
    scan_results = scanner.scan_universe(
        intervals=args.intervals,
        top_n=args.top_n,
    )

    # Display Market Regime Tear Sheet
    print("\n" + "-" * 100)
    print(" 🌐 AGGREGATE MARKET REGIME EVALUATION BY INTERVAL")
    print("-" * 100)
    print(f" {'Interval':<10} | {'Regime Classification':<26} | {'> EMA20 (%)':>12} | {'> SMA50 (%)':>12} | {'A/D Ratio':>10} | {'Avg ADX':>8} | {'Avg ATR%':>9} | {'In Squeeze':>11}")
    print("-" * 100)
    for interval, reg in scan_results["regimes_by_interval"].items():
        print(
            f" {interval:<10} | {reg['regime']:<26} | "
            f"{reg['breadth_pct_above_ema20']:>11.1f}% | "
            f"{reg['breadth_pct_above_sma50']:>11.1f}% | "
            f"{reg['advance_decline_ratio']:>10.2f} | "
            f"{reg['avg_adx']:>8.1f} | "
            f"{reg['avg_atr_pct']:>8.2f}% | "
            f"{reg['pct_in_squeeze']:>10.1f}%"
        )

    # Display Top Candidates Per Interval
    for interval, candidates in scan_results["top_setups_by_interval"].items():
        print("\n" + "-" * 100)
        print(f" 📈 [INTERVAL: {interval.upper()}] TOP BREAKOUT & MOMENTUM SETUPS (Showing {len(candidates)})")
        print("-" * 100)
        print(f" {'Symbol':<12} | {'Sector':<18} | {'Setup':<22} | {'LTP (₹)':>9} | {'RSI':>5} | {'RVOL':>5} | {'ADX':>5} | {'SL (₹)':>9} | {'TP (₹)':>9}")
        print("-" * 100)
        if not candidates:
            print("  No qualifying setups detected in this interval.")
        else:
            for c in candidates:
                print(
                    f" {c['symbol']:<12} | {c['sector']:<18} | {c['setup']:<22} | "
                    f"{c['close']:>9.2f} | {c['rsi_14']:>5.1f} | {c['rel_volume']:>5.2f} | "
                    f"{c['adx_14']:>5.1f} | {c['stop_loss']:>9.2f} | {c['take_profit']:>9.2f}"
                )

    # Display Multi-Timeframe Confluence
    confluences = scan_results["confluence_symbols"]
    print("\n" + "=" * 100)
    print(f" 🎯 MULTI-TIMEFRAME CONFLUENCE SIGNALS (Present in ≥ 2 intervals: {len(confluences)} detected)")
    print("=" * 100)
    if not confluences:
        print("  • No confluence detected across requested intervals.")
    else:
        for sym, setups in sorted(confluences.items(), key=lambda x: len(x[1]), reverse=True):
            print(f"  • {sym:<12} | Confluence ({len(setups)}x): {' | '.join(setups)}")

    # Persist JSON report
    out_path = BASE_DIR / "data" / "multi_interval_scan_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(scan_results, f, indent=2)

    print(f"\n✅ Structured scan report saved to: {out_path}")
    print("=" * 100 + "\n")


if __name__ == "__main__":
    main()
