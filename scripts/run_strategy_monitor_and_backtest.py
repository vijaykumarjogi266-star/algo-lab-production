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


def calculate_adx(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(closes)
    tr = np.zeros(n)
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    for i in range(1, n):
        h, l, prev_c = highs[i], lows[i], closes[i-1]
        tr[i] = max(h - l, abs(h - prev_c), abs(l - prev_c))
        up = highs[i] - highs[i-1]
        down = lows[i-1] - lows[i]
        if up > down and up > 0:
            plus_dm[i] = up
        if down > up and down > 0:
            minus_dm[i] = down
    atr = pd.Series(tr).ewm(alpha=1/period, adjust=False).mean().values
    smooth_plus = pd.Series(plus_dm).ewm(alpha=1/period, adjust=False).mean().values
    smooth_minus = pd.Series(minus_dm).ewm(alpha=1/period, adjust=False).mean().values
    plus_di = 100 * (smooth_plus / (atr + 1e-9))
    minus_di = 100 * (smooth_minus / (atr + 1e-9))
    dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9))
    adx = pd.Series(dx).ewm(alpha=1/period, adjust=False).mean().values
    return adx


def run_comparative_backtest(symbols):
    print("\n" + "=" * 80)
    print("PART 2: EMPIRICAL BACKTEST COMPARISON: BASELINE vs HARDENED INSTITUTIONAL")
    print("Backtest Period: 3 Months Hourly Bars (NSE Intraday Session Structure)")
    print("Capital: INR 100,000 per strategy | Leverage: 1x | Statutory Costs: 10 bps")
    print("=" * 80)

    bb_results = {"trades": [], "wins": [], "losses": [], "pnls": []}
    bb_hardened = {"trades": [], "wins": [], "losses": [], "pnls": []}
    orb_results = {"trades": [], "wins": [], "losses": [], "pnls": []}
    orb_hardened = {"trades": [], "wins": [], "losses": [], "pnls": []}
    ema_pullback = {"trades": [], "wins": [], "losses": [], "pnls": []}

    fee_pct = 0.0010  # 10 bps total round-trip brokerage + STT + slippage

    for sym in symbols:
        try:
            df = yf.download(sym, period="3mo", interval="1h", progress=False)
            if hasattr(df.columns, "levels") and len(df.columns.levels) > 1:
                df.columns = df.columns.get_level_values(0)
            df = df.dropna(subset=["Close", "High", "Low", "Volume"])

            if len(df) < 50:
                continue

            closes = df["Close"].values.astype(float)
            highs = df["High"].values.astype(float)
            lows = df["Low"].values.astype(float)
            vols = df["Volume"].values.astype(float)
            adx = calculate_adx(highs, lows, closes, 14)

            # ----------------------------------------------------
            # 1. Baseline Bollinger Bands Mean Reversion
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
                curr_c = closes[i]
                curr_l = lows[i]
                curr_h = highs[i]

                if bb_pos is not None:
                    exit_px = None
                    if curr_l <= bb_stop:
                        exit_px = bb_stop
                    elif curr_h >= bb_tp:
                        exit_px = bb_tp
                    if exit_px is not None:
                        ret = (exit_px - bb_entry_px) / bb_entry_px - fee_pct
                        bb_results["trades"].append(ret)
                        bb_results["pnls"].append(ret * 100000.0)
                        if ret > 0: bb_results["wins"].append(ret)
                        else: bb_results["losses"].append(ret)
                        bb_pos = None

                if bb_pos is None and curr_c < lower_band:
                    bb_pos = "LONG"
                    bb_entry_px = curr_c
                    bb_stop = curr_c * 0.985
                    bb_tp = sma

            # ----------------------------------------------------
            # 1b. Hardened Bollinger: ADX <= 25 + 2-Bar Time-Stop + ATR SL
            # ----------------------------------------------------
            hbb_pos = None
            hbb_bars = 0
            hbb_entry = 0.0
            hbb_stop = 0.0
            hbb_tp = 0.0

            for i in range(bb_period, len(closes)):
                w_close = closes[i-bb_period:i]
                sma = np.mean(w_close)
                std = np.std(w_close)
                lower_band = sma - (2.0 * std)
                curr_c = closes[i]
                curr_l = lows[i]
                curr_h = highs[i]
                atr = np.mean(np.maximum(highs[i-14:i] - lows[i-14:i], abs(highs[i-14:i] - closes[i-15:i-1]))) if i >= 15 else (curr_c * 0.015)

                if hbb_pos is not None:
                    hbb_bars += 1
                    exit_px = None
                    if curr_l <= hbb_stop:
                        exit_px = hbb_stop
                    elif curr_h >= hbb_tp:
                        exit_px = hbb_tp
                    elif hbb_bars >= 2:  # 2-hour Time-Stop: cuts stale bleeds
                        exit_px = curr_c

                    if exit_px is not None:
                        ret = (exit_px - hbb_entry) / hbb_entry - fee_pct
                        bb_hardened["trades"].append(ret)
                        bb_hardened["pnls"].append(ret * 100000.0)
                        if ret > 0: bb_hardened["wins"].append(ret)
                        else: bb_hardened["losses"].append(ret)
                        hbb_pos = None

                # Gated by ADX <= 25 (non-trending regime only)
                if hbb_pos is None and curr_c < lower_band and adx[i] <= 25:
                    hbb_pos = "LONG"
                    hbb_bars = 0
                    hbb_entry = curr_c
                    hbb_stop = curr_c - (1.5 * atr)
                    hbb_tp = sma

            # ----------------------------------------------------
            # 2. Baseline Opening Range Breakout (ORB)
            # ----------------------------------------------------
            orb_pos = None
            orb_entry_px = 0.0
            orb_stop = 0.0
            orb_tp = 0.0

            for i in range(6, len(closes)):
                day_bar_idx = i % 6
                curr_c = closes[i]
                curr_h = highs[i]
                curr_l = lows[i]

                if day_bar_idx == 0:
                    range_high = highs[i]
                    range_low = lows[i]
                    range_size = range_high - range_low
                elif day_bar_idx > 0 and 'range_high' in locals():
                    if orb_pos is not None:
                        exit_px = None
                        if curr_l <= orb_stop:
                            exit_px = orb_stop
                        elif curr_h >= orb_tp:
                            exit_px = orb_tp
                        elif day_bar_idx == 5:
                            exit_px = curr_c
                        if exit_px is not None:
                            ret = (exit_px - orb_entry_px) / orb_entry_px - fee_pct
                            orb_results["trades"].append(ret)
                            orb_results["pnls"].append(ret * 100000.0)
                            if ret > 0: orb_results["wins"].append(ret)
                            else: orb_results["losses"].append(ret)
                            orb_pos = None

                    if orb_pos is None and curr_c > range_high and range_size > 0:
                        orb_pos = "LONG"
                        orb_entry_px = curr_c
                        orb_stop = range_low
                        orb_tp = curr_c + (2.0 * range_size)

            # ----------------------------------------------------
            # 2b. Hardened ORB: 2.0x Volume Hurdle + ADX > 25 + Trend Filter
            # ----------------------------------------------------
            horb_pos = None
            horb_entry = 0.0
            horb_stop = 0.0
            horb_tp = 0.0

            for i in range(20, len(closes)):
                day_bar_idx = i % 6
                curr_c = closes[i]
                curr_h = highs[i]
                curr_l = lows[i]
                curr_v = vols[i]
                avg_v20 = np.mean(vols[i-20:i])
                sma20 = np.mean(closes[i-20:i])

                if day_bar_idx == 0:
                    hrange_high = highs[i]
                    hrange_low = lows[i]
                    hrange_size = hrange_high - hrange_low
                elif day_bar_idx > 0 and 'hrange_high' in locals():
                    if horb_pos is not None:
                        exit_px = None
                        if curr_l <= horb_stop:
                            exit_px = horb_stop
                        elif curr_h >= horb_tp:
                            exit_px = horb_tp
                        elif day_bar_idx == 5:
                            exit_px = curr_c
                        if exit_px is not None:
                            ret = (exit_px - horb_entry) / horb_entry - fee_pct
                            orb_hardened["trades"].append(ret)
                            orb_hardened["pnls"].append(ret * 100000.0)
                            if ret > 0: orb_hardened["wins"].append(ret)
                            else: orb_hardened["losses"].append(ret)
                            horb_pos = None

                    # Strict Gate: 2.0x Volume + ADX > 25 + Price > SMA20
                    if (horb_pos is None and curr_c > hrange_high and hrange_size > 0
                            and curr_v >= 2.0 * avg_v20 and adx[i] > 25 and curr_c > sma20):
                        horb_pos = "LONG"
                        horb_entry = curr_c
                        horb_stop = hrange_low
                        horb_tp = curr_c + (2.0 * hrange_size)

            # ----------------------------------------------------
            # 3. EMA 9/21 Trend Pullback Swing with 2.0x ATR Trailing Stop
            # ----------------------------------------------------
            ema_pos = None
            ema_entry = 0.0
            ema_stop = 0.0
            for i in range(21, len(closes)):
                c = closes[i]
                l = lows[i]
                h = highs[i]
                fast_ema = pd.Series(closes[:i+1]).ewm(span=9, adjust=False).mean().iloc[-1]
                slow_ema = pd.Series(closes[:i+1]).ewm(span=21, adjust=False).mean().iloc[-1]
                sma50 = np.mean(closes[i-50:i]) if i >= 50 else slow_ema
                atr = np.mean(np.maximum(highs[i-14:i] - lows[i-14:i], abs(highs[i-14:i] - closes[i-15:i-1]))) if i >= 15 else (c * 0.015)

                if ema_pos is not None:
                    # Ratchet trailing stop
                    new_stop = c - (2.0 * atr)
                    if new_stop > ema_stop:
                        ema_stop = new_stop
                    exit_px = None
                    if l <= ema_stop:
                        exit_px = ema_stop
                    elif fast_ema < slow_ema:
                        exit_px = c
                    if exit_px is not None:
                        ret = (exit_px - ema_entry) / ema_entry - fee_pct
                        ema_pullback["trades"].append(ret)
                        ema_pullback["pnls"].append(ret * 100000.0)
                        if ret > 0: ema_pullback["wins"].append(ret)
                        else: ema_pullback["losses"].append(ret)
                        ema_pos = None

                # Entry: Primary uptrend (EMA9 > EMA21 > SMA50) + Pullback touch to EMA9
                if (ema_pos is None and fast_ema > slow_ema and c > sma50 and l <= fast_ema and c >= fast_ema and adx[i] > 20):
                    ema_pos = "LONG"
                    ema_entry = c
                    ema_stop = c - (2.0 * atr)

        except Exception as e:
            print(f"Backtest error on {sym}: {e}")

    # Compute Statistics Helper
    def compute_stats(name, data):
        trades = data["trades"]
        if not trades:
            return {"name": name, "trades_count": 0, "win_rate": 0.0, "profit_factor": 0.0, "net_pnl": 0.0, "avg_return": 0.0, "max_drawdown": 0.0, "sharpe": 0.0}
        n_trades = len(trades)
        wins = len(data["wins"])
        win_rate = (wins / n_trades) * 100 if n_trades > 0 else 0.0
        tot_pnl = sum(data["pnls"])
        avg_ret = np.mean(trades) * 100
        gross_profit = sum([p for p in data["pnls"] if p > 0])
        gross_loss = abs(sum([p for p in data["pnls"] if p < 0]))
        pf = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
        cum_pnls = np.cumsum(data["pnls"])
        cum_equity = 100000.0 + cum_pnls
        peak = np.maximum.accumulate(cum_equity)
        dd = (peak - cum_equity) / peak
        max_dd = np.max(dd) * 100 if len(dd) > 0 else 0.0
        sharpe = (np.mean(trades) / np.std(trades) * np.sqrt(252 * 6)) if np.std(trades) > 0 else 0.0
        return {
            "name": name,
            "trades_count": n_trades,
            "win_rate": win_rate,
            "profit_factor": pf,
            "net_pnl": tot_pnl,
            "avg_return": avg_ret,
            "max_drawdown": max_dd,
            "sharpe": sharpe,
        }

    stats = [
        compute_stats("Baseline ORB", orb_results),
        compute_stats("Hardened ORB (2.0x Vol + ADX)", orb_hardened),
        compute_stats("Baseline Bollinger Reversion", bb_results),
        compute_stats("Hardened Bollinger (Time-Stop + ADX)", bb_hardened),
        compute_stats("EMA 9/21 Trend Pullback", ema_pullback),
    ]

    print(f"\n{'Strategy Model':<35} | {'Trades':<7} | {'Win %':<7} | {'PF':<6} | {'Net PnL (₹)':<14} | {'Max DD %':<9} | {'Sharpe':<7}")
    print("-" * 96)
    for s in stats:
        print(f"{s['name']:<35} | {s['trades_count']:<7} | {s['win_rate']:<6.1f}% | {s['profit_factor']:<6.2f} | ₹{s['net_pnl']:<13,.2f} | {s['max_drawdown']:<8.2f}% | {s['sharpe']:<7.2f}")
    print("=" * 96)



if __name__ == "__main__":
    run_live_strategy_scan(WATCHLIST)
    run_comparative_backtest(WATCHLIST)
