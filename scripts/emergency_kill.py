#!/usr/bin/env python3
"""
AlgoLab Emergency Panic Button & Instant Flattener.
Segment: INTRADAY ONLY.
Bypasses all normal strategy logic, executes immediate market exit for all open positions,
commits to SQLite audit ledger, flushes cash, and guarantees 100% flat exposure.
"""

import os
import sys
import time
import sqlite3
import subprocess
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import yfinance as yf

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "intraday_ledger.db"
IST = ZoneInfo("Asia/Kolkata")


def execute_emergency_flatten():
    print("=" * 80)
    print(" 🚨 ALGO LAB EMERGENCY PANIC BUTTON ACTIVATED")
    print(f"    Timestamp: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')}")
    print("    Action: IMMEDIATE LIQUIDATION OF ALL OPEN INTRADAY POSITIONS")
    print("=" * 80)

    if not DB_PATH.exists():
        print("[ERROR] Intraday ledger database not found.")
        return

    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT * FROM intraday_sessions ORDER BY created_at DESC LIMIT 1;")
    session = c.fetchone()
    if not session:
        print("[ERROR] No active intraday session found.")
        return

    session_id = session["session_id"]
    c.execute("SELECT * FROM intraday_positions WHERE session_id = ? AND status = 'OPEN';", (session_id,))
    open_positions = c.fetchall()

    if not open_positions:
        print("✅ No open positions found. Portfolio is already 100% FLAT.")
        return

    print(f"⚠️ Found {len(open_positions)} active open position(s) to emergency liquidate:")
    now_iso = datetime.now(timezone.utc).isoformat()
    now_ist_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")

    total_recovered_margin = 0.0
    total_net_pnl = 0.0

    for pos in open_positions:
        sym = pos["symbol"]
        qty = pos["quantity"]
        entry = pos["entry_price"]
        allocated_margin = pos["allocated_margin"]

        # Fetch current price
        try:
            exit_price = float(yf.Ticker(f"{sym}.NS").history(period="1d")["Close"].iloc[-1])
        except Exception:
            exit_price = float(pos["current_price"])

        turnover = exit_price * qty
        gross_pnl = (exit_price - entry) * qty
        brokerage = min(20.0, turnover * 0.0003)
        stt = turnover * 0.00025
        friction = round(brokerage + stt + (turnover * 0.00004), 2)
        net_pnl = round(gross_pnl - friction, 2)
        ret_pct = round((net_pnl / (entry * qty)) * 100, 2)

        print(f"  🔥 Emergency Liquidating: {sym} | {qty} shs @ ₹{exit_price:.2f} | Net P&L: ₹{net_pnl:+,.2f} ({ret_pct:+.2f}%)")

        # 1. Update position status
        c.execute("""
            UPDATE intraday_positions
            SET current_price = ?, status = 'CLOSED', closed_at = ?, exit_price = ?, exit_reason = 'EMERGENCY_PANIC_BUTTON', realized_pnl = ?
            WHERE position_id = ?
        """, (exit_price, now_iso, exit_price, net_pnl, pos["position_id"]))

        # 2. Record audit trade
        c.execute("""
            INSERT INTO intraday_trades_audit
            (trade_id, session_id, symbol, side, strategy, quantity, entry_price, exit_price, gross_pnl, friction_charges, net_pnl, return_pct, exit_reason, opened_at, closed_at)
            VALUES (?, ?, ?, 'BUY', ?, ?, ?, ?, ?, ?, ?, ?, 'EMERGENCY_PANIC_BUTTON', ?, ?)
        """, (
            f"EMERG_{pos['position_id']}",
            session_id,
            sym,
            pos["strategy_phase"],
            qty,
            entry,
            exit_price,
            gross_pnl,
            friction,
            net_pnl,
            ret_pct,
            pos["opened_at"],
            now_iso
        ))

        # 3. Record transaction log
        c.execute("""
            INSERT INTO intraday_transaction_log
            (tx_id, session_id, timestamp_ist, timestamp_utc, symbol, tx_type, side, quantity, price, turnover, allocated_margin, cash_before, cash_after, buying_power_utilized_pct, gross_pnl, friction, net_pnl, notes)
            VALUES (?, ?, ?, ?, ?, 'EMERGENCY_FLATTEN', 'SELL', ?, ?, ?, 0.0, ?, ?, 0.0, ?, ?, ?, 'EMERGENCY PANIC BUTTON TRIGGERED')
        """, (
            f"TX_EMERG_{int(time.time()*1000)}_{sym}",
            session_id,
            now_ist_str,
            now_iso,
            sym,
            qty,
            exit_price,
            turnover,
            session["cash"],
            session["cash"] + allocated_margin + net_pnl,
            gross_pnl,
            friction,
            net_pnl
        ))

        total_recovered_margin += allocated_margin
        total_net_pnl += net_pnl

    # 4. Update session balance
    new_cash = session["cash"] + total_recovered_margin + total_net_pnl
    new_realized = session["realized_pnl"] + total_net_pnl
    c.execute("""
        UPDATE intraday_sessions
        SET cash = ?, realized_pnl = ?, unrealized_pnl = 0.0, updated_at = ?
        WHERE session_id = ?
    """, (new_cash, new_realized, now_iso, session_id))

    conn.commit()
    conn.close()

    print("-" * 80)
    print(f"✅ EMERGENCY FLATTEN COMPLETE. All positions closed.")
    print(f"   Recovered Margin: ₹{total_recovered_margin:,.2f}")
    print(f"   Net P&L on Liquidation: ₹{total_net_pnl:+,.2f}")
    print(f"   Updated Cash: ₹{new_cash:,.2f}")
    print("=" * 80)


if __name__ == "__main__":
    execute_emergency_flatten()
