"""
OMS Project - Parameter Optimizer ("Golden Parameter Finder")
Grid searches strategy parameters over historical tick datasets
to find maximum profit, minimal drawdown, and zero-variance execution.
"""

from typing import List, Dict, Any, Optional
from oms_project.schemas import NormalizedTick
from oms_project.gateway import BrokerGateway
from oms_project.paper_exchange import PaperExchange
from oms_project.central_data_feed import MarketDataService
from oms_project.replay_service import HistoricalReplayEngine
from oms_project.strategies.mean_reversion.mean_reversion_strat import MeanReversionStrategy
from oms_project.strategies.mean_reversion.strategy_sdk import StrategySDK
from oms_project.scripts.reconciliation import AssetReconciler


class StrategyOptimizer:
    """
    Grid Search Optimizer for Quantitative Trading Strategies.
    Performs clean-slate reset before each simulation run.
    """

    def __init__(
        self,
        ticks: List[Dict[str, Any]],
        strategy_id: str = "STRAT_MEAN_REV_001",
        symbol: str = "RELIANCE",
        initial_cash: float = 100000.0,
        slippage_bps: float = 0.0,
    ):
        self.ticks = ticks
        self.strategy_id = strategy_id
        self.symbol = symbol
        self.initial_cash = initial_cash
        self.slippage_bps = slippage_bps

    def run_single_backtest(
        self,
        window_size: int,
        std_dev_threshold: float,
        order_qty: float = 10.0,
    ) -> Dict[str, Any]:
        """Runs a single deterministic simulation for given parameters."""
        paper_ex = PaperExchange(initial_cash=self.initial_cash)
        gateway = BrokerGateway(
            paper_exchange=paper_ex,
            simulation_mode=True,
            slippage_bps=self.slippage_bps,
        )
        gateway.strategy_balances[self.strategy_id] = self.initial_cash
        gateway.reset_simulation(initial_cash=self.initial_cash)
        gateway.simulation_mode = True
        gateway.slippage_bps = self.slippage_bps

        feed = MarketDataService()
        replay = HistoricalReplayEngine(market_data_service=feed, playback_speed=0.0)
        replay.load_ticks(self.ticks)

        sdk = StrategySDK(strategy_id=self.strategy_id)
        bot = MeanReversionStrategy(
            strategy_id=self.strategy_id,
            symbol=self.symbol,
            window_size=window_size,
            std_dev_threshold=std_dev_threshold,
            order_qty=order_qty,
            sdk=sdk,
        )

        equity_curve: List[float] = [self.initial_cash]
        peak_equity: float = self.initial_cash
        max_drawdown_pct: float = 0.0
        filled_orders: List[Dict[str, Any]] = []

        def on_tick_step(tick: NormalizedTick):
            gateway.set_market_price(tick.symbol, tick.price, tick.timestamp)
            intent = bot.on_tick(tick.price, timestamp=tick.timestamp)
            if intent:
                res = gateway.process_order_intent(intent)
                if res.status.value == "FILLED":
                    filled_orders.append(res.model_dump())

            # Track equity & drawdown
            curr_assets = gateway.get_broker_ledger_total_assets(self.strategy_id)
            equity_curve.append(curr_assets)
            nonlocal peak_equity, max_drawdown_pct
            if curr_assets > peak_equity:
                peak_equity = curr_assets
            dd = (peak_equity - curr_assets) / peak_equity * 100.0
            if dd > max_drawdown_pct:
                max_drawdown_pct = dd

        replay.replay_ticks_sync(on_tick_step)

        reconciler = AssetReconciler(gateway, gateway.paper_exchange)
        recon_report = reconciler.run_reconciliation(self.strategy_id)

        final_equity = gateway.get_broker_ledger_total_assets(self.strategy_id)
        net_pnl = final_equity - self.initial_cash
        net_pnl_pct = (net_pnl / self.initial_cash) * 100.0

        return {
            "window_size": window_size,
            "std_dev_threshold": std_dev_threshold,
            "initial_cash": round(self.initial_cash, 8),
            "final_equity": round(final_equity, 8),
            "net_pnl": round(net_pnl, 8),
            "net_pnl_pct": round(net_pnl_pct, 4),
            "max_drawdown_pct": round(max_drawdown_pct, 4),
            "total_trades": len(filled_orders),
            "reconciliation_variance": round(recon_report["variance"], 8),
            "reconciliation_status": recon_report["status"],
        }

    def grid_search(
        self,
        window_range: List[int],
        std_dev_range: List[float],
        order_qty: float = 10.0,
    ) -> Dict[str, Any]:
        """Runs parameter sweep grid search and identifies optimal parameters."""
        all_results = []
        best_result: Optional[Dict[str, Any]] = None

        for w in window_range:
            for s in std_dev_range:
                res = self.run_single_backtest(
                    window_size=w,
                    std_dev_threshold=s,
                    order_qty=order_qty,
                )
                all_results.append(res)
                if best_result is None or res["net_pnl"] > best_result["net_pnl"]:
                    best_result = res

        heatmap_str = self.format_heatmap(all_results, window_range, std_dev_range)

        return {
            "best_parameters": best_result,
            "all_results": all_results,
            "heatmap": heatmap_str,
        }

    def format_heatmap(
        self,
        results: List[Dict[str, Any]],
        window_range: List[int],
        std_dev_range: List[float],
    ) -> str:
        """Formats ASCII Performance Heatmap table for P&L across parameter matrix."""
        lines = []
        lines.append("\n============================================================")
        lines.append("           QUANT-OS PARAMETER PERFORMANCE HEATMAP           ")
        lines.append("                 Net P&L (₹) Matrix Output                  ")
        lines.append("============================================================")
        header = f"Window \\ StdDev | " + " | ".join(f"σ = {s:4.1f}" for s in std_dev_range)
        lines.append(header)
        lines.append("-" * len(header))

        res_lookup = {(r["window_size"], r["std_dev_threshold"]): r["net_pnl"] for r in results}

        for w in window_range:
            row_str = f"  Window = {w:2d}   | "
            vals = []
            for s in std_dev_range:
                pnl = res_lookup.get((w, s), 0.0)
                vals.append(f"₹{pnl:9.2f}")
            row_str += " | ".join(vals)
            lines.append(row_str)

        lines.append("============================================================")
        return "\n".join(lines)
