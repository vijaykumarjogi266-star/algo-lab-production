"""
Algo Lab Backtest Stress Testing & Drawdown Sensitivity Engine.
Evaluates active strategies across historical market regimes, variable friction/slippage models,
and drawdown sensitivity matrices to guarantee capital survival and Taleb antifragility.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import polars as pl

from services.backtest_engine.adaptive_market_engine import (
    AdaptiveMarketSurvivalBacktester,
    ProductType,
)
from services.scanner.nifty100_universe import Nifty100UniverseManager

logger = logging.getLogger("StressTestingEngine")

ACTIVE_STRATEGIES = [
    ("STRATEGY_A", "CFI: Golden Cross (SMA 50/200)"),
    ("STRATEGY_B", "CFI: 5-8-13 Fibonacci EMA"),
    ("STRATEGY_C", "CFI: Simple ADX Trend"),
    ("STRATEGY_D", "Prabhu: 8/20 EMA Pullback"),
    ("STRATEGY_E", "Prabhu: High-Volume PDH Follow-Through"),
    ("STRATEGY_SUPER_ADAPTIVE", "AlgoLab: Super-Adaptive Trend & Breakout"),
]

REGIME_WINDOWS = [
    ("2021_BULL_RUN", "2021-01-01", "2021-12-31", "Strong Trend Expansion"),
    ("2022_BEAR_CORRECTION", "2022-01-01", "2022-12-31", "High-Inflation Tech/Growth Pullback"),
    ("2023_2024_BULL_EXPANSION", "2023-01-01", "2024-12-31", "Broad Mid/Small & Large-Cap Rally"),
    ("2025_2026_ROTATIONAL_CHOP", "2025-01-01", "2026-10-12", "Range-bound & Sectoral Rotation"),
]

SLIPPAGE_GRID = [
    (0.0000, "0 bps (Pure Statutory Frictions)"),
    (0.0005, "5 bps (Baseline Liquid Execution)"),
    (0.0010, "10 bps (Elevated Slippage / Volatility)"),
    (0.0020, "20 bps (High-Beta Liquidity Stress)"),
    (0.0050, "50 bps (Black Swan / Gap Risk Stress)"),
]


class StressTestingEngine:
    """
    Executes multi-regime stress testing, drawdown sensitivity analysis,
    and friction sensitivity matrices for Algolab active strategies.
    """

    def __init__(
        self,
        datasets: Dict[str, pl.DataFrame],
        sector_map: Optional[Dict[str, str]] = None,
        initial_capital: float = 100000.0,
    ):
        self.datasets = datasets
        self.sector_map = sector_map or Nifty100UniverseManager().get_sector_map()
        self.initial_capital = initial_capital

    def filter_datasets_by_date(
        self,
        start_date: str,
        end_date: str,
    ) -> Dict[str, pl.DataFrame]:
        """Filters all constituent parquets to a specified historical window."""
        filtered = {}
        t_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        t_end = datetime.strptime(end_date, "%Y-%m-%d").date()

        for sym, df in self.datasets.items():
            date_col = "date" if "date" in df.columns else "Date"
            # Ensure date filtering handles both Date and Datetime types
            df_filtered = df.filter(
                (pl.col(date_col).dt.date() >= t_start) & (pl.col(date_col).dt.date() <= t_end)
            )
            if df_filtered.height >= 20:
                filtered[sym] = df_filtered

        return filtered

    def run_strategy_backtest(
        self,
        strategy_code: str,
        datasets: Dict[str, pl.DataFrame],
        slippage_override_bps: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Runs single backtest instance with optional custom slippage in bps."""
        slip_bps = slippage_override_bps if slippage_override_bps is not None else 5.0

        backtester = AdaptiveMarketSurvivalBacktester(
            initial_capital=self.initial_capital,
            max_capital_per_position=45000.0,
            max_concurrent_positions=2,
            risk_per_trade_pct=0.010,
            slippage_bps=slip_bps,
            product=ProductType.DELIVERY,
            stop_loss_atr_multiplier=2.5,
            take_profit_risk_multiplier=3.5,
            sector_map=self.sector_map,
            strategy=strategy_code,
        )

        return backtester.run_backtest(datasets)

    def evaluate_regime_stress_testing(
        self,
        strategy_code: str,
    ) -> List[Dict[str, Any]]:
        """Evaluates a strategy across all historical regime windows."""
        results = []
        for reg_id, start_d, end_d, desc in REGIME_WINDOWS:
            reg_datasets = self.filter_datasets_by_date(start_d, end_d)
            if not reg_datasets:
                continue

            bt_res = self.run_strategy_backtest(strategy_code, reg_datasets)
            meta = bt_res["metadata"]
            perf = bt_res["performance_metrics"]

            results.append({
                "regime_id": reg_id,
                "description": desc,
                "start_date": start_d,
                "end_date": end_d,
                "total_trades": perf["total_trades"],
                "win_rate_pct": perf["win_rate_pct"],
                "profit_factor": perf["profit_factor"],
                "net_pnl_inr": perf["net_pnl_inr"],
                "net_return_pct": meta["net_return_pct"],
                "max_drawdown_pct": perf["max_drawdown_pct"],
                "taleb_compliance": perf["taleb_compliance"],
            })
        return results

    def evaluate_slippage_sensitivity(
        self,
        strategy_code: str,
    ) -> List[Dict[str, Any]]:
        """Evaluates strategy sensitivity across variable slippage/friction models."""
        sensitivity_results = []
        baseline_net_pnl = None

        for slip_rate, label in SLIPPAGE_GRID:
            slip_bps = float(slip_rate * 10000)
            bt_res = self.run_strategy_backtest(strategy_code, self.datasets, slippage_override_bps=slip_bps)
            meta = bt_res["metadata"]
            perf = bt_res["performance_metrics"]
            fric = bt_res["friction_breakdown"]

            if baseline_net_pnl is None:
                baseline_net_pnl = perf["net_pnl_inr"]

            slip_drag_inr = round(baseline_net_pnl - perf["net_pnl_inr"], 2)

            sensitivity_results.append({
                "slippage_rate": slip_rate,
                "slippage_bps": int(slip_rate * 10000),
                "model_description": label,
                "total_trades": perf["total_trades"],
                "win_rate_pct": perf["win_rate_pct"],
                "profit_factor": perf["profit_factor"],
                "net_pnl_inr": perf["net_pnl_inr"],
                "net_return_pct": meta["net_return_pct"],
                "max_drawdown_pct": perf["max_drawdown_pct"],
                "total_friction_inr": fric["total_friction_inr"],
                "slippage_inr": fric["slippage_inr"],
                "slippage_drag_inr": slip_drag_inr,
                "is_profitable": perf["net_pnl_inr"] > 0,
            })

        return sensitivity_results

    def compute_drawdown_sensitivity_curve(
        self,
        strategy_code: str,
    ) -> Dict[str, Any]:
        """Analyzes drawdown distribution, consecutive loss streaks, and recovery factor."""
        bt_res = self.run_strategy_backtest(strategy_code, self.datasets)
        trades = bt_res.get("trades", [])

        if not trades:
            return {
                "max_drawdown_pct": 0.0,
                "max_consecutive_losses": 0,
                "avg_loss_pct": 0.0,
                "avg_win_pct": 0.0,
                "recovery_factor": 0.0,
                "calmar_ratio": 0.0,
            }

        # Analyze streaks
        max_consec_losses = 0
        current_loss_streak = 0
        loss_returns = []
        win_returns = []

        for t in trades:
            if t["net_pnl"] <= 0:
                current_loss_streak += 1
                max_consec_losses = max(max_consec_losses, current_loss_streak)
                loss_returns.append(t["return_pct"])
            else:
                current_loss_streak = 0
                win_returns.append(t["return_pct"])

        perf = bt_res["performance_metrics"]
        mdd = perf["max_drawdown_pct"]
        net_ret = bt_res["metadata"]["net_return_pct"]
        recovery_factor = round(perf["net_pnl_inr"] / (mdd * self.initial_capital * 0.01 + 1e-9), 2) if mdd > 0 else 99.0

        return {
            "max_drawdown_pct": mdd,
            "max_consecutive_losses": max_consec_losses,
            "avg_loss_return_pct": round(float(np.mean(loss_returns)), 2) if loss_returns else 0.0,
            "avg_win_return_pct": round(float(np.mean(win_returns)), 2) if win_returns else 0.0,
            "recovery_factor": recovery_factor,
            "calmar_ratio": perf["calmar_ratio"],
            "taleb_certification": "PASSED" if mdd <= 12.0 and perf["rejected_orders_solvency"] == 0 else "CAUTION",
        }

    def execute_comprehensive_stress_test(
        self,
        strategies: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Executes stress test across active strategies (or a specified subset)."""
        if strategies:
            strat_list = [s for s in ACTIVE_STRATEGIES if s[0] in strategies]
        else:
            strat_list = ACTIVE_STRATEGIES

        logger.info(f"Starting comprehensive stress test for {len(strat_list)} strategies...")

        report = {
            "stress_test_timestamp": datetime.now(timezone.utc).isoformat(),
            "initial_capital_inr": self.initial_capital,
            "datasets_count": len(self.datasets),
            "strategies": {},
        }

        for strat_code, strat_name in strat_list:
            logger.info(f"Stress testing {strat_name} ({strat_code})...")
            regime_results = self.evaluate_regime_stress_testing(strat_code)
            slippage_results = self.evaluate_slippage_sensitivity(strat_code)
            dd_metrics = self.compute_drawdown_sensitivity_curve(strat_code)

            # Determine breakeven slippage tolerance
            breakeven_bps = None
            for s in slippage_results:
                if not s["is_profitable"]:
                    breakeven_bps = s["slippage_bps"]
                    break

            report["strategies"][strat_code] = {
                "strategy_name": strat_name,
                "regime_stress_testing": regime_results,
                "slippage_friction_sensitivity": slippage_results,
                "drawdown_metrics": dd_metrics,
                "breakeven_slippage_tolerance_bps": breakeven_bps or ">50 bps",
            }

        return report
