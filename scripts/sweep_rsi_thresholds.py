#!/usr/bin/env python3
"""
Algo Lab — Super-Adaptive RSI Exit Threshold Sensitivity Analysis (2021–2026)
Sweeps RSI exit thresholds: 65, 70, 75, 80, 85, and None (Pure Convexity).
"""

import sys
import json
from pathlib import Path
from decimal import Decimal
import polars as pl

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from services.backtest_engine.adaptive_market_engine import (
    AdaptiveMarketSurvivalBacktester,
    ProductType,
)
from services.scanner.universe_manager import Nifty50UniverseManager


class CustomRSIExitEngine(AdaptiveMarketSurvivalBacktester):
    def __init__(self, rsi_threshold: float = None, **kwargs):
        super().__init__(**kwargs)
        self.rsi_threshold = rsi_threshold

    def _evaluate_position_exits(self, positions, current_time, dict_datasets, closed_positions, total_friction):
        # Apply custom RSI threshold logic
        if self.rsi_threshold is not None:
            for sym, pos in list(positions.items()):
                bar = dict_datasets.get(sym, {}).get(current_time)
                if bar:
                    curr_price = bar["close"]
                    rsi_14 = bar.get("rsi_14")
                    # If position has not already been marked for exit
                    if rsi_14 is not None and rsi_14 >= self.rsi_threshold:
                        # Force exit
                        qty = pos["quantity"]
                        exit_price = curr_price
                        from services.backtest_engine.statutory_cost_model import IndianStatutoryCostModel, OrderLeg
                        exit_friction = IndianStatutoryCostModel.calculate_order_friction(
                            leg=OrderLeg.SELL,
                            price=Decimal(str(exit_price)),
                            quantity=qty,
                            product=self.product,
                            slippage_bps=Decimal(str(self.slippage_bps)),
                            dp_charge_flat=self.dp_charge_flat,
                        )
                        gross_pnl = (exit_price - pos["entry_price"]) * qty
                        entry_fric_val = float(pos["entry_friction"]["total_friction"]) if isinstance(pos["entry_friction"], dict) else float(pos["entry_friction"].all_in_total_friction)
                        net_pnl = gross_pnl - entry_fric_val - float(exit_friction.all_in_total_friction)
                        
                        self.cash += (exit_price * qty) - float(exit_friction.all_in_total_friction)
                        total_friction[0] += exit_friction.all_in_total_friction
                        
                        closed_positions.append({
                            "symbol": sym,
                            "entry_time": pos["entry_time"],
                            "exit_time": current_time,
                            "entry_price": pos["entry_price"],
                            "exit_price": exit_price,
                            "quantity": qty,
                            "gross_pnl": gross_pnl,
                            "net_pnl": net_pnl,
                            "exit_reason": f"RSI_{self.rsi_threshold}_EXIT",
                            "friction_total": entry_fric_val + float(exit_friction.all_in_total_friction),
                        })
                        del positions[sym]
        
        # Continue with standard trailing stops and Donchian exits
        return super()._evaluate_position_exits(positions, current_time, dict_datasets, closed_positions, total_friction)


def main():
    cache_dir = BASE_DIR / "data" / "cache"
    universe_mgr = Nifty50UniverseManager()
    symbols = universe_mgr.get_symbols()
    sector_map = universe_mgr.get_sector_map()

    datasets = {}
    for sym in symbols:
        p = cache_dir / f"{sym}_NS_5y_1d.parquet"
        if p.exists():
            datasets[sym] = pl.read_parquet(p)

    print("=" * 105)
    print(" 🔬 SUPER-ADAPTIVE: RSI OVERBOUGHT EXIT THRESHOLD SENSITIVITY SWEEP (2021–2026)")
    print("=" * 105)

    thresholds = [None, 85.0, 80.0, 75.0, 70.0, 65.0]
    results = []

    for thresh in thresholds:
        label = "None (Pure Convexity)" if thresh is None else f"RSI >= {thresh:.0f}"
        engine = CustomRSIExitEngine(
            rsi_threshold=thresh,
            initial_capital=100000.0,
            max_capital_per_position=30000.0,
            max_concurrent_positions=3,
            risk_per_trade_pct=0.010,
            product=ProductType.DELIVERY,
            stop_loss_atr_multiplier=2.5,
            take_profit_risk_multiplier=3.5,
            sector_map=sector_map,
            strategy="STRATEGY_SUPER_ADAPTIVE",
            enable_technical_exit=False,
        )
        res = engine.run_backtest(datasets)
        meta = res["metadata"]
        perf = res["performance_metrics"]
        fric = res["friction_breakdown"]
        cagr = ((meta["final_equity_inr"] / 100000.0) ** (1.0 / 5.0) - 1.0) * 100.0

        results.append({
            "label": label,
            "net_profit": meta["net_profit_inr"],
            "cagr": cagr,
            "max_dd": perf["max_drawdown_pct"],
            "win_rate": perf["win_rate_pct"],
            "profit_factor": perf["profit_factor"],
            "total_trades": perf["total_trades"],
            "total_friction": fric["total_friction_inr"],
        })
        print(f"Tested: {label:<24} | Net: ₹{meta['net_profit_inr']:>10,.2f} | CAGR: {cagr:>5.2f}% | Max DD: {perf['max_drawdown_pct']:>5.2f}% | Trades: {perf['total_trades']:>4} | Friction: ₹{fric['total_friction_inr']:>8,.2f}")

    print("\n" + "=" * 105)
    print(" 📋 SUMMARY TABLE: RSI EXIT THRESHOLD VS PURE CONVEXITY")
    print("=" * 105)
    print(f"{'RSI Exit Setting':<26} | {'Net PnL (₹)':>12} | {'CAGR (%)':>8} | {'Max DD (%)':>10} | {'Win Rate':>8} | {'PF':>5} | {'Trades':>6} | {'Friction':>9}")
    print("-" * 100)
    for r in results:
        print(f"{r['label']:<26} | ₹{r['net_profit']:>11,.2f} | {r['cagr']:>7.2f}% | {r['max_dd']:>9.2f}% | {r['win_rate']:>7.1f}% | {r['profit_factor']:>5.2f} | {r['total_trades']:>6} | ₹{r['total_friction']:>8,.2f}")

    out_file = BASE_DIR / "data" / "processed" / "rsi_exit_threshold_sweep_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved results to: {out_file}")


if __name__ == "__main__":
    main()
