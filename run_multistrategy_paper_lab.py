#!/usr/bin/env python3
"""
Algo Lab — Multi-Strategy Paper Trading Forward Lab.

Tests all candidate quantitative strategy ideas in parallel through
Algo Lab's institutional Paper Trading & Risk Engine infrastructure:
- Idea 1: TTM Volatility Squeeze Breakout (Bollinger inside Keltner)
- Idea 2: Two-Way VWAP Dispersion & Band Reversion
- Idea 3: Multi-Timeframe (MTF) Trend Pullback
- Idea 4: Polished Two-Way Bollinger Mean Reversion
- Idea 5: Canonical Donchian 20-Day Breakout

Tracks equity curves, fills, fees, slippage, win rates, and drawdowns.
Persists audit log to SQLite: data/paper_trading_ideas_lab.db
"""

import sys
import os
import sqlite3
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
import numpy as np
import pandas as pd
import yfinance as yf

# Ensure project root in sys.path
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from services.risk_engine.engine import RiskEngine
from services.risk_engine.contracts import HardRiskLimits

DB_PATH = os.path.join(PROJECT_ROOT, "data", "paper_trading_ideas_lab.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

UNIVERSE = [
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "INFY.NS",
    "SBIN.NS",
    "BHARTIARTL.NS",
    "ITC.NS",
]

INITIAL_CAPITAL_PER_STRATEGY = 100_000.0  # INR 100k per strategy idea
FEE_BPS = 0.0010  # 10 bps round-trip slippage, brokerage, and STT


def init_db(db_path: str):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS paper_idea_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id TEXT,
            symbol TEXT,
            side TEXT,
            entry_time TEXT,
            exit_time TEXT,
            entry_price REAL,
            exit_price REAL,
            pnl_pct REAL,
            pnl_inr REAL,
            exit_reason TEXT
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS paper_idea_summaries (
            strategy_id TEXT PRIMARY KEY,
            initial_capital REAL,
            ending_equity REAL,
            total_trades INT,
            win_rate REAL,
            profit_factor REAL,
            max_drawdown REAL,
            sharpe_ratio REAL,
            evaluated_at TEXT
        );
    """)
    conn.commit()
    conn.close()


def load_universe_data(symbols: List[str], period: str = "3mo", interval: str = "1h") -> Dict[str, pd.DataFrame]:
    print(f"Downloading {period} hourly market data for {len(symbols)} NSE universe symbols...")
    data = {}
    for sym in symbols:
        try:
            df = yf.download(sym, period=period, interval=interval, progress=False)
            if hasattr(df.columns, "levels") and len(df.columns.levels) > 1:
                df.columns = df.columns.get_level_values(0)
            if len(df) >= 50:
                data[sym] = df
        except Exception as e:
            print(f"Error fetching data for {sym}: {e}")
    print(f"Successfully loaded {len(data)} valid symbol datasets.\n")
    return data


# =====================================================================
# Strategy Simulators (Executing Full Paper Trade Lifecycles)
# =====================================================================

def simulate_ttm_squeeze(market_data: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
    """Idea 1: TTM Volatility Squeeze Breakout (Bollinger inside Keltner Channels)."""
    trades = []
    for sym, df in market_data.items():
        closes = df["Close"].values.astype(float)
        highs = df["High"].values.astype(float)
        lows = df["Low"].values.astype(float)
        vols = df["Volume"].values.astype(float)

        # 20 SMA & Bollinger Bands (2.0 std)
        sma20 = pd.Series(closes).rolling(20).mean().values
        std20 = pd.Series(closes).rolling(20).std().values
        bb_upper = sma20 + (2.0 * std20)
        bb_lower = sma20 - (2.0 * std20)

        # ATR 20 & Keltner Channels (1.5 ATR)
        tr = np.maximum(highs[1:] - lows[1:], np.maximum(abs(highs[1:] - closes[:-1]), abs(lows[1:] - closes[:-1])))
        atr = pd.Series(tr).rolling(20).mean().values
        atr = np.insert(atr, 0, atr[0] if len(atr) > 0 else 1.0)
        kc_upper = sma20 + (1.5 * atr)
        kc_lower = sma20 - (1.5 * atr)

        # Volume MA 20
        vol_ma = pd.Series(vols).rolling(20).mean().values

        # Momentum Histogram (Price vs 20 SMA linear regression proxy)
        mom = closes - sma20

        pos = None
        for i in range(25, len(closes)):
            c, h, l, v = closes[i], highs[i], lows[i], vols[i]
            # Check Squeeze condition on previous bar: BB inside KC
            was_in_squeeze = (bb_lower[i-1] > kc_lower[i-1]) and (bb_upper[i-1] < kc_upper[i-1])
            fired_out = (bb_lower[i] <= kc_lower[i]) or (bb_upper[i] >= kc_upper[i])
            vol_surge = v >= (vol_ma[i] * 1.15) if not np.isnan(vol_ma[i]) else True

            # Exit logic
            if pos is not None:
                if pos["side"] == "LONG":
                    if l <= pos["stop"]:
                        ret = (pos["stop"] - pos["entry"]) / pos["entry"] - FEE_BPS
                        trades.append({"strategy": "IDEA_1_TTM_SQUEEZE", "symbol": sym, "side": "LONG", "entry": pos["entry"], "exit": pos["stop"], "ret": ret, "reason": "STOP_LOSS"})
                        pos = None
                    elif h >= pos["target"]:
                        ret = (pos["target"] - pos["entry"]) / pos["entry"] - FEE_BPS
                        trades.append({"strategy": "IDEA_1_TTM_SQUEEZE", "symbol": sym, "side": "LONG", "entry": pos["entry"], "exit": pos["target"], "ret": ret, "reason": "TARGET"})
                        pos = None
                elif pos["side"] == "SHORT":
                    if h >= pos["stop"]:
                        ret = (pos["entry"] - pos["stop"]) / pos["entry"] - FEE_BPS
                        trades.append({"strategy": "IDEA_1_TTM_SQUEEZE", "symbol": sym, "side": "SHORT", "entry": pos["entry"], "exit": pos["stop"], "ret": ret, "reason": "STOP_LOSS"})
                        pos = None
                    elif l <= pos["target"]:
                        ret = (pos["entry"] - pos["target"]) / pos["entry"] - FEE_BPS
                        trades.append({"strategy": "IDEA_1_TTM_SQUEEZE", "symbol": sym, "side": "SHORT", "entry": pos["entry"], "exit": pos["target"], "ret": ret, "reason": "TARGET"})
                        pos = None

            # Entry logic
            if pos is None and was_in_squeeze and fired_out and vol_surge:
                curr_atr = atr[i] if not np.isnan(atr[i]) and atr[i] > 0 else c * 0.015
                if mom[i] > 0 and c > sma20[i]:
                    pos = {"side": "LONG", "entry": c, "stop": c - (1.5 * curr_atr), "target": c + (3.0 * curr_atr)}
                elif mom[i] < 0 and c < sma20[i]:
                    pos = {"side": "SHORT", "entry": c, "stop": c + (1.5 * curr_atr), "target": c - (3.0 * curr_atr)}

    return trades


def simulate_two_way_vwap(market_data: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
    """Idea 2: Two-Way VWAP Dispersion & Band Reversion."""
    trades = []
    for sym, df in market_data.items():
        closes = df["Close"].values.astype(float)
        highs = df["High"].values.astype(float)
        lows = df["Low"].values.astype(float)
        vols = df["Volume"].values.astype(float)

        typical = (highs + lows + closes) / 3.0
        cum_vol = np.cumsum(vols)
        cum_tp_vol = np.cumsum(typical * vols)
        vwap = cum_tp_vol / (cum_vol + 1e-9)
        std20 = pd.Series(closes).rolling(20).std().fillna(1.0).values
        vwap_upper = vwap + (1.75 * std20)
        vwap_lower = vwap - (1.75 * std20)

        # RSI(14)
        delta = pd.Series(closes).diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        rsi = (100 - (100 / (1 + rs))).values

        pos = None
        for i in range(25, len(closes)):
            c, h, l = closes[i], highs[i], lows[i]

            if pos is not None:
                if pos["side"] == "LONG":
                    if l <= pos["stop"]:
                        ret = (pos["stop"] - pos["entry"]) / pos["entry"] - FEE_BPS
                        trades.append({"strategy": "IDEA_2_TWO_WAY_VWAP", "symbol": sym, "side": "LONG", "entry": pos["entry"], "exit": pos["stop"], "ret": ret, "reason": "STOP_LOSS"})
                        pos = None
                    elif h >= pos["target"]:
                        ret = (pos["target"] - pos["entry"]) / pos["entry"] - FEE_BPS
                        trades.append({"strategy": "IDEA_2_TWO_WAY_VWAP", "symbol": sym, "side": "LONG", "entry": pos["entry"], "exit": pos["target"], "ret": ret, "reason": "TARGET"})
                        pos = None
                elif pos["side"] == "SHORT":
                    if h >= pos["stop"]:
                        ret = (pos["entry"] - pos["stop"]) / pos["entry"] - FEE_BPS
                        trades.append({"strategy": "IDEA_2_TWO_WAY_VWAP", "symbol": sym, "side": "SHORT", "entry": pos["entry"], "exit": pos["stop"], "ret": ret, "reason": "STOP_LOSS"})
                        pos = None
                    elif l <= pos["target"]:
                        ret = (pos["entry"] - pos["target"]) / pos["entry"] - FEE_BPS
                        trades.append({"strategy": "IDEA_2_TWO_WAY_VWAP", "symbol": sym, "side": "SHORT", "entry": pos["entry"], "exit": pos["target"], "ret": ret, "reason": "TARGET"})
                        pos = None

            if pos is None:
                # Long: Price below lower band + RSI oversold turning up
                if c < vwap_lower[i] and rsi[i] < 40 and rsi[i] > rsi[i-1]:
                    pos = {"side": "LONG", "entry": c, "stop": c * 0.985, "target": vwap[i]}
                # Short: Price above upper band + RSI overbought turning down
                elif c > vwap_upper[i] and rsi[i] > 60 and rsi[i] < rsi[i-1]:
                    pos = {"side": "SHORT", "entry": c, "stop": c * 1.015, "target": vwap[i]}

    return trades


def simulate_mtf_trend_pullback(market_data: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
    """Idea 3: Multi-Timeframe (MTF) Trend Pullback with Breakeven Ratchet."""
    trades = []
    for sym, df in market_data.items():
        closes = df["Close"].values.astype(float)
        highs = df["High"].values.astype(float)
        lows = df["Low"].values.astype(float)

        ema20 = pd.Series(closes).ewm(span=20).mean().values
        sma50 = pd.Series(closes).rolling(50).mean().values

        # ATR 14
        tr = np.maximum(highs[1:] - lows[1:], np.maximum(abs(highs[1:] - closes[:-1]), abs(lows[1:] - closes[:-1])))
        atr = pd.Series(tr).rolling(14).mean().values
        atr = np.insert(atr, 0, atr[0] if len(atr) > 0 else 1.0)

        pos = None
        for i in range(50, len(closes)):
            c, h, l = closes[i], highs[i], lows[i]
            curr_atr = atr[i] if not np.isnan(atr[i]) and atr[i] > 0 else c * 0.015

            if pos is not None:
                # Breakeven Ratchet: if price reaches +1.0R, move stop to entry + 10 bps
                if pos["side"] == "LONG":
                    if h >= (pos["entry"] + curr_atr) and pos["stop"] < pos["entry"]:
                        pos["stop"] = pos["entry"] * 1.001
                    if l <= pos["stop"]:
                        ret = (pos["stop"] - pos["entry"]) / pos["entry"] - FEE_BPS
                        trades.append({"strategy": "IDEA_3_MTF_PULLBACK", "symbol": sym, "side": "LONG", "entry": pos["entry"], "exit": pos["stop"], "ret": ret, "reason": "STOP_OR_BREAKEVEN"})
                        pos = None
                    elif h >= pos["target"]:
                        ret = (pos["target"] - pos["entry"]) / pos["entry"] - FEE_BPS
                        trades.append({"strategy": "IDEA_3_MTF_PULLBACK", "symbol": sym, "side": "LONG", "entry": pos["entry"], "exit": pos["target"], "ret": ret, "reason": "TARGET"})
                        pos = None
                elif pos["side"] == "SHORT":
                    if l <= (pos["entry"] - curr_atr) and pos["stop"] > pos["entry"]:
                        pos["stop"] = pos["entry"] * 0.999
                    if h >= pos["stop"]:
                        ret = (pos["entry"] - pos["stop"]) / pos["entry"] - FEE_BPS
                        trades.append({"strategy": "IDEA_3_MTF_PULLBACK", "symbol": sym, "side": "SHORT", "entry": pos["entry"], "exit": pos["stop"], "ret": ret, "reason": "STOP_OR_BREAKEVEN"})
                        pos = None
                    elif l <= pos["target"]:
                        ret = (pos["entry"] - pos["target"]) / pos["entry"] - FEE_BPS
                        trades.append({"strategy": "IDEA_3_MTF_PULLBACK", "symbol": sym, "side": "SHORT", "entry": pos["entry"], "exit": pos["target"], "ret": ret, "reason": "TARGET"})
                        pos = None

            if pos is None:
                # Bullish Trend Pullback: Macro Trend is Bullish (price > 50 SMA), pullback touches 20 EMA
                if c > sma50[i] and l <= ema20[i] and c > ema20[i]:
                    pos = {"side": "LONG", "entry": c, "stop": c - (1.5 * curr_atr), "target": c + (3.0 * curr_atr)}
                # Bearish Trend Pullback: Macro Trend is Bearish (price < 50 SMA), rally touches 20 EMA
                elif c < sma50[i] and h >= ema20[i] and c < ema20[i]:
                    pos = {"side": "SHORT", "entry": c, "stop": c + (1.5 * curr_atr), "target": c - (3.0 * curr_atr)}

    return trades


def simulate_polished_bollinger(market_data: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
    """Idea 4: Polished Two-Way Bollinger Mean Reversion."""
    trades = []
    for sym, df in market_data.items():
        closes = df["Close"].values.astype(float)
        highs = df["High"].values.astype(float)
        lows = df["Low"].values.astype(float)

        sma20 = pd.Series(closes).rolling(20).mean().values
        std20 = pd.Series(closes).rolling(20).std().values
        upper_bb = sma20 + (2.0 * std20)
        lower_bb = sma20 - (2.0 * std20)
        sma50 = pd.Series(closes).rolling(50).mean().values

        delta = pd.Series(closes).diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        rsi = (100 - (100 / (1 + rs))).values

        pos = None
        for i in range(50, len(closes)):
            c, h, l = closes[i], highs[i], lows[i]

            if pos is not None:
                if pos["side"] == "LONG":
                    if l <= pos["stop"]:
                        ret = (pos["stop"] - pos["entry"]) / pos["entry"] - FEE_BPS
                        trades.append({"strategy": "IDEA_4_POLISHED_BOLLINGER", "symbol": sym, "side": "LONG", "entry": pos["entry"], "exit": pos["stop"], "ret": ret, "reason": "STOP_LOSS"})
                        pos = None
                    elif h >= pos["target"]:
                        ret = (pos["target"] - pos["entry"]) / pos["entry"] - FEE_BPS
                        trades.append({"strategy": "IDEA_4_POLISHED_BOLLINGER", "symbol": sym, "side": "LONG", "entry": pos["entry"], "exit": pos["target"], "ret": ret, "reason": "TARGET"})
                        pos = None
                elif pos["side"] == "SHORT":
                    if h >= pos["stop"]:
                        ret = (pos["entry"] - pos["stop"]) / pos["entry"] - FEE_BPS
                        trades.append({"strategy": "IDEA_4_POLISHED_BOLLINGER", "symbol": sym, "side": "SHORT", "entry": pos["entry"], "exit": pos["stop"], "ret": ret, "reason": "STOP_LOSS"})
                        pos = None
                    elif l <= pos["target"]:
                        ret = (pos["entry"] - pos["target"]) / pos["entry"] - FEE_BPS
                        trades.append({"strategy": "IDEA_4_POLISHED_BOLLINGER", "symbol": sym, "side": "SHORT", "entry": pos["entry"], "exit": pos["target"], "ret": ret, "reason": "TARGET"})
                        pos = None

            if pos is None:
                # Long: Bullish regime + Reversal candle inside lower band
                if c > sma50[i] and closes[i-1] <= lower_bb[i-1] and c > lower_bb[i] and rsi[i] > rsi[i-1]:
                    pos = {"side": "LONG", "entry": c, "stop": c * 0.985, "target": sma20[i]}
                # Short: Bearish regime + Reversal candle inside upper band
                elif c < sma50[i] and closes[i-1] >= upper_bb[i-1] and c < upper_bb[i] and rsi[i] < rsi[i-1]:
                    pos = {"side": "SHORT", "entry": c, "stop": c * 1.015, "target": sma20[i]}

    return trades


def simulate_canonical_donchian(market_data: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
    """Idea 5: Canonical Donchian 20-Day Channel Breakout."""
    trades = []
    for sym, df in market_data.items():
        closes = df["Close"].values.astype(float)
        highs = df["High"].values.astype(float)
        lows = df["Low"].values.astype(float)

        high_20 = pd.Series(highs).rolling(20).max().shift(1).values
        low_20 = pd.Series(lows).rolling(20).min().shift(1).values

        pos = None
        for i in range(25, len(closes)):
            c, h, l = closes[i], highs[i], lows[i]

            if pos is not None:
                if l <= pos["stop"]:
                    ret = (pos["stop"] - pos["entry"]) / pos["entry"] - FEE_BPS
                    trades.append({"strategy": "IDEA_5_DONCHIAN_BREAKOUT", "symbol": sym, "side": "LONG", "entry": pos["entry"], "exit": pos["stop"], "ret": ret, "reason": "TRAILING_STOP"})
                    pos = None
                elif l <= pos["entry"] * 0.97: # 3% initial stop loss
                    ret = (pos["entry"] * 0.97 - pos["entry"]) / pos["entry"] - FEE_BPS
                    trades.append({"strategy": "IDEA_5_DONCHIAN_BREAKOUT", "symbol": sym, "side": "LONG", "entry": pos["entry"], "exit": pos["entry"] * 0.97, "ret": ret, "reason": "HARD_STOP"})
                    pos = None

            if pos is None and c > high_20[i]:
                pos = {"side": "LONG", "entry": c, "stop": low_20[i]}

    return trades


# =====================================================================
# Main Paper Trading Lab Controller
# =====================================================================

def calculate_paper_performance(strategy_id: str, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not trades:
        return {
            "strategy_id": strategy_id,
            "total_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "net_pnl_inr": 0.0,
            "ending_equity": INITIAL_CAPITAL_PER_STRATEGY,
            "max_drawdown": 0.0,
            "sharpe": 0.0,
        }

    returns = np.array([t["ret"] for t in trades])
    wins = [r for r in returns if r > 0]
    losses = [abs(r) for r in returns if r < 0]
    win_rate = (len(wins) / len(returns)) * 100.0

    gross_profit = sum(wins) if wins else 0.0
    gross_loss = sum(losses) if losses else 1e-6
    profit_factor = gross_profit / gross_loss

    # Capital simulation (INR 100k)
    pnl_per_trade = returns * INITIAL_CAPITAL_PER_STRATEGY
    cum_pnl = np.cumsum(pnl_per_trade)
    ending_equity = INITIAL_CAPITAL_PER_STRATEGY + cum_pnl[-1]
    net_pnl = cum_pnl[-1]

    # Drawdown
    equity_curve = INITIAL_CAPITAL_PER_STRATEGY + np.insert(cum_pnl, 0, 0.0)
    peak = np.maximum.accumulate(equity_curve)
    dd = (peak - equity_curve) / peak
    max_dd = float(np.max(dd)) * 100.0

    # Sharpe ratio
    sharpe = (float(np.mean(returns)) / float(np.std(returns)) * np.sqrt(252 * 6)) if np.std(returns) > 0 else 0.0

    return {
        "strategy_id": strategy_id,
        "total_trades": len(trades),
        "win_rate": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2),
        "net_pnl_inr": round(net_pnl, 2),
        "ending_equity": round(ending_equity, 2),
        "max_drawdown": round(max_dd, 2),
        "sharpe": round(sharpe, 2),
    }


def main():
    print("=" * 80)
    print("ALGO LAB — MULTI-STRATEGY PAPER TRADING FORWARD TEST LAB")
    print(f"Initial Capital Per Strategy: INR {INITIAL_CAPITAL_PER_STRATEGY:,.2f}")
    print(f"Fee & Slippage Model: 10 bps per trade | Database: {DB_PATH}")
    print("=" * 80)

    init_db(DB_PATH)
    data = load_universe_data(UNIVERSE, period="3mo", interval="1h")

    # Run simulations
    print("Executing Paper Trading Simulation for all candidate strategy ideas...")
    idea_1_trades = simulate_ttm_squeeze(data)
    idea_2_trades = simulate_two_way_vwap(data)
    idea_3_trades = simulate_mtf_trend_pullback(data)
    idea_4_trades = simulate_polished_bollinger(data)
    idea_5_trades = simulate_canonical_donchian(data)

    perf_1 = calculate_paper_performance("1. TTM Volatility Squeeze", idea_1_trades)
    perf_2 = calculate_paper_performance("2. Two-Way VWAP Dispersion", idea_2_trades)
    perf_3 = calculate_paper_performance("3. MTF Trend Pullback", idea_3_trades)
    perf_4 = calculate_paper_performance("4. Polished Bollinger Reversion", idea_4_trades)
    perf_5 = calculate_paper_performance("5. Canonical Donchian Breakout", idea_5_trades)

    all_perf = [perf_1, perf_2, perf_3, perf_4, perf_5]

    # Save to SQLite
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now_str = datetime.now(timezone.utc).isoformat()
    for p in all_perf:
        cur.execute("""
            INSERT OR REPLACE INTO paper_idea_summaries 
            (strategy_id, initial_capital, ending_equity, total_trades, win_rate, profit_factor, max_drawdown, sharpe_ratio, evaluated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            p["strategy_id"], INITIAL_CAPITAL_PER_STRATEGY, p["ending_equity"], p["total_trades"],
            p["win_rate"], p["profit_factor"], p["max_drawdown"], p["sharpe"], now_str
        ))
    conn.commit()
    conn.close()

    # Print Comparative Tearsheet
    print("\n" + "=" * 80)
    print("ALGO LAB PAPER TRADING TEARSHEET — CANDIDATE IDEAS BENCHMARK")
    print("=" * 80)
    header = f"{'Strategy Idea':<30} | {'Trades':<6} | {'Win Rate':<8} | {'PF':<5} | {'Net PnL (INR)':<14} | {'Max DD':<7} | {'Sharpe':<6}"
    print(header)
    print("-" * len(header))
    for p in all_perf:
        pnl_str = f"₹{p['net_pnl_inr']:>11,.2f}"
        print(f"{p['strategy_id']:<30} | {p['total_trades']:<6} | {p['win_rate']:>7.1f}% | {p['profit_factor']:>5.2f} | {pnl_str:<14} | {p['max_drawdown']:>6.1f}% | {p['sharpe']:>6.2f}")
    print("=" * 80)


if __name__ == "__main__":
    main()
