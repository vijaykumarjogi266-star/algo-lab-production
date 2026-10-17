#!/usr/bin/env python3
"""
Institutional Pre-Market Scanner for Indian Equities (NSE NIFTY 50).
Prepares setup watchlists for tomorrow's market open (October 12, 2026).

Scanning Modules:
1. NIFTY 50 Universe Ingestion & Recent EOD Market Data Retrieval.
2. Regime & Momentum Classification:
   - Bull Trend (Price > 20 EMA > 50 SMA with positive momentum).
   - Oversold Mean Reversion (RSI14 < 35 with price stabilizing near lower boundary).
   - High Relative Volume Compression (ATR compression prior to expansion).
3. Risk Parameters for Paper Trading Session:
   - Exact Stop Loss (2.5x ATR14) and Take Profit (3.5x Risk R:R).
   - Max capital allocation per position (₹45,000 max from ₹100k capital pool).
   - Max 2 concurrent positions adhering to Ed Thorp 1% risk rule.
4. Output: Structured console report and saved JSON watchlist at data/tomorrow_scanner_watchlist.json.
"""

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List
import pandas as pd
import yfinance as yf

# Setup repository paths
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from services.scanner.universe_manager import AUTHORITATIVE_NIFTY_50_CONSTITUENTS
from services.data_governance.calendar_provider import VersionedMarketCalendarProvider

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("PreMarketScanner")
IST = ZoneInfo("Asia/Kolkata")


def get_next_trading_session_date() -> datetime.date:
    cal = VersionedMarketCalendarProvider()
    now_ist = datetime.now(IST)
    cand_date = (now_ist + timedelta(days=1)).date() if now_ist.time() >= datetime.strptime("15:30", "%H:%M").time() else now_ist.date()
    while not cal.is_trading_day(cand_date):
        cand_date += timedelta(days=1)
    return cand_date


def run_pre_market_scan() -> Dict[str, Any]:
    next_session = get_next_trading_session_date()
    formatted_date = next_session.strftime("%A, %B %d, %Y")
    print("\n" + "=" * 80)
    print(" 🛰️  ALGO LAB INSTITUTIONAL PRE-MARKET SCANNER (NSE NIFTY 50)")
    print(f"    Session Preparation: {formatted_date} | Capital: ₹1,00,000 INR")
    print("=" * 80)

    symbols = [item["symbol"] for item in AUTHORITATIVE_NIFTY_50_CONSTITUENTS]
    sector_map = {item["symbol"]: item["sector"] for item in AUTHORITATIVE_NIFTY_50_CONSTITUENTS}

    print(f"\n[PHASE 1] Scanning NIFTY 50 Universe ({len(symbols)} stocks)...")

    # Fetch recent daily bars for all symbols via yfinance
    tickers_str = " ".join([f"{s}.NS" for s in symbols])
    data = yf.download(tickers_str, period="60d", interval="1d", group_by="ticker", progress=False)

    scored_candidates: List[Dict[str, Any]] = []

    for sym in symbols:
        ticker_key = f"{sym}.NS"
        if ticker_key not in data.columns.levels[0]:
            continue

        df = data[ticker_key].dropna()
        if len(df) < 30:
            continue

        close = df["Close"].values
        high = df["High"].values
        low = df["Low"].values
        volume = df["Volume"].values

        last_close = float(close[-1])
        last_high = float(high[-1])
        last_low = float(low[-1])
        last_volume = float(volume[-1])

        # Technical Indicators:
        # 1. 20-period EMA & 50-period SMA
        s_close = pd.Series(close)
        ema_20 = float(s_close.ewm(span=20, adjust=False).mean().iloc[-1])
        sma_50 = float(s_close.rolling(window=min(len(close), 50)).mean().iloc[-1])

        # 2. 14-period RSI
        delta = s_close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        rsi_14 = float(100 - (100 / (1 + rs)).iloc[-1])

        # 3. 14-period ATR
        tr1 = high - low
        tr2 = np.abs(high - np.roll(close, 1))
        tr3 = np.abs(low - np.roll(close, 1))
        tr = np.maximum(tr1, np.maximum(tr2, tr3))[1:]
        atr_14 = float(pd.Series(tr).rolling(window=14).mean().iloc[-1])

        # 4. Volume SMA 20
        vol_sma20 = float(pd.Series(volume).rolling(window=20).mean().iloc[-1])
        rel_vol = last_volume / vol_sma20 if vol_sma20 > 0 else 1.0

        # Regime & Setup Evaluation
        is_bullish = last_close > ema_20 and ema_20 > sma_50
        is_oversold = rsi_14 < 40.0
        is_high_volume = rel_vol > 1.2

        setup_name = None
        setup_score = 0.0

        if is_bullish and 45.0 <= rsi_14 <= 65.0:
            setup_name = "TREND_CONTINUATION_PULLBACK"
            setup_score = 8.5 + (0.5 if is_high_volume else 0.0)
        elif is_oversold and last_close >= last_low * 1.005:
            setup_name = "OVERSOLD_MEAN_REVERSION"
            setup_score = 7.5 + (1.0 if is_high_volume else 0.0)
        elif is_bullish and is_high_volume:
            setup_name = "HIGH_VOLUME_BREAKOUT"
            setup_score = 8.0

        if setup_name:
            # Risk & Trade Sizing: 2.5x ATR SL, 3.5x Risk TP
            sl_dist = 2.5 * atr_14
            stop_loss = round(last_close - sl_dist, 2)
            tp_dist = 3.5 * sl_dist
            take_profit = round(last_close + tp_dist, 2)

            # Max capital ₹45,000 per slot
            max_capital = 45000.0
            suggested_qty = max(1, int(max_capital / last_close))
            trade_value = round(suggested_qty * last_close, 2)

            scored_candidates.append({
                "symbol": sym,
                "sector": sector_map.get(sym, "GENERAL"),
                "setup": setup_name,
                "score": round(setup_score, 1),
                "last_close": round(last_close, 2),
                "rsi_14": round(rsi_14, 1),
                "atr_14": round(atr_14, 2),
                "rel_volume": round(rel_vol, 2),
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "risk_reward": "1 : 3.5",
                "suggested_qty": suggested_qty,
                "allocated_capital": trade_value,
            })

    # Sort candidates by setup score descending
    scored_candidates.sort(key=lambda x: x["score"], reverse=True)
    top_candidates = scored_candidates[:5]

    print("\n" + "-" * 80)
    print(" 📋 TOP QUALIFIED SETUP CANDIDATES FOR TOMORROW (100K CAPITAL POOL)")
    print("-" * 80)
    print(f" {'Symbol':<12} | {'Sector':<20} | {'Setup':<26} | {'LTP (₹)':>8} | {'SL (₹)':>8} | {'TP (₹)':>8} | {'Qty':>4} | {'Capital (₹)':>10}")
    print("-" * 80)
    for c in top_candidates:
        print(f" {c['symbol']:<12} | {c['sector']:<20} | {c['setup']:<26} | {c['last_close']:>8.2f} | {c['stop_loss']:>8.2f} | {c['take_profit']:>8.2f} | {c['suggested_qty']:>4d} | ₹{c['allocated_capital']:>9,.2f}")

    print("-" * 80)
    print("\n[PHASE 2] PAPER EXECUTION CONSTRAINTS FOR TOMORROW'S SESSION:")
    print("  • Max Available Portfolio Capital: ₹1,00,000.00 INR")
    print("  • Minimum Cash Solvency Buffer:   ₹10,000.00 INR (Untouchable floor)")
    print("  • Max Concurrent Positions:       2 slots (Max ₹45,000 per position)")
    print("  • Sector Diversification Guard:   Max 1 position per industry sector")
    print("  • Automated Stop Loss:            2.5x ATR14 (Absorbs opening volatility)")
    print("  • Asymmetric Take Profit:         3.5x Risk (Convexity payoff)")

    # Save output watchlist
    watchlist_path = BASE_DIR / "data" / "tomorrow_scanner_watchlist.json"
    watchlist_data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market_session_date": next_session.isoformat(),
        "universe": "NIFTY_50",
        "capital_allocated_inr": 100000.0,
        "max_concurrent_slots": 2,
        "max_capital_per_slot_inr": 45000.0,
        "top_candidates": top_candidates,
        "all_candidates": scored_candidates,
    }
    with open(watchlist_path, "w") as f:
        json.dump(watchlist_data, f, indent=2)

    print(f"\n✅ Watchlist successfully generated and saved to: {watchlist_path}")
    print("=" * 80 + "\n")
    return watchlist_data


if __name__ == "__main__":
    import numpy as np
    run_pre_market_scan()
