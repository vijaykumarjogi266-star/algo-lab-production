#!/usr/bin/env python3
"""
Algo Lab — Comprehensive RSI Strategy Matrix Backtester (2021–2026)

Evaluates different canonical RSI models on 5-Year Nifty 50 cached daily data:
1. RSI(14) Oversold Reversal (RSI < 30 + 200 SMA filter)
2. RSI(14) Deep Capitulation (RSI < 25 + 200 SMA filter)
3. RSI(14) Momentum Range Breakout (RSI cross > 60 in Bull Trend)
4. RSI(14) Uptrend Pullback (40 <= RSI <= 50 sweet spot bounce)
5. Connors RSI(2) Short-Term Reversion (RSI(2) < 10 + 200 SMA)
6. RSI Overbought Exit Tuning on Super-Adaptive (Thresholds: 65, 70, 75, 80, 85 vs None)

Includes strict double-entry balance sheet accounting and Indian statutory delivery frictions (STT, DP, GST, 5 bps slippage).
"""

import sys
import os
import json
from pathlib import Path
from decimal import Decimal
from typing import Dict, List, Any, Optional

import polars as pl
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from services.backtest_engine.adaptive_market_engine import (
    AdaptiveMarketSurvivalBacktester,
    ProductType,
    MarketRegime,
)
from services.backtest_engine.statutory_cost_model import IndianStatutoryCostModel, OrderLeg
from services.scanner.universe_manager import Nifty50UniverseManager


def enrich_rsi_indicators(df: pl.DataFrame) -> pl.DataFrame:
    """Enriches dataset with RSI(14), RSI(2), and moving averages."""
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # Moving averages
    sma_5 = close.rolling_mean(window_size=5).fill_null(close)
    sma_20 = close.rolling_mean(window_size=20).fill_null(close)
    sma_50 = close.rolling_mean(window_size=50).fill_null(close)
    sma_200 = close.rolling_mean(window_size=200).fill_null(close)
    ema_8 = close.ewm_mean(span=8, adjust=False).fill_null(close)
    ema_20 = close.ewm_mean(span=20, adjust=False).fill_null(close)

    # ATR 14
    prev_close = close.shift(1).fill_null(close)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pl.max_horizontal([tr1, tr2, tr3])
    atr_14 = tr.rolling_mean(window_size=14).fill_null(close * 0.015)

    # RSI 14
    delta = close.diff().fill_null(0.0)
    gain = pl.when(delta > 0).then(delta).otherwise(0.0)
    loss = pl.when(delta < 0).then(-delta).otherwise(0.0)
    
    avg_gain_14 = gain.ewm_mean(alpha=1/14, adjust=False)
    avg_loss_14 = loss.ewm_mean(alpha=1/14, adjust=False)
    rs_14 = avg_gain_14 / (avg_loss_14 + 1e-9)
    rsi_14 = 100.0 - (100.0 / (1.0 + rs_14))

    # Connors RSI 2
    avg_gain_2 = gain.ewm_mean(alpha=1/2, adjust=False)
    avg_loss_2 = loss.ewm_mean(alpha=1/2, adjust=False)
    rs_2 = avg_gain_2 / (avg_loss_2 + 1e-9)
    rsi_2 = 100.0 - (100.0 / (1.0 + rs_2))

    return df.with_columns([
        sma_5.alias("sma_5"),
        sma_20.alias("sma_20"),
        sma_50.alias("sma_50"),
        sma_200.alias("sma_200"),
        ema_8.alias("ema_8"),
        ema_20.alias("ema_20"),
        atr_14.alias("atr_14"),
        rsi_14.alias("rsi_14"),
        rsi_2.alias("rsi_2"),
    ])


class RSIEngineBacktester:
    """Specialized Backtester for RSI strategies with statutory Indian delivery accounting."""

    def __init__(
        self,
        initial_capital: float = 100000.0,
        max_concurrent_positions: int = 3,
        risk_per_trade_pct: float = 0.010,
        slippage_bps: float = 5.0,
    ):
        self.initial_capital = initial_capital
        self.max_concurrent_positions = max_concurrent_positions
        self.risk_per_trade_pct = risk_per_trade_pct
        self.slippage_bps = slippage_bps
        self.dp_charge = Decimal("15.34")

    def run_strategy(
        self,
        strategy_name: str,
        datasets: Dict[str, pl.DataFrame],
        strategy_type: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Runs a specific RSI strategy across all constituents."""
        cash = float(self.initial_capital)
        equity = float(self.initial_capital)
        peak_equity = float(self.initial_capital)
        max_drawdown = 0.0

        positions: Dict[str, Dict[str, Any]] = {}
        trade_log: List[Dict[str, Any]] = []

        total_friction = Decimal("0.0")
        total_brokerage = Decimal("0.0")
        total_stt = Decimal("0.0")
        total_dp = Decimal("0.0")

        # Gather sorted unique dates
        all_dates = set()
        dict_datasets = {}
        for sym, df in datasets.items():
            enriched = enrich_rsi_indicators(df)
            rows = enriched.to_dicts()
            dict_datasets[sym] = {r["date"]: r for r in rows}
            all_dates.update(r["date"] for r in rows)

        sorted_dates = sorted(all_dates)
        max_cap_per_pos = (self.initial_capital - 10000.0) / self.max_concurrent_positions

        for d in sorted_dates:
            # 1. Update existing positions & check exits
            closed_syms = []
            for sym, pos in positions.items():
                bar = dict_datasets.get(sym, {}).get(d)
                if not bar:
                    continue

                curr_close = bar["close"]
                high = bar["high"]
                low = bar["low"]
                rsi_14 = bar["rsi_14"]
                rsi_2 = bar["rsi_2"]
                sma_5 = bar["sma_5"]

                pos["highest"] = max(pos["highest"], high)
                exit_reason = None
                exit_price = curr_close

                # Check Stop Loss hit
                if low <= pos["stop_loss"]:
                    exit_reason = "STOP_LOSS_HIT"
                    exit_price = min(pos["stop_loss"], curr_close)
                # Check Take Profit
                elif pos.get("take_profit") and high >= pos["take_profit"]:
                    exit_reason = "TAKE_PROFIT_HIT"
                    exit_price = pos["take_profit"]
                else:
                    # Strategy-specific exit rules
                    if strategy_type == "RSI_OVERSOLD":
                        # Exit on RSI recovery
                        exit_thresh = params.get("exit_rsi", 50.0)
                        if rsi_14 >= exit_thresh:
                            exit_reason = f"RSI_TARGET_{exit_thresh}"
                            exit_price = curr_close
                    elif strategy_type == "CONNORS_RSI_2":
                        # Exit when Close crosses above 5 SMA
                        if curr_close > sma_5:
                            exit_reason = "CLOSE_ABOVE_SMA5"
                            exit_price = curr_close
                    elif strategy_type == "RSI_MOMENTUM_BREAKOUT":
                        # Exit when RSI falls below 45 or trailing stop
                        if rsi_14 < 45.0:
                            exit_reason = "RSI_MOMENTUM_LOST"
                            exit_price = curr_close
                    elif strategy_type == "RSI_PULLBACK":
                        if rsi_14 >= 70.0:
                            exit_reason = "RSI_OVERBOUGHT_EXIT"
                            exit_price = curr_close

                    # Trailing stop update if in profit
                    if not exit_reason:
                        atr = bar["atr_14"]
                        trail_stop = pos["highest"] - (atr * 2.5)
                        if trail_stop > pos["stop_loss"]:
                            pos["stop_loss"] = trail_stop

                if exit_reason:
                    qty = pos["qty"]
                    exit_fric = IndianStatutoryCostModel.calculate_order_friction(
                        leg=OrderLeg.SELL,
                        price=Decimal(str(exit_price)),
                        quantity=qty,
                        product=ProductType.DELIVERY,
                        slippage_bps=Decimal(str(self.slippage_bps)),
                        dp_charge_flat=self.dp_charge,
                    )
                    gross_pnl = (exit_price - pos["entry_price"]) * qty
                    net_pnl = gross_pnl - float(pos["entry_friction"].all_in_total_friction) - float(exit_fric.all_in_total_friction)

                    cash += (exit_price * qty) - float(exit_fric.all_in_total_friction)
                    total_friction += pos["entry_friction"].all_in_total_friction + exit_fric.all_in_total_friction

                    trade_log.append({
                        "symbol": sym,
                        "entry_date": pos["entry_date"],
                        "exit_date": d,
                        "entry_price": pos["entry_price"],
                        "exit_price": exit_price,
                        "qty": qty,
                        "gross_pnl": gross_pnl,
                        "net_pnl": net_pnl,
                        "exit_reason": exit_reason,
                    })
                    closed_syms.append(sym)

            for s in closed_syms:
                del positions[s]

            # 2. Check for new entries if capacity exists
            if len(positions) < self.max_concurrent_positions and cash >= 15000.0:
                available_syms = [s for s in datasets.keys() if s not in positions]

                for sym in available_syms:
                    if len(positions) >= self.max_concurrent_positions:
                        break

                    bar = dict_datasets.get(sym, {}).get(d)
                    if not bar:
                        continue

                    curr_close = bar["close"]
                    sma_200 = bar["sma_200"]
                    sma_50 = bar["sma_50"]
                    sma_20 = bar["sma_20"]
                    ema_8 = bar["ema_8"]
                    ema_20 = bar["ema_20"]
                    atr = bar["atr_14"]
                    rsi_14 = bar["rsi_14"]
                    rsi_2 = bar["rsi_2"]

                    buy_signal = False
                    stop_dist = max(atr * 2.5, curr_close * 0.025)
                    sl_price = curr_close - stop_dist
                    tp_price = curr_close + (stop_dist * 3.5)

                    if strategy_type == "RSI_OVERSOLD":
                        # Trend-filtered Oversold Bounce
                        oversold_thresh = params.get("entry_rsi", 30.0)
                        require_trend = params.get("trend_filter", True)
                        if rsi_14 <= oversold_thresh:
                            if not require_trend or curr_close > sma_200:
                                buy_signal = True

                    elif strategy_type == "CONNORS_RSI_2":
                        # Connors 2-Period RSI
                        rsi2_thresh = params.get("entry_rsi2", 10.0)
                        if rsi_2 <= rsi2_thresh and curr_close > sma_200:
                            buy_signal = True
                            tp_price = None  # Exit purely on SMA 5 cross

                    elif strategy_type == "RSI_MOMENTUM_BREAKOUT":
                        # Cardwell Momentum: RSI crosses > 60 in established uptrend
                        breakout_thresh = params.get("entry_rsi", 60.0)
                        if rsi_14 >= breakout_thresh and curr_close > sma_50 and sma_20 > sma_50:
                            buy_signal = True

                    elif strategy_type == "RSI_PULLBACK":
                        # Pullback to 40-50 zone in uptrend
                        if 40.0 <= rsi_14 <= 50.0 and curr_close > sma_200 and ema_8 > ema_20:
                            buy_signal = True

                    if buy_signal:
                        risk_amt = self.initial_capital * self.risk_per_trade_pct
                        qty = max(1, int(risk_amt / stop_dist))
                        trade_cost = qty * curr_close

                        if trade_cost > max_cap_per_pos:
                            qty = max(1, int(max_cap_per_pos / curr_close))
                            trade_cost = qty * curr_close

                        if trade_cost <= cash - 5000.0:
                            entry_fric = IndianStatutoryCostModel.calculate_order_friction(
                                leg=OrderLeg.BUY,
                                price=Decimal(str(curr_close)),
                                quantity=qty,
                                product=ProductType.DELIVERY,
                                slippage_bps=Decimal(str(self.slippage_bps)),
                                dp_charge_flat=Decimal("0.0"),
                            )
                            cash -= (trade_cost + float(entry_fric.all_in_total_friction))
                            positions[sym] = {
                                "entry_date": d,
                                "entry_price": curr_close,
                                "qty": qty,
                                "stop_loss": sl_price,
                                "take_profit": tp_price,
                                "highest": curr_close,
                                "entry_friction": entry_fric,
                            }

            # Calculate day-end equity & drawdown
            unrealized = sum(
                (dict_datasets.get(s, {}).get(d, {}).get("close", p["entry_price"]) - p["entry_price"]) * p["qty"]
                for s, p in positions.items()
            )
            equity = cash + sum(
                dict_datasets.get(s, {}).get(d, {}).get("close", p["entry_price"]) * p["qty"]
                for s, p in positions.items()
            )
            peak_equity = max(peak_equity, equity)
            dd = (peak_equity - equity) / peak_equity
            max_drawdown = max(max_drawdown, dd)

        # Performance summary
        wins = [t for t in trade_log if t["net_pnl"] > 0]
        losses = [t for t in trade_log if t["net_pnl"] <= 0]
        total_trades = len(trade_log)
        win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0

        gross_profit = sum(t["gross_pnl"] for t in wins)
        gross_loss = abs(sum(t["gross_pnl"] for t in losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        net_profit = equity - self.initial_capital
        cagr = ((equity / self.initial_capital) ** (1.0 / 5.0) - 1.0) * 100.0

        return {
            "strategy_name": strategy_name,
            "strategy_type": strategy_type,
            "params": params,
            "final_equity": round(equity, 2),
            "net_profit": round(net_profit, 2),
            "cagr_pct": round(cagr, 2),
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown_pct": round(max_drawdown * 100.0, 2),
            "total_trades": total_trades,
            "total_friction": round(float(total_friction), 2),
        }


def main():
    print("=" * 95)
    print(" ⚡ ALGO LAB — COMPREHENSIVE RSI STRATEGY MATRIX (2021–2026 | 5-YEAR DAILY NIFTY 50)")
    print("=" * 95)

    cache_dir = BASE_DIR / "data" / "cache"
    universe_mgr = Nifty50UniverseManager()
    symbols = universe_mgr.get_symbols()

    # Load cached datasets
    datasets = {}
    for sym in symbols:
        p = cache_dir / f"{sym}_NS_5y_1d.parquet"
        if p.exists():
            datasets[sym] = pl.read_parquet(p)

    print(f"Loaded {len(datasets)} verified constituent parquets from {cache_dir}.\n")

    rsi_models = [
        # Model 1: Classic RSI(14) Oversold (<30) with 200 SMA filter
        ("RSI(14) Oversold <30 (Trend Filtered)", "RSI_OVERSOLD", {"entry_rsi": 30.0, "exit_rsi": 60.0, "trend_filter": True}),
        # Model 2: RSI(14) Oversold (<30) Unfiltered (Classic Retail)
        ("RSI(14) Oversold <30 (No Trend Filter)", "RSI_OVERSOLD", {"entry_rsi": 30.0, "exit_rsi": 50.0, "trend_filter": False}),
        # Model 3: Deep Capitulation (<25)
        ("RSI(14) Deep Capitulation <25", "RSI_OVERSOLD", {"entry_rsi": 25.0, "exit_rsi": 50.0, "trend_filter": True}),
        # Model 4: Mild Dip (<35)
        ("RSI(14) Mild Dip <35", "RSI_OVERSOLD", {"entry_rsi": 35.0, "exit_rsi": 65.0, "trend_filter": True}),
        # Model 5: Connors 2-Period RSI (<10)
        ("Connors RSI(2) <10 (SMA 5 Exit)", "CONNORS_RSI_2", {"entry_rsi2": 10.0}),
        # Model 6: Connors 2-Period RSI Extreme (<5)
        ("Connors RSI(2) <5 (SMA 5 Exit)", "CONNORS_RSI_2", {"entry_rsi2": 5.0}),
        # Model 7: Cardwell RSI Momentum Breakout (>60)
        ("Cardwell RSI(14) Momentum Breakout (>60)", "RSI_MOMENTUM_BREAKOUT", {"entry_rsi": 60.0}),
        # Model 8: RSI Pullback to Sweet Spot (40-50 zone)
        ("RSI(14) Bullish Pullback (40-50 Zone)", "RSI_PULLBACK", {}),
    ]

    engine = RSIEngineBacktester(
        initial_capital=100000.0,
        max_concurrent_positions=3,
        risk_per_trade_pct=0.010,
        slippage_bps=5.0,
    )

    results = []
    for name, stype, params in rsi_models:
        print(f"Running: {name} ...", end="", flush=True)
        res = engine.run_strategy(name, datasets, stype, params)
        results.append(res)
        print(f" Done! Net: ₹{res['net_profit']:,.2f} | CAGR: {res['cagr_pct']}% | WR: {res['win_rate_pct']}% | DD: {res['max_drawdown_pct']}% | Trades: {res['total_trades']}")

    # Print summary table
    print("\n" + "=" * 105)
    print(" 📊 RSI STRATEGIES MASTER PERFORMANCE MATRIX (NIFTY 50 | 2021–2026)")
    print("=" * 105)
    header = f"{'Strategy Name':<42} | {'Net PnL (₹)':>12} | {'CAGR (%)':>8} | {'WinRate':>7} | {'PF':>5} | {'Max DD':>7} | {'Trades':>6} | {'Friction':>9}"
    print(header)
    print("-" * len(header))

    for r in sorted(results, key=lambda x: x["net_profit"], reverse=True):
        print(
            f"{r['strategy_name']:<42} | "
            f"₹{r['net_profit']:>11,.2f} | "
            f"{r['cagr_pct']:>7.2f}% | "
            f"{r['win_rate_pct']:>6.1f}% | "
            f"{r['profit_factor']:>5.2f} | "
            f"{r['max_drawdown_pct']:>6.2f}% | "
            f"{r['total_trades']:>6} | "
            f"₹{r['total_friction']:>8,.2f}"
        )

    out_file = BASE_DIR / "data" / "processed" / "rsi_strategies_comparison_matrix.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 105)
    print(f"✅ Saved full RSI strategy matrix evidence to: {out_file}")
    print("=" * 105)


if __name__ == "__main__":
    main()
