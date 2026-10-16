#!/usr/bin/env python3
"""
AlgoLab Intraday Survival Engine — Live Capital, Margin & Position Inspector.
Segment: INTRADAY ONLY (MIS Equities).
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import yfinance as yf

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "intraday_ledger.db"
IST = ZoneInfo("Asia/Kolkata")


def inspect_intraday():
    if not DB_PATH.exists():
        print("No intraday ledger database found.")
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT * FROM intraday_sessions ORDER BY created_at DESC LIMIT 1;")
    session = c.fetchone()
    if not session:
        print("No active intraday session found.")
        return

    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    base_cap = session["base_capital"]
    leverage = session["leverage"]
    total_buying_power = session["buying_power"]
    cash_buying_power = session["cash"]
    realized_pnl = session["realized_pnl"]
    fees_paid = session["fees_paid"]
    peak_margin = session["peak_margin_deployed"] or 0.0

    # Fetch live positions
    c.execute("SELECT * FROM intraday_positions WHERE session_id = ? AND status = 'OPEN';", (session["session_id"],))
    open_positions = c.fetchall()

    total_unrealized = 0.0
    active_margin_deployed = 0.0
    positions_view = []

    for p in open_positions:
        sym = p["symbol"]
        qty = p["quantity"]
        entry = p["entry_price"]
        allocated_margin = p["allocated_margin"]
        active_margin_deployed += allocated_margin

        try:
            ltp = float(yf.Ticker(f"{sym}.NS").history(period="1d")["Close"].iloc[-1])
        except Exception:
            ltp = float(p["current_price"])

        pnl = (ltp - entry) * qty
        total_unrealized += pnl
        ret_pct = ((ltp - entry) / entry) * 100
        positions_view.append({
            "symbol": sym,
            "strategy": p["strategy_phase"],
            "qty": qty,
            "entry": entry,
            "ltp": ltp,
            "sl": p["stop_loss"],
            "tp": p["target_price"],
            "margin": allocated_margin,
            "pnl": pnl,
            "ret_pct": ret_pct,
            "be_locked": bool(p["breakeven_locked"])
        })

    # Live Capital Computation
    live_free_margin = max(0.0, total_buying_power - active_margin_deployed + realized_pnl + total_unrealized)
    margin_utilization_pct = (active_margin_deployed / total_buying_power * 100) if total_buying_power > 0 else 0.0
    
    # Net equity on base capital
    total_net_day_pnl = realized_pnl + total_unrealized
    live_net_equity = base_cap + (total_net_day_pnl / leverage)
    roi_base_equity_pct = ((live_net_equity - base_cap) / base_cap) * 100

    print("=" * 78)
    print(" ⚡ ALGO LAB INTRADAY SURVIVAL ENGINE — LIVE CAPITAL & P&L DASHBOARD")
    print(f"    Timestamp: {now_ist} | Session: {session['session_id']}")
    print(f"    Status: {session['status']} | Cutoff: 15:15:00 IST (Strict MIS auto-squareoff)")
    print("=" * 78)

    print("\n💰 [LIVE ACCOUNT CAPITAL & NET WORTH]")
    print(f"  • Starting Base Capital:      ₹{base_cap:>10,.2f}")
    print(f"  • Live Account Net Equity:    ₹{live_net_equity:>10,.2f} ({roi_base_equity_pct:>+6.2f}% ROI)")
    print(f"  • Total Day Net P&L:          ₹{total_net_day_pnl:>+10,.2f}")
    print(f"    └─ Realized P&L (Settled):  ₹{realized_pnl:>+10,.2f}")
    print(f"    └─ Unrealized P&L (MTM):    ₹{total_unrealized:>+10,.2f}")
    print(f"    └─ Statutory Frictions:     ₹{fees_paid:>10,.2f}")

    print("\n🔋 [LIVE LEVERAGE & MARGIN UTILIZATION (5.0x MIS)]")
    print(f"  • Total Effective Buying Power: ₹{total_buying_power:>10,.2f}")
    print(f"  • Active Margin Deployed:       ₹{active_margin_deployed:>10,.2f} ({margin_utilization_pct:>5.1f}% Utilized)")
    print(f"  • Free Buying Power Available:  ₹{live_free_margin:>10,.2f}")
    print(f"  • Peak Margin Used Today:       ₹{peak_margin:>10,.2f} ({(peak_margin/total_buying_power*100):>5.1f}% Peak)")

    print("\n🎯 [ACTIVE OPEN INTRADAY POSITIONS]")
    if not positions_view:
        print("  0 active open positions (100% Cash Preserved / Overnight Protected).")
    else:
        print(f"  {'Symbol':<10} | {'Phase':<18} | {'Qty':>3} | {'Entry (₹)':>9} | {'LTP (₹)':>9} | {'SL (₹)':>9} | {'Margin':>10} | {'MTM P&L (₹)':>12}")
        print("  " + "-" * 90)
        for pv in positions_view:
            be_tag = " [BE]" if pv["be_locked"] else ""
            print(f"  {pv['symbol']:<10} | {pv['strategy']:<18} | {pv['qty']:>3} | ₹{pv['entry']:>8.2f} | ₹{pv['ltp']:>8.2f} | ₹{pv['sl']:>8.2f}{be_tag} | ₹{pv['margin']:>9,.2f} | ₹{pv['pnl']:>+8.2f} ({pv['ret_pct']:>+5.2f}%)")

    # Completed trades
    c.execute("SELECT * FROM intraday_trades_audit WHERE session_id = ? ORDER BY closed_at ASC;", (session["session_id"],))
    closed_trades = c.fetchall()
    print("\n📋 [COMPLETED INTRADAY TRADES TODAY]")
    if not closed_trades:
        print("  0 closed trades today.")
    else:
        for t in closed_trades:
            print(f"  • {t['symbol']:10} | {t['strategy']:<18} | Qty: {t['quantity']:>3} | Exit: ₹{t['exit_price']:>7.2f} | Net P&L: ₹{t['net_pnl']:>+7.2f} ({t['return_pct']:>+5.2f}%) | {t['exit_reason']}")

    print("=" * 78)


if __name__ == "__main__":
    inspect_intraday()
