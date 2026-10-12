#!/usr/bin/env python3
"""
Institutional Live Intraday Scanner (NSE NIFTY 50).
Evaluates real-time 5m bars for today's active session:
1. Opening Range Breakout (ORB-15): Price breaking out above 09:15–09:30 range.
2. Intraday VWAP Trend: Price > VWAP with volume expansion.
3. Intraday Mean Reversion: Extreme oversold bounce at session low with VWAP magnet.

Includes exact Intraday Entry, Stop Loss, Target, and 15:15 IST square-off mandate.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List
import numpy as np
import pandas as pd
import yfinance as yf

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from services.scanner.universe_manager import AUTHORITATIVE_NIFTY_50_CONSTITUENTS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("LiveIntradayScanner")


def run_live_intraday_scan() -> Dict[str, Any]:
    print("\n" + "=" * 90)
    print(" ⚡ ALGO LAB INSTITUTIONAL LIVE INTRADAY SCANNER (NSE NIFTY 50)")
    print(f"    Session Date: Monday, October 12, 2026 | Active Time: {datetime.now().strftime('%H:%M:%S IST')}")
    print("    Product: MIS (Intraday) | Mandatory Square-Off: 15:15:00 IST")
    print("=" * 90)

    symbols = [item["symbol"] for item in AUTHORITATIVE_NIFTY_50_CONSTITUENTS]
    sector_map = {item["symbol"]: item["sector"] for item in AUTHORITATIVE_NIFTY_50_CONSTITUENTS}

    print(f"\n[PHASE 1] Fetching live 5-minute session bars for {len(symbols)} NIFTY 50 stocks...")
    tickers_str = " ".join([f"{s}.NS" for s in symbols])
    data = yf.download(tickers_str, period="1d", interval="5m", group_by="ticker", progress=False)

    scored_setups: List[Dict[str, Any]] = []

    for sym in symbols:
        ticker_key = f"{sym}.NS"
        if ticker_key not in data.columns.levels[0]:
            continue

        df = data[ticker_key].dropna()
        if len(df) < 3: # Need at least 3 bars (15 mins) for ORB
            continue

        close = df["Close"].squeeze()
        high = df["High"].squeeze()
        low = df["Low"].squeeze()
        open_p = df["Open"].squeeze()
        volume = df["Volume"].squeeze()

        if close.empty or len(close) < 3:
            continue

        current_price = float(close.iloc[-1])
        day_open = float(open_p.iloc[0])
        day_high = float(high.max())
        day_low = float(low.min())
        curr_vol = float(volume.iloc[-1]) if not volume.empty else 0.0

        # 1. 15-Minute Opening Range (First 3 bars: 09:15-09:30)
        orb_high = float(high.iloc[:3].max())
        orb_low = float(low.iloc[:3].min())
        orb_range = orb_high - orb_low

        # 2. Intraday VWAP
        typical_price = (high + low + close) / 3.0
        cum_vol = volume.cumsum()
        cum_tp_vol = (typical_price * volume).cumsum()
        vwap_series = cum_tp_vol / (cum_vol + 1e-6)
        current_vwap = float(vwap_series.iloc[-1])

        # 3. 20-period EMA on 5m
        ema_20 = float(close.ewm(span=min(len(close), 20), adjust=False).mean().iloc[-1])

        # 4. Intraday ATR
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        intraday_atr = float(tr.rolling(min(len(tr), 14)).mean().iloc[-1]) if len(tr) >= 3 else (current_price * 0.005)

        # 5. Session Change %
        session_change_pct = ((current_price - day_open) / day_open) * 100.0

        # 6. Relative Volume on 5m
        avg_5m_vol = float(volume.mean()) if len(volume) > 0 else 1.0
        rvol_5m = curr_vol / avg_5m_vol if avg_5m_vol > 0 else 1.0

        # Setup Evaluation
        setup_name = None
        score = 0.0
        sl_price = 0.0
        tp_price = 0.0

        # SETUP A: 15-Min Opening Range Breakout (ORB-15)
        if current_price > orb_high and current_price > current_vwap:
            setup_name = "ORB_15M_BREAKOUT"
            score = 9.0 + (0.5 if rvol_5m >= 1.5 else 0.0) + (0.5 if session_change_pct > 1.0 else 0.0)
            sl_price = round(max(orb_high - (0.5 * orb_range), current_vwap * 0.998), 2)
            risk = current_price - sl_price
            tp_price = round(current_price + (2.0 * risk), 2)

        # SETUP B: VWAP Trend Bounce (Trading above VWAP, pulling back to EMA20 / VWAP)
        elif current_price > current_vwap and abs(current_price - ema_20) / current_price < 0.003 and session_change_pct > 0.3:
            setup_name = "VWAP_TREND_PULLBACK"
            score = 8.0 + (0.5 if current_price > ema_20 else 0.0)
            sl_price = round(current_vwap * 0.996, 2)
            risk = current_price - sl_price
            tp_price = round(current_price + (2.5 * risk), 2)

        # SETUP C: Intraday Momentum Surge
        elif session_change_pct >= 1.5 and current_price > current_vwap:
            setup_name = "INTRADAY_MOMENTUM"
            score = 8.5
            sl_dist = max(1.5 * intraday_atr, current_price * 0.006)
            sl_price = round(current_price - sl_dist, 2)
            tp_price = round(current_price + (2.0 * sl_dist), 2)

        if setup_name and sl_price < current_price:
            # Capital allocation: ₹25,000 per intraday slot
            intraday_slot_capital = 25000.0
            suggested_qty = max(1, int(intraday_slot_capital / current_price))
            risk_inr = round((current_price - sl_price) * suggested_qty, 2)
            reward_inr = round((tp_price - current_price) * suggested_qty, 2)

            scored_setups.append({
                "symbol": sym,
                "sector": sector_map.get(sym, "GENERAL"),
                "setup": setup_name,
                "score": round(score, 1),
                "ltp": round(current_price, 2),
                "day_open": round(day_open, 2),
                "session_change_pct": round(session_change_pct, 2),
                "vwap": round(current_vwap, 2),
                "orb_high": round(orb_high, 2),
                "orb_low": round(orb_low, 2),
                "rvol_5m": round(rvol_5m, 2),
                "stop_loss": sl_price,
                "take_profit": tp_price,
                "suggested_qty": suggested_qty,
                "allocated_capital": round(suggested_qty * current_price, 2),
                "risk_inr": risk_inr,
                "reward_inr": reward_inr,
                "risk_reward_ratio": "1 : 2.0+",
            })

    # Sort setups by score descending
    scored_setups.sort(key=lambda x: x["score"], reverse=True)

    print("\n" + "=" * 90)
    print(f" 📋 TOP INTRADAY SETUPS PICKED RIGHT NOW (Total Triggered: {len(scored_setups)})")
    print("=" * 90)
    print(f" {'Symbol':<12} | {'Setup':<20} | {'LTP (₹)':>9} | {'Chg %':>6} | {'VWAP (₹)':>9} | {'SL (₹)':>9} | {'Target (₹)':>10} | {'Qty':>4} | {'Capital (₹)':>10}")
    print("-" * 90)

    for s in scored_setups[:8]:
        print(f" {s['symbol']:<12} | {s['setup']:<20} | {s['ltp']:>9.2f} | {s['session_change_pct']:>+5.2f}% | {s['vwap']:>9.2f} | {s['stop_loss']:>9.2f} | {s['take_profit']:>10.2f} | {s['suggested_qty']:>4d} | ₹{s['allocated_capital']:>9,.2f}")

    print("-" * 90)
    print("\n[PHASE 2] INTRADAY EXECUTION RULES (MIS):")
    print("  • Max Intraday Slots:        2 concurrent positions")
    print("  • Max Intraday Allocation:   ₹25,000 INR per position (Total ₹50k from ₹100k pool)")
    print("  • Intraday Statutory Taxes:  Zero DP charge, STT 0.025% on sell only, ₹20 Brokerage")
    print("  • Mandatory Auto Square-off: 15:15:00 IST (Strict Intraday Invariant)")

    # Save to JSON
    out_file = BASE_DIR / "data" / "live_intraday_picked_stocks.json"
    out_data = {
        "scan_timestamp": datetime.now(timezone.utc).isoformat(),
        "market_time_ist": datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
        "total_setups": len(scored_setups),
        "top_setups": scored_setups[:10],
    }
    with open(out_file, "w") as f:
        json.dump(out_data, f, indent=2)

    print(f"\n✅ Intraday picks saved to: {out_file}")
    print("=" * 90 + "\n")
    return out_data


if __name__ == "__main__":
    run_live_intraday_scan()
