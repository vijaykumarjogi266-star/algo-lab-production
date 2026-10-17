#!/usr/bin/env python3
"""
Algo Lab — Comprehensive Multi-Strategy Live Scanner & Empirical Backtester.
1. Live Signal Scan across all 5 registered quantitative strategies:
   - Bollinger Bands Mean Reversion
   - Opening Range Breakout (ORB)
   - VWAP Mean Reversion
   - SMA / EMA Momentum Crossover
   - Donchian Channel Breakout
2. Rigorous Comparative Backtest:
   - Bollinger Reversion vs Opening Range Breakout (ORB)
"""

import sys
import os
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd
import yfinance as yf

# Ensure project root in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from quant.strategies.registry import StrategyRegistry
from quant.strategies.bollinger_reversion import BollingerReversion
from quant.strategies.orb import OpeningRangeBreakout
from quant.strategies.vwap_reversion import VWAPReversion
from quant.strategies.sma_cross import SMACross
from quant.strategies.donchian_breakout import DonchianBreakout

WATCHLIST = [
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "INFY.NS",
    "SBIN.NS",
]


def run_live_strategy_scan(symbols):
    print("=" * 80)
    print("PART 1: LIVE MULTI-STRATEGY SCANNER (ALL 5 CANONICAL STRATEGIES)")
    print(f"Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} | Universe: {len(symbols)} Large-Cap Equities")
    print("=" * 80)

    strategies = [
        ("STRAT_BOLLINGER_REVERSION", "Bollinger Mean Reversion"),
        ("STRAT_ORB", "Opening Range Breakout"),
        ("STRAT_VWAP_REVERSION", "VWAP Reversion"),
        ("STRAT_SMA", "EMA/SMA Momentum Cross"),
        ("STRAT_DONCHIAN_BREAKOUT", "Donchian 20d Breakout"),
    ]

    scan_results = []

    for sym in symbols:
        try:
            df = yf.download(sym, period="1mo", interval="1d", progress=False)
            if hasattr(df.columns, "levels") and len(df.columns.levels) > 1:
                df.columns = df.columns.get_level_values(0)
            df = df.dropna(subset=["Close", "High", "Low"])

            if len(df) < 20:
                print(f"Skipping {sym}: insufficient historical bars ({len(df)} bars)")
                continue

            closes = df["Close"].values.astype(float)
            highs = df["High"].values.astype(float)
            lows = df["Low"].values.astype(float)
            vols = df["Volume"].values.astype(float)
            latest_price = round(closes[-1], 2)

            # Technical indicators
            sma20 = float(np.mean(closes[-20:]))
            std20 = float(np.std(closes[-20:]))
            lower_bb = round(sma20 - (2.0 * std20), 2)
            upper_bb = round(sma20 + (2.0 * std20), 2)
            tr = np.maximum(highs[1:] - lows[1:], np.maximum(abs(highs[1:] - closes[:-1]), abs(lows[1:] - closes[:-1])))
            atr = float(np.mean(tr[-14:])) if len(tr) >= 14 else float(latest_price * 0.015)

            # Highs/Lows for Donchian
            highest_20 = float(np.max(highs[-20:]))
            lowest_20 = float(np.min(lows[-20:]))

            market_payload = {
                "price": latest_price,
                "closes": closes.tolist(),
                "highs": highs.tolist(),
                "lows": lows.tolist(),
                "volumes": vols.tolist(),
                "atr": atr,
                "lower_bb": lower_bb,
                "upper_bb": upper_bb,
                "sma20": sma20,
                "highest_20": highest_20,
                "lowest_20": lowest_20,
                "bar_timestamp": datetime.now(timezone.utc).isoformat(),
            }

            sym_signals = {}
            for strat_id, strat_name in strategies:
                decision = StrategyRegistry.dispatch_symbol(strat_id, sym, market_payload)
                sig = decision.get("signal", "WAIT")
                conf = decision.get("confidence", 0.0)
                sl = decision.get("stop_loss")
                tp = decision.get("target")
                sym_signals[strat_id] = {
                    "signal": sig,
                    "confidence": conf,
                    "stop_loss": sl,
                    "target": tp,
                    "reason": decision.get("reason", ""),
                }

            scan_results.append({
                "symbol": sym,
                "price": latest_price,
                "lower_bb": lower_bb,
                "upper_bb": upper_bb,
                "atr": round(atr, 2),
                "signals": sym_signals,
            })
        except Exception as e:
            print(f"Error scanning {sym}: {e}")

    # Display Scan Table
    header = f"{'Symbol':<12} | {'Price':<9} | {'Bollinger':<10} | {'ORB':<8} | {'VWAP':<8} | {'SMA Cross':<10} | {'Donchian':<10}"
    print(header)
    print("-" * len(header))
    for r in scan_results:
        sym = r["symbol"]
        px = f"₹{r['price']:.2f}"
        sig_bb = r["signals"]["STRAT_BOLLINGER_REVERSION"]["signal"]
        sig_orb = r["signals"]["STRAT_ORB"]["signal"]
        sig_vwap = r["signals"]["STRAT_VWAP_REVERSION"]["signal"]
        sig_sma = r["signals"]["STRAT_SMA"]["signal"]
        sig_don = r["signals"]["STRAT_DONCHIAN_BREAKOUT"]["signal"]
        print(f"{sym:<12} | {px:<9} | {sig_bb:<10} | {sig_orb:<8} | {sig_vwap:<8} | {sig_sma:<10} | {sig_don:<10}")

    print("\nDetailed Strategy Setup Insights:")
    for r in scan_results:
        print(f"\n[{r['symbol']}] LTP: ₹{r['price']} | ATR(14): ₹{r['atr']} | BB: [₹{r['lower_bb']} - ₹{r['upper_bb']}]")
        for strat_id, s in r["signals"].items():
            if s["signal"] != "WAIT":
                print(f"  ⚡ {strat_id}: {s['signal']} (SL: {s['stop_loss']} | Target: {s['target']}) - Reason: {s['reason']}")
            else:
                print(f"  • {strat_id}: WAIT")


def run_comparative_backtest(symbols):
    print("\n" + "=" * 80)
    print("PART 2: EMPIRICAL BACKTEST COMPARISON: BOLLINGER REVERSION vs ORB")
    print("Backtest Period: 3 Months Hourly Bars (NSE Intraday Session Structure)")
    print("Capital: INR 100,000 per strategy | Leverage: 1x | Slippage & Fees: Included (10 bps)")
    print("=" * 80)

    bb_results = {"trades": [], "wins": [], "losses": [], "pnls": []}
    orb_results = {"trades": [], "wins": [], "losses": [], "pnls": []}

    fee_pct = 0.0010  # 10 bps total round-trip brokerage + STT + slippage

    for sym in symbols:
        try:
            df = yf.download(sym, period="3mo", interval="1h", progress=False)
            if hasattr(df.columns, "levels") and len(df.columns.levels) > 1:
                df.columns = df.columns.get_level_values(0)
            df = df.dropna(subset=["Close", "High", "Low"])

            if len(df) < 50:
                continue

            closes = df["Close"].values.astype(float)
            highs = df["High"].values.astype(float)
            lows = df["Low"].values.astype(float)
            vols = df["Volume"].values.astype(float)

            # ----------------------------------------------------
            # 1. Backtest Strategy A: Bollinger Bands Mean Reversion
            # ----------------------------------------------------
            bb_period = 20
            bb_pos = None
            bb_entry_px = 0.0
            bb_stop = 0.0
            bb_tp = 0.0

            for i in range(bb_period, len(closes)):
                w_close = closes[i-bb_period:i]
                sma = np.mean(w_close)
                std = np.std(w_close)
                lower_band = sma - (2.0 * std)
                upper_band = sma + (2.0 * std)
                curr_c = closes[i]
                curr_l = lows[i]
                curr_h = highs[i]

                # Position Exit
                if bb_pos is not None:
                    exit_px = None
                    if curr_l <= bb_stop:
                        exit_px = bb_stop
                    elif curr_h >= bb_tp:
                        exit_px = bb_tp

                    if exit_px is not None:
                        ret = (exit_px - bb_entry_px) / bb_entry_px - fee_pct
                        pnl = ret * 100000.0  # Normalized 100k capital allocation
                        bb_results["trades"].append(ret)
                        bb_results["pnls"].append(pnl)
                        if ret > 0:
                            bb_results["wins"].append(ret)
                        else:
                            bb_results["losses"].append(ret)
                        bb_pos = None

                # Position Entry
                if bb_pos is None and curr_c < lower_band:
                    bb_pos = "LONG"
                    bb_entry_px = curr_c
                    bb_stop = curr_c * 0.985  # 1.5% SL
                    bb_tp = sma               # Mean reversion target

            # ----------------------------------------------------
            # 2. Backtest Strategy B: Opening Range Breakout (ORB)
            # ----------------------------------------------------
            # Approximate ORB using daily open range expansion on hourly bars
            orb_pos = None
            orb_entry_px = 0.0
            orb_stop = 0.0
            orb_tp = 0.0

            for i in range(6, len(closes)):
                # 6 hourly bars per trading day approx in NSE
                day_bar_idx = i % 6
                curr_c = closes[i]
                curr_h = highs[i]
                curr_l = lows[i]

                if day_bar_idx == 0:
                    # Opening candle established
                    range_high = highs[i]
                    range_low = lows[i]
                    range_size = range_high - range_low
                elif day_bar_idx > 0 and 'range_high' in locals():
                    # Check for exit if in position
                    if orb_pos is not None:
                        exit_px = None
                        if curr_l <= orb_stop:
                            exit_px = orb_stop
                        elif curr_h >= orb_tp:
                            exit_px = orb_tp
                        elif day_bar_idx == 5:
                            # EOD intraday square-off
                            exit_px = curr_c

                        if exit_px is not None:
                            ret = (exit_px - orb_entry_px) / orb_entry_px - fee_pct
                            pnl = ret * 100000.0
                            orb_results["trades"].append(ret)
                            orb_results["pnls"].append(pnl)
                            if ret > 0:
                                orb_results["wins"].append(ret)
                            else:
                                orb_results["losses"].append(ret)
                            orb_pos = None

                    # Entry on breakout beyond first candle
                    if orb_pos is None and curr_c > range_high and range_size > 0:
                        orb_pos = "LONG"
                        orb_entry_px = curr_c
                        orb_stop = range_low
                        orb_tp = curr_c + (2.0 * range_size)

        except Exception as e:
            print(f"Backtest error on {sym}: {e}")

    # Compute Statistics
    def compute_stats(name, data):
        trades = data["trades"]
        if not trades:
            return {"name": name, "trades_count": 0}
        n_trades = len(trades)
        wins = len(data["wins"])
        losses = len(data["losses"])
        win_rate = (wins / n_trades) * 100 if n_trades > 0 else 0.0
        tot_pnl = sum(data["pnls"])
        avg_ret = np.mean(trades) * 100
        gross_profit = sum([p for p in data["pnls"] if p > 0])
        gross_loss = abs(sum([p for p in data["pnls"] if p < 0]))
        pf = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        # Drawdown calculation
        cum_pnls = np.cumsum(data["pnls"])
        cum_equity = 100000.0 + cum_pnls
        peak = np.maximum.accumulate(cum_equity)
        dd = (peak - cum_equity) / peak
        max_dd = np.max(dd) * 100 if len(dd) > 0 else 0.0

        # Sharpe ratio (annualized hourly: sqrt(252*6))
        sharpe = (np.mean(trades) / np.std(trades) * np.sqrt(252 * 6)) if np.std(trades) > 0 else 0.0

        return {
            "name": name,
            "trades_count": n_trades,
            "win_rate": win_rate,
            "net_pnl": tot_pnl,
            "avg_return": avg_ret,
            "profit_factor": pf,
            "max_drawdown": max_dd,
            "sharpe": sharpe,
        }

    bb_stats = compute_stats("STRAT_BOLLINGER_REVERSION", bb_results)
    orb_stats = compute_stats("STRAT_ORB", orb_results)

    print(f"\n{'Metric':<28} | {'Bollinger Reversion':<22} | {'Opening Range Breakout (ORB)':<25}")
    print("-" * 80)
    print(f"{'Total Trades':<28} | {bb_stats['trades_count']:<22} | {orb_stats['trades_count']:<25}")
    print(f"{'Win Rate (%)':<28} | {bb_stats['win_rate']:<21.2f}% | {orb_stats['win_rate']:<24.2f}%")
    print(f"{'Profit Factor':<28} | {bb_stats['profit_factor']:<22.2f} | {orb_stats['profit_factor']:<25.2f}")
    print(f"{'Cumulative Net PnL (INR)':<28} | ₹{bb_stats['net_pnl']:<21,.2f} | ₹{orb_stats['net_pnl']:<24,.2f}")
    print(f"{'Average Return per Trade':<28} | {bb_stats['avg_return']:<21.2f}% | {orb_stats['avg_return']:<24.2f}%")
    print(f"{'Max Drawdown (%)':<28} | {bb_stats['max_drawdown']:<21.2f}% | {orb_stats['max_drawdown']:<24.2f}%")
    print(f"{'Sharpe Ratio (Annualized)':<28} | {bb_stats['sharpe']:<22.2f} | {orb_stats['sharpe']:<25.2f}")
    print("=" * 80)


if __name__ == "__main__":
    run_live_strategy_scan(WATCHLIST)
    run_comparative_backtest(WATCHLIST)
