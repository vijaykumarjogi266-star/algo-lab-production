#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PYTHON_BIN = BASE_DIR / ".venv" / "bin" / "python"
RUNNER_SCRIPT = BASE_DIR / "scripts" / "run_adaptive_market_survival_backtest.py"

universes = ["nifty50", "leaders"]
exit_mechanisms = [("Pure Convexity", False), ("Hybrid RSI Exit", True)]
positions = [2, 3, 5]

results_table = []

for u in universes:
    for exit_name, tech_exit in exit_mechanisms:
        for pos in positions:
            cmd = [
                str(PYTHON_BIN),
                str(RUNNER_SCRIPT),
                "--universe", u,
                "--max-positions", str(pos),
            ]
            if tech_exit:
                cmd.append("--enable-tech-exit")
            
            print(f"Running: universe={u}, exit={exit_name}, max_positions={pos}...")
            res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(BASE_DIR))
            if res.returncode != 0:
                print(f"Error in {cmd}: {res.stderr}")
                continue
            
            # Read output artifact
            artifact_path = BASE_DIR / "data" / "processed" / f"swing_trading_{u}_5year_backtest_20261001.json"
            with open(artifact_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            meta = data["backtest_results"]["metadata"]
            perf = data["backtest_results"]["performance_metrics"]
            fric = data["backtest_results"]["friction_breakdown"]
            cagr = data["cagr_pct"]
            
            results_table.append({
                "universe": u,
                "exit_mechanism": exit_name,
                "max_positions": pos,
                "net_profit_inr": meta["net_profit_inr"],
                "cagr_pct": cagr,
                "max_drawdown_pct": perf["max_drawdown_pct"],
                "win_rate_pct": perf["win_rate_pct"],
                "profit_factor": perf["profit_factor"],
                "calmar_ratio": perf["calmar_ratio"],
                "total_trades": perf["total_trades"],
                "winning_trades": perf["winning_trades"],
                "losing_trades": perf["losing_trades"],
                "total_friction_inr": fric["total_friction_inr"],
                "gross_pnl_inr": perf["gross_pnl_inr"],
            })

print("\n" + "=" * 120)
print(f"{'Universe':<10} | {'Exit Mechanism':<16} | {'Slots':<5} | {'Net Profit (₹)':>14} | {'CAGR (%)':>9} | {'Max DD (%)':>10} | {'Win Rate':>9} | {'Profit Factor':>13} | {'Calmar':>8} | {'Trades':>6} | {'Friction (₹)':>12}")
print("-" * 120)
for r in results_table:
    print(f"{r['universe']:<10} | {r['exit_mechanism']:<16} | {r['max_positions']:<5} | ₹{r['net_profit_inr']:>12,.2f} | {r['cagr_pct']:>8.2f}% | {r['max_drawdown_pct']:>9.2f}% | {r['win_rate_pct']:>8.2f}% | {r['profit_factor']:>13.2f} | {r['calmar_ratio']:>8.2f} | {r['total_trades']:>6} | ₹{r['total_friction_inr']:>10,.2f}")

# Save JSON results summary
summary_path = BASE_DIR / "data" / "processed" / "super_adaptive_variant_matrix_results.json"
with open(summary_path, "w", encoding="utf-8") as f:
    json.dump(results_table, f, indent=2)

print(f"\nSaved matrix results to {summary_path}")
