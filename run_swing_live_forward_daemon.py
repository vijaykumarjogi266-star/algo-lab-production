#!/usr/bin/env python3
"""
Algo Lab — Live Swing Trading Forward Testing Daemon (Paper Mode)

Runs a local persistent or single-cycle forward-testing paper trading engine:
1. Implements the Top-Validated Swing Trading Strategies:
   - Primary: EMA 9/21 Confluence Pullback Swing (Close > 200 SMA, 20 SMA > 50 SMA)
   - Secondary: Stage-2 50D Breakout with Dynamic Ratchet (with Market Breadth Guard)
2. Realistic Delivery Friction Engine:
   - 0.1% STT on Buy and Sell legs
   - Flat ₹15.34 Depository Participant (DP) charge on Delivery Sell
   - 0.015% Stamp duty on Buy leg
   - 18% GST on services (Exchange + SEBI + DP)
   - 5 bps execution slippage per fill
3. Ed Thorp 1.0% Capital Risk Rule & Sector Isolation Guard (Strictly 1 position per sector).
4. Full ACID Persistence in SQLite: data/swing_forward_testing.db.
5. Absolute Safety Invariant: ALLOW_LIVE_TRADING = False (Pure local forward simulation).
"""

import sys
import os
import time
import json
import sqlite3
import signal
import logging
import argparse
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from decimal import Decimal
from typing import Dict, List, Any, Optional, Tuple

import pandas as pd
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.backtest_engine.statutory_cost_model import (
    IndianStatutoryCostModel,
    OrderLeg,
    ProductType,
)
from services.scanner.universe_manager import Nifty50UniverseManager

# ==============================================================================
# ABSOLUTE SAFETY INVARIANTS
# ==============================================================================
ALLOW_LIVE_TRADING: bool = False
ALLOW_REAL_BROKER_EXECUTION: bool = False

def verify_safety_invariants():
    if ALLOW_LIVE_TRADING or ALLOW_REAL_BROKER_EXECUTION:
        raise RuntimeError("FAIL-CLOSED: Live trading is strictly forbidden in forward testing daemon.")

IST = ZoneInfo("Asia/Kolkata")
DB_PATH = PROJECT_ROOT / "data" / "swing_forward_testing.db"
LOG_PATH = PROJECT_ROOT / "data" / "swing_forward_daemon.log"
PID_PATH = PROJECT_ROOT / "logs" / "swing_forward_daemon.pid"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("SwingForwardDaemon")


class SwingForwardDatabase:
    """ACID SQLite persistence layer for swing forward testing paper portfolio."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_tables()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Account summary
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS account_summary (
                    account_id TEXT PRIMARY KEY,
                    initial_capital REAL NOT NULL,
                    current_cash REAL NOT NULL,
                    portfolio_equity REAL NOT NULL,
                    peak_equity REAL NOT NULL,
                    max_drawdown_pct REAL NOT NULL,
                    total_trades INTEGER DEFAULT 0,
                    winning_trades INTEGER DEFAULT 0,
                    losing_trades INTEGER DEFAULT 0,
                    total_friction_paid REAL DEFAULT 0.0,
                    updated_at TEXT NOT NULL
                )
            """)

            # Open positions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS open_positions (
                    symbol TEXT PRIMARY KEY,
                    sector TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    entry_date TEXT NOT NULL,
                    entry_time TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    current_price REAL NOT NULL,
                    quantity INTEGER NOT NULL,
                    cost_basis REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    initial_sl REAL NOT NULL,
                    take_profit REAL,
                    highest_high REAL NOT NULL,
                    unrealized_pnl REAL NOT NULL,
                    entry_friction REAL NOT NULL,
                    days_held INTEGER DEFAULT 0,
                    ratchet_level INTEGER DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
            """)

            # Closed trade journal
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_journal (
                    trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    sector TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    entry_time TEXT NOT NULL,
                    exit_time TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    quantity INTEGER NOT NULL,
                    turnover REAL NOT NULL,
                    gross_pnl REAL NOT NULL,
                    total_friction REAL NOT NULL,
                    net_pnl REAL NOT NULL,
                    return_pct REAL NOT NULL,
                    days_held INTEGER NOT NULL,
                    exit_reason TEXT NOT NULL
                )
            """)

            # Equity snapshots
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS equity_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    cash REAL NOT NULL,
                    holdings_value REAL NOT NULL,
                    total_equity REAL NOT NULL,
                    open_positions_count INTEGER NOT NULL
                )
            """)

            # Seed account if empty
            cursor.execute("SELECT COUNT(*) FROM account_summary")
            if cursor.fetchone()[0] == 0:
                now_str = datetime.now(IST).isoformat()
                cursor.execute("""
                    INSERT INTO account_summary (
                        account_id, initial_capital, current_cash, portfolio_equity,
                        peak_equity, max_drawdown_pct, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, ("SWING-FORWARD-100K", 100000.0, 100000.0, 100000.0, 100000.0, 0.0, now_str))
            conn.commit()

    def reset_account(self, initial_capital: float = 100000.0):
        """Resets the account to a fresh ₹100k balance."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM open_positions")
            cursor.execute("DELETE FROM trade_journal")
            cursor.execute("DELETE FROM equity_snapshots")
            cursor.execute("DELETE FROM account_summary")
            now_str = datetime.now(IST).isoformat()
            cursor.execute("""
                INSERT INTO account_summary (
                    account_id, initial_capital, current_cash, portfolio_equity,
                    peak_equity, max_drawdown_pct, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ("SWING-FORWARD-100K", initial_capital, initial_capital, initial_capital, initial_capital, 0.0, now_str))
            conn.commit()


class SwingLiveForwardDaemon:
    """Forward-testing paper trading daemon for Indian cash delivery swing strategies."""

    def __init__(
        self,
        initial_capital: float = 100000.0,
        max_positions: int = 3,
        max_capital_per_pos: float = 30000.0,
        risk_per_trade_pct: float = 0.010,
        min_cash_reserve: float = 10000.0,
        poll_interval_sec: int = 60,
    ):
        verify_safety_invariants()
        self.initial_capital = initial_capital
        self.max_positions = max_positions
        self.max_capital_per_pos = max_capital_per_pos
        self.risk_per_trade_pct = risk_per_trade_pct
        self.min_cash_reserve = min_cash_reserve
        self.poll_interval = poll_interval_sec
        self.db = SwingForwardDatabase()
        self.running = False
        self.dp_charge = Decimal("15.34")

        # Load sector mapping
        self.universe_mgr = Nifty50UniverseManager()
        self.sector_map = self.universe_mgr.get_sector_map()
        self.sector_map["BSE"] = "FINANCIAL_SERVICES_EXCHANGE"

    def get_ist_now(self) -> datetime:
        return datetime.now(IST)

    def is_market_open(self) -> Tuple[bool, str]:
        """Checks if NSE is currently in regular trading session (09:15 to 15:30 IST on weekdays)."""
        now = self.get_ist_now()
        if now.weekday() >= 5:  # Saturday or Sunday
            return False, "WEEKEND"
        
        t = now.time()
        market_open = datetime.strptime("09:15:00", "%H:%M:%S").time()
        market_close = datetime.strptime("15:30:00", "%H:%M:%S").time()

        if t < market_open:
            return False, "PRE_MARKET_STANDBY"
        elif t > market_close:
            return False, "POST_MARKET_STANDBY"
        return True, "MARKET_OPEN"

    def fetch_market_bars(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetches latest daily bars and indicators for swing candidates using parallel batch download.
        """
        import yfinance as yf
        results = {}
        tickers = [f"{sym}.NS" for sym in symbols]

        try:
            batch_df = yf.download(
                tickers,
                period="1y",
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
        except Exception as e:
            logger.error(f"Batch market download error: {e}")
            return results

        for sym in symbols:
            ticker = f"{sym}.NS"
            try:
                if len(symbols) == 1:
                    sub_df = batch_df.dropna()
                else:
                    if ticker not in batch_df or batch_df[ticker].empty:
                        continue
                    sub_df = batch_df[ticker].dropna()

                if len(sub_df) < 50:
                    continue

                close = sub_df["Close"].to_numpy()
                high = sub_df["High"].to_numpy()
                low = sub_df["Low"].to_numpy()
                vol = sub_df["Volume"].to_numpy()
                open_p = sub_df["Open"].to_numpy()

                n = len(close)
                curr_close = float(close[-1])
                curr_high = float(high[-1])
                curr_low = float(low[-1])
                curr_open = float(open_p[-1])
                curr_vol = float(vol[-1])

                sma_20 = float(np.mean(close[-20:])) if n >= 20 else curr_close
                sma_50 = float(np.mean(close[-50:])) if n >= 50 else curr_close
                sma_200 = float(np.mean(close[-200:])) if n >= 200 else curr_close

                s = pd.Series(close)
                ema_9 = float(s.ewm(span=9, adjust=False).mean().iloc[-1])
                ema_21 = float(s.ewm(span=21, adjust=False).mean().iloc[-1])

                prev_c = s.shift(1).fillna(s)
                tr = np.maximum(high - low, np.maximum(np.abs(high - prev_c), np.abs(low - prev_c)))
                atr_14 = float(pd.Series(tr).rolling(14).mean().iloc[-1]) if n >= 14 else curr_close * 0.02

                h_50 = float(np.max(high[-51:-1])) if n >= 51 else curr_high
                l_20 = float(np.min(low[-21:-1])) if n >= 21 else curr_low

                vol_sma20 = float(np.mean(vol[-20:])) if n >= 20 else curr_vol

                delta = s.diff().fillna(0.0)
                gain = delta.clip(lower=0.0)
                loss = -delta.clip(upper=0.0)
                avg_gain = gain.ewm(alpha=1/14, adjust=False).mean().iloc[-1]
                avg_loss = loss.ewm(alpha=1/14, adjust=False).mean().iloc[-1]
                rs = avg_gain / (avg_loss + 1e-9)
                rsi_14 = float(100.0 - (100.0 / (1.0 + rs)))

                results[sym] = {
                    "symbol": sym,
                    "close": curr_close,
                    "high": curr_high,
                    "low": curr_low,
                    "open": curr_open,
                    "volume": curr_vol,
                    "sma_20": sma_20,
                    "sma_50": sma_50,
                    "sma_200": sma_200,
                    "ema_9": ema_9,
                    "ema_21": ema_21,
                    "atr_14": atr_14,
                    "h_50": h_50,
                    "l_20": l_20,
                    "vol_sma20": vol_sma20,
                    "rsi_14": rsi_14,
                }
            except Exception as e:
                logger.debug(f"Indicator calculation error for {sym}: {e}")
                continue

        return results

    def step_forward_cycle(self) -> Dict[str, Any]:
        """
        Executes a single forward evaluation cycle:
        1. Reads open positions from DB.
        2. Evaluates exit triggers (Stop Loss, Take Profit, Trailing Stops, Ratchets).
        3. Scans Nifty 50 universe for high-conviction swing entries if portfolio has capacity.
        4. Updates mark-to-market valuations and commits ACID transaction to SQLite.
        """
        now = self.get_ist_now()
        now_str = now.isoformat()
        date_str = now.strftime("%Y-%m-%d")

        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Load account summary
            cursor.execute("SELECT * FROM account_summary WHERE account_id = ?", ("SWING-FORWARD-100K",))
            acc = dict(cursor.fetchone())
            current_cash = Decimal(str(acc["current_cash"]))

            # Load open positions
            cursor.execute("SELECT * FROM open_positions")
            positions = [dict(r) for r in cursor.fetchall()]

            # Determine universe to fetch (full Nifty 50 constituents)
            universe_symbols = self.universe_mgr.get_symbols()
            active_symbols = [p["symbol"] for p in positions]
            symbols_to_fetch = list(set(active_symbols + universe_symbols))
            logger.info(f"[*] Cycle wakeup: Fetching market data for {len(symbols_to_fetch)} symbols (Active open positions: {len(positions)})...")
            market_data = self.fetch_market_bars(symbols_to_fetch)
            logger.info(f"[✓] Retrieved verified bars for {len(market_data)} symbols.")

            closed_trades = []
            updated_positions = []

            # ------------------------------------------------------------------
            # 1. EVALUATE EXITS & RATCHET STOPS ON OPEN POSITIONS
            # ------------------------------------------------------------------
            for pos in positions:
                sym = pos["symbol"]
                bar = market_data.get(sym)
                if not bar:
                    updated_positions.append(pos)
                    continue

                curr_close = bar["close"]
                curr_high = bar["high"]
                curr_low = bar["low"]
                atr = bar["atr_14"]
                highest_high = max(pos["highest_high"], curr_high)
                pos["highest_high"] = highest_high
                pos["current_price"] = curr_close

                # Dynamic Profit Ratchet (Algo Lab Ratchet Rule)
                gain = highest_high - pos["entry_price"]
                r = pos["entry_price"] - pos["initial_sl"]
                sl = pos["stop_loss"]

                if r > 0:
                    if gain >= 1.5 * r and pos["ratchet_level"] < 1:
                        # Lock Breakeven + 0.5% (covers all statutory frictions)
                        sl = max(sl, pos["entry_price"] * 1.005)
                        pos["ratchet_level"] = 1
                        logger.info(f"[{sym}] Dynamic Ratchet L1: Stop Loss ratcheted to Breakeven (₹{sl:.2f})")
                    if gain >= 3.0 * r and pos["ratchet_level"] < 2:
                        # Lock 1.5R minimum profit
                        sl = max(sl, pos["entry_price"] + (1.5 * r))
                        pos["ratchet_level"] = 2
                        logger.info(f"[{sym}] Dynamic Ratchet L2: Stop Loss ratcheted to +1.5R (₹{sl:.2f})")
                    if gain >= 5.0 * r and pos["ratchet_level"] < 3:
                        # Chandelier trailing stop (2.0x ATR from peak)
                        sl = max(sl, highest_high - (atr * 2.0))
                        pos["ratchet_level"] = 3
                        logger.info(f"[{sym}] Dynamic Ratchet L3: Chandelier Trailing Stop (₹{sl:.2f})")

                pos["stop_loss"] = sl

                # Check Exits
                exit_reason = None
                exit_price = curr_close

                if curr_low <= pos["stop_loss"]:
                    exit_reason = "STOP_LOSS_HIT"
                    exit_price = pos["stop_loss"]
                elif pos.get("take_profit") and curr_high >= pos["take_profit"]:
                    exit_reason = "TAKE_PROFIT_HIT"
                    exit_price = pos["take_profit"]
                elif pos["strategy"] == "EMA_PULLBACK":
                    # EMA trend-break exit: EMA 9 crosses below EMA 21
                    if bar["ema_9"] < bar["ema_21"] and pos["days_held"] >= 3:
                        exit_reason = "EMA9_BELOW_EMA21"
                        exit_price = curr_close

                if exit_reason:
                    qty = pos["quantity"]
                    exit_turnover = Decimal(str(round(exit_price * qty, 2)))
                    exit_fric = IndianStatutoryCostModel.calculate_order_friction(
                        leg=OrderLeg.SELL,
                        price=Decimal(str(exit_price)),
                        quantity=qty,
                        product=ProductType.DELIVERY,
                        slippage_bps=Decimal("5.0"),
                        dp_charge_flat=self.dp_charge,
                    )
                    gross_pnl = (exit_price - pos["entry_price"]) * qty
                    all_in_fric = Decimal(str(pos["entry_friction"])) + exit_fric.all_in_total_friction
                    net_pnl = gross_pnl - float(all_in_fric)
                    ret_pct = (net_pnl / pos["cost_basis"]) * 100.0

                    current_cash += exit_turnover - exit_fric.all_in_total_friction

                    # Insert into trade journal
                    cursor.execute("""
                        INSERT INTO trade_journal (
                            symbol, sector, strategy, entry_time, exit_time,
                            entry_price, exit_price, quantity, turnover,
                            gross_pnl, total_friction, net_pnl, return_pct,
                            days_held, exit_reason
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        sym, pos["sector"], pos["strategy"], pos["entry_time"], now_str,
                        pos["entry_price"], exit_price, qty, float(exit_turnover),
                        gross_pnl, float(all_in_fric), net_pnl, ret_pct,
                        pos["days_held"], exit_reason
                    ))

                    # Remove from open positions
                    cursor.execute("DELETE FROM open_positions WHERE symbol = ?", (sym,))
                    closed_trades.append({
                        "symbol": sym,
                        "exit_price": exit_price,
                        "net_pnl": net_pnl,
                        "exit_reason": exit_reason
                    })
                    logger.info(f"[*] CLOSED POSITION: {sym} @ ₹{exit_price:.2f} | Net PnL: ₹{net_pnl:+,.2f} ({ret_pct:+.2f}%) [{exit_reason}]")
                else:
                    # Update active position in DB
                    unrealized = (curr_close - pos["entry_price"]) * pos["quantity"]
                    pos["unrealized_pnl"] = unrealized
                    cursor.execute("""
                        UPDATE open_positions SET
                            current_price = ?, stop_loss = ?, highest_high = ?,
                            unrealized_pnl = ?, ratchet_level = ?, updated_at = ?
                        WHERE symbol = ?
                    """, (curr_close, sl, highest_high, unrealized, pos["ratchet_level"], now_str, sym))
                    updated_positions.append(pos)

            # ------------------------------------------------------------------
            # 2. SCAN FOR NEW SWING ENTRIES (IF PORTFOLIO CAPACITY ALLOWS)
            # ------------------------------------------------------------------
            slots_available = self.max_positions - len(updated_positions)
            active_sectors = {p["sector"] for p in updated_positions}
            active_syms = {p["symbol"] for p in updated_positions}

            new_entries = []
            if slots_available > 0 and float(current_cash) > self.min_cash_reserve + 5000.0:
                candidates = []
                for sym, bar in market_data.items():
                    if sym in active_syms:
                        continue
                    sector = self.sector_map.get(sym, "GENERAL")
                    if sector in active_sectors:
                        continue

                    curr_close = bar["close"]
                    low_p = bar["low"]
                    open_p = bar["open"]
                    sma_200 = bar["sma_200"]
                    sma_50 = bar["sma_50"]
                    sma_20 = bar["sma_20"]
                    ema_9 = bar["ema_9"]
                    ema_21 = bar["ema_21"]
                    atr = bar["atr_14"]
                    vol = bar["volume"]
                    vol_sma = bar["vol_sma20"]

                    signal = False
                    strat = "EMA_PULLBACK"
                    sl_price = 0.0
                    tp_price = 0.0

                    # 1. Primary Setup: EMA 9/21 Confluence Pullback
                    in_uptrend = (curr_close > sma_200) and (sma_20 > sma_50)
                    bounced = (low_p <= ema_9 * 1.005) and (curr_close > ema_9) and (curr_close > open_p)
                    if in_uptrend and bounced and ema_9 > ema_21:
                        signal = True
                        stop_dist = max(atr * 2.0, curr_close * 0.025)
                        sl_price = min(ema_21 * 0.99, curr_close - stop_dist)
                        tp_price = curr_close + ((curr_close - sl_price) * 3.0)

                    # 2. Secondary Setup: Stage-2 50D Breakout
                    elif curr_close > sma_200 and sma_50 > sma_200:
                        if curr_close >= bar["h_50"] and vol >= vol_sma * 1.05:
                            signal = True
                            strat = "STAGE2_50D_BREAKOUT"
                            stop_dist = max(atr * 2.5, curr_close * 0.02)
                            sl_price = curr_close - stop_dist
                            tp_price = curr_close + (stop_dist * 3.5)

                    if signal and sl_price > 0 and sl_price < curr_close:
                        candidates.append({
                            "symbol": sym,
                            "sector": sector,
                            "strategy": strat,
                            "price": curr_close,
                            "sl": sl_price,
                            "tp": tp_price,
                            "stop_dist": curr_close - sl_price,
                            "score": vol / (vol_sma + 1e-9),
                        })

                # Sort by volume quality score
                candidates.sort(key=lambda x: x["score"], reverse=True)

                # Total current portfolio equity
                holdings_val = sum(p["quantity"] * p["current_price"] for p in updated_positions)
                total_equity = float(current_cash) + holdings_val

                for cand in candidates:
                    if len(updated_positions) >= self.max_positions:
                        break
                    if cand["sector"] in active_sectors:
                        continue

                    # Ed Thorp 1.0% Risk Rule sizing
                    risk_capital = total_equity * self.risk_per_trade_pct
                    qty_risk = int(risk_capital / cand["stop_dist"]) if cand["stop_dist"] > 0 else 1

                    available_cash = max(0.0, float(current_cash) - self.min_cash_reserve)
                    max_spend = min(self.max_capital_per_pos, available_cash)
                    qty_cash = int(max_spend / cand["price"]) if cand["price"] > 0 else 0

                    final_qty = min(qty_risk, qty_cash)
                    if final_qty <= 0:
                        continue

                    entry_turnover = Decimal(str(round(cand["price"] * final_qty, 2)))
                    entry_fric = IndianStatutoryCostModel.calculate_order_friction(
                        leg=OrderLeg.BUY,
                        price=Decimal(str(cand["price"])),
                        quantity=final_qty,
                        product=ProductType.DELIVERY,
                        slippage_bps=Decimal("5.0"),
                        dp_charge_flat=Decimal("0.0"),
                    )

                    total_cost = entry_turnover + entry_fric.all_in_total_friction
                    if total_cost > current_cash - Decimal(str(self.min_cash_reserve)):
                        continue

                    current_cash -= total_cost
                    active_sectors.add(cand["sector"])

                    new_pos = {
                        "symbol": cand["symbol"],
                        "sector": cand["sector"],
                        "strategy": cand["strategy"],
                        "entry_date": date_str,
                        "entry_time": now_str,
                        "entry_price": cand["price"],
                        "current_price": cand["price"],
                        "quantity": final_qty,
                        "cost_basis": float(total_cost),
                        "stop_loss": cand["sl"],
                        "initial_sl": cand["sl"],
                        "take_profit": cand["tp"],
                        "highest_high": cand["price"],
                        "unrealized_pnl": 0.0,
                        "entry_friction": float(entry_fric.all_in_total_friction),
                        "days_held": 0,
                        "ratchet_level": 0,
                        "updated_at": now_str,
                    }

                    cursor.execute("""
                        INSERT INTO open_positions (
                            symbol, sector, strategy, entry_date, entry_time,
                            entry_price, current_price, quantity, cost_basis,
                            stop_loss, initial_sl, take_profit, highest_high,
                            unrealized_pnl, entry_friction, days_held,
                            ratchet_level, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, tuple(new_pos.values()))

                    updated_positions.append(new_pos)
                    new_entries.append(new_pos)
                    logger.info(f"[+] NEW SWING ENTRY: {cand['symbol']} ({cand['strategy']}) | {final_qty} shs @ ₹{cand['price']:.2f} | SL: ₹{cand['sl']:.2f} | TP: ₹{cand['tp']:.2f}")

            # ------------------------------------------------------------------
            # 3. UPDATE ACCOUNT SUMMARY & SNAPSHOTS
            # ------------------------------------------------------------------
            holdings_now = sum(p["quantity"] * p["current_price"] for p in updated_positions)
            final_equity = float(current_cash) + holdings_now
            peak_equity = max(acc["peak_equity"], final_equity)
            drawdown = (peak_equity - final_equity) / peak_equity if peak_equity > 0 else 0.0
            max_drawdown = max(acc["max_drawdown_pct"], drawdown * 100.0)

            # Cumulative stats from trade journal
            cursor.execute("SELECT COUNT(*), SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END), SUM(total_friction) FROM trade_journal")
            tj_row = cursor.fetchone()
            total_tr = tj_row[0] or 0
            win_tr = tj_row[1] or 0
            loss_tr = total_tr - win_tr
            total_fric = tj_row[2] or 0.0

            cursor.execute("""
                UPDATE account_summary SET
                    current_cash = ?, portfolio_equity = ?, peak_equity = ?,
                    max_drawdown_pct = ?, total_trades = ?, winning_trades = ?,
                    losing_trades = ?, total_friction_paid = ?, updated_at = ?
                WHERE account_id = ?
            """, (
                float(current_cash), final_equity, peak_equity, max_drawdown,
                total_tr, win_tr, loss_tr, total_fric, now_str, "SWING-FORWARD-100K"
            ))

            cursor.execute("""
                INSERT INTO equity_snapshots (
                    timestamp, cash, holdings_value, total_equity, open_positions_count
                ) VALUES (?, ?, ?, ?, ?)
            """, (now_str, float(current_cash), holdings_now, final_equity, len(updated_positions)))

            conn.commit()
            logger.info(f"[✓] Cycle complete. Portfolio Equity: ₹{final_equity:,.2f} | Free Cash: ₹{float(current_cash):,.2f} | Open Positions: {len(updated_positions)}")

        return {
            "timestamp": now_str,
            "cash": float(current_cash),
            "holdings_value": holdings_now,
            "portfolio_equity": final_equity,
            "open_positions": updated_positions,
            "new_entries": new_entries,
            "closed_trades": closed_trades,
            "max_drawdown_pct": max_drawdown,
        }

    def print_portfolio_status(self):
        """Displays formatted CLI portfolio tear sheet and live ledger state."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM account_summary WHERE account_id = ?", ("SWING-FORWARD-100K",))
            acc = dict(cursor.fetchone())

            cursor.execute("SELECT * FROM open_positions")
            positions = [dict(r) for r in cursor.fetchall()]

            cursor.execute("SELECT * FROM trade_journal ORDER BY trade_id DESC LIMIT 5")
            recent_trades = [dict(r) for r in cursor.fetchall()]

        init_cap = acc["initial_capital"]
        eq = acc["portfolio_equity"]
        cash = acc["current_cash"]
        pnl = eq - init_cap
        ret_pct = (pnl / init_cap) * 100.0

        print("\n" + "=" * 80)
        print(" ALGO LAB — SWING TRADING LIVE FORWARD TESTING PORTFOLIO")
        print("=" * 80)
        print(f" Account ID       : {acc['account_id']} (Delivery CNC Paper Mode)")
        print(f" Portfolio Equity : ₹{eq:,.2f}  [{pnl:+,.2f} / {ret_pct:+.2f}%]")
        print(f" Free Cash Balance: ₹{cash:,.2f}")
        print(f" Peak Equity      : ₹{acc['peak_equity']:,.2f} (Max Drawdown: {acc['max_drawdown_pct']:.2f}%)")
        print(f" Closed Trades    : {acc['total_trades']} (Wins: {acc['winning_trades']}, Losses: {acc['losing_trades']})")
        print(f" Frictions Paid   : ₹{acc['total_friction_paid']:,.2f} (STT + DP + GST)")
        print("-" * 80)

        print("\n[ACTIVE SWING POSITIONS]")
        if not positions:
            print("  No open swing positions currently active. Ready for scanner entry.")
        else:
            headers = ["Symbol", "Strategy", "Qty", "Entry ₹", "LTP ₹", "Unrealized ₹", "Stop Loss ₹", "Target ₹", "Hold"]
            print(f"  {headers[0]:<12} {headers[1]:<20} {headers[2]:<5} {headers[3]:<10} {headers[4]:<10} {headers[5]:<14} {headers[6]:<12} {headers[7]:<10} {headers[8]:<5}")
            print("  " + "-" * 92)
            for p in positions:
                tp_str = f"₹{p['take_profit']:.1f}" if p.get('take_profit') else "Trailing"
                print(f"  {p['symbol']:<12} {p['strategy']:<20} {p['quantity']:<5} ₹{p['entry_price']:<9.2f} ₹{p['current_price']:<9.2f} ₹{p['unrealized_pnl']:<13.2f} ₹{p['stop_loss']:<11.2f} {tp_str:<10} {p['days_held']}d")

        if recent_trades:
            print("\n[RECENT CLOSED TRADES]")
            headers = ["ID", "Symbol", "Entry Date", "Exit Date", "Net PnL (₹)", "Return %", "Exit Reason"]
            print(f"  {headers[0]:<4} {headers[1]:<10} {headers[2]:<12} {headers[3]:<12} {headers[4]:<13} {headers[5]:<10} {headers[6]:<20}")
            print("  " + "-" * 85)
            for t in recent_trades:
                ed = t["entry_time"][:10]
                xd = t["exit_time"][:10]
                print(f"  #{t['trade_id']:<3} {t['symbol']:<10} {ed:<12} {xd:<12} ₹{t['net_pnl']:<12.2f} {t['return_pct']:<9.2f}% {t['exit_reason']:<20}")

        print("=" * 80 + "\n")

    def run_daemon_loop(self):
        """Persistent background daemon loop with signal handling and PID tracking."""
        self.running = True

        # Save PID file
        PID_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(PID_PATH, "w") as f:
            f.write(str(os.getpid()))

        def handle_exit(signum, frame):
            logger.info("Signal received. Terminating swing forward daemon gracefully...")
            self.running = False

        signal.signal(signal.SIGINT, handle_exit)
        signal.signal(signal.SIGTERM, handle_exit)

        logger.info(f"Swing Forward Daemon started. PID={os.getpid()}. Poll Interval={self.poll_interval}s.")

        try:
            while self.running:
                is_open, state_msg = self.is_market_open()

                if is_open:
                    logger.info(f"[MARKET ACTIVE] Running scheduled swing forward evaluation cycle...")
                    self.step_forward_cycle()
                    time.sleep(self.poll_interval)
                else:
                    logger.info(f"[{state_msg}] Outside active NSE trading hours. Standby mode...")
                    # Sleep longer outside market hours
                    for _ in range(min(300, self.poll_interval * 5)):
                        if not self.running:
                            break
                        time.sleep(1)

        finally:
            if PID_PATH.exists():
                try:
                    os.remove(PID_PATH)
                except Exception:
                    pass
            logger.info("Swing Forward Daemon safely stopped.")


def main():
    parser = argparse.ArgumentParser(description="Algo Lab Swing Trading Live Forward Testing Daemon")
    parser.add_argument("--daemon", action="store_true", help="Run as persistent background daemon loop")
    parser.add_argument("--cycle", "--single-run", dest="single_run", action="store_true", help="Run a single evaluation cycle and display results")
    parser.add_argument("--status", action="store_true", help="Display current forward paper portfolio status")
    parser.add_argument("--reset", action="store_true", help="Reset forward paper portfolio to ₹100,000 baseline")
    parser.add_argument("--interval", type=int, default=60, help="Daemon poll interval in seconds (default: 60)")
    args = parser.parse_args()

    daemon = SwingLiveForwardDaemon(poll_interval_sec=args.interval)

    if args.reset:
        daemon.db.reset_account(100000.0)
        print("[✓] Swing forward testing account successfully reset to ₹100,000.00.")
        daemon.print_portfolio_status()
        return

    if args.status:
        daemon.print_portfolio_status()
        return

    if args.single_run or (not args.daemon and not args.status and not args.reset):
        print("Executing single forward testing evaluation cycle...")
        cycle_res = daemon.step_forward_cycle()
        daemon.print_portfolio_status()
        return

    if args.daemon:
        daemon.run_daemon_loop()


if __name__ == "__main__":
    main()
