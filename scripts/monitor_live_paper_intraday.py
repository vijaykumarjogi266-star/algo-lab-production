#!/usr/bin/env python3
"""
Algo Lab Live Intraday Paper Trading Monitor & Manager.
Tracks active intraday paper session, queries live quotes, updates mark-to-market,
and enforces dynamic Trailing Stop / Ratchet / Target / 15:15 IST Square-off.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import zoneinfo

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import yfinance as yf
from services.paper_engine.session import PaperTradingEngine, SessionStatus
from services.paper_engine.trailing_stop_engine import TrailingStopEngine, TrailingPositionConfig, IST_TZ

DB_PATH = str(BASE_DIR / "data" / "paper_intraday_sessions.db")


def inspect_intraday_session(session_id: str = None) -> TrailingStopEngine:
    engine = PaperTradingEngine(DB_PATH)
    sessions = engine.list_sessions()
    if not sessions:
        print("[ERROR] No paper trading sessions found.")
        sys.exit(1)

    target_session = None
    if session_id:
        target_session = engine.get_session(session_id)
    else:
        target_session = sessions[0]

    if not target_session:
        print(f"[ERROR] Session {session_id} not found.")
        sys.exit(1)

    trailing_engine = TrailingStopEngine(engine, target_session.session_id)
    summary = trailing_engine.get_status_summary()

    now_ist = datetime.now(IST_TZ)
    print("=" * 95)
    print(f" 📊 ALGO LAB LIVE INTRADAY PAPER TRADING MONITOR & TRAILING STOP ENGINE")
    print(f"    Session ID:   {summary['session_id']}")
    print(f"    Session Name: {summary['session_name']} ({summary['status']})")
    print(f"    Active Time:  {now_ist.strftime('%Y-%m-%d %H:%M:%S IST')}")
    print(f"    Mandatory Intraday Square-off: 15:15:00 IST")
    print("=" * 95)

    guards = summary["guards"]
    if not guards:
        print("  No active or guarded positions in this session.")
    else:
        print(f" {'Symbol':<10} | {'Side':<4} | {'Qty':>3} | {'Entry (₹)':>10} | {'LTP (₹)':>10} | {'Stop Loss':>11} | {'Target (₹)':>10} | {'High (₹)':>10} | {'Status':<12}")
        print("-" * 95)
        for g in guards:
            status_desc = "CLOSED" if g["is_closed"] else ("BE LOCKED" if g["breakeven_locked"] else "ACTIVE")
            print(
                f" {g['symbol']:<10} | {g['side']:<4} | {g['quantity']:>3d} | "
                f"₹{g['entry_price']:>9.2f} | ₹{g['current_price']:>9.2f} | "
                f"₹{g['stop_loss']:>10.2f} | ₹{g['target_price']:>9.2f} | "
                f"₹{g['highest_watermark']:>9.2f} | {status_desc:<12}"
            )

    pf = summary["portfolio"]
    print("-" * 95)
    print(f" Available Cash:     ₹{pf['cash']:,.2f}")
    print(f" Total Mark-to-Mkt:  ₹{pf['total_equity']:,.2f}")
    print(f" Total Realized P&L: ₹{pf['total_realized_pnl']:+,.2f}")
    print(f" Total Fees Paid:    ₹{pf['total_fees_paid']:,.2f}")
    print("=" * 95 + "\n")

    return trailing_engine


def run_tick_cycle(trailing_engine: TrailingStopEngine, fetch_live: bool = True):
    """Fetches quotes and processes a tick cycle for all open positions."""
    open_guards = [g for g in trailing_engine.guards.values() if not g.is_closed]
    if not open_guards:
        print("ℹ️ All positions in this session are already closed.")
        return

    quotes = {}
    for g in open_guards:
        sym = g.symbol
        if fetch_live:
            ticker_sym = f"{sym}.NS" if not sym.endswith(".NS") else sym
            try:
                hist = yf.Ticker(ticker_sym).history(period="1d")
                ltp = float(hist["Close"].iloc[-1]) if not hist.empty else g.current_price
            except Exception:
                ltp = g.current_price
        else:
            ltp = g.current_price
        quotes[sym] = ltp

    results = trailing_engine.process_tick_batch(quotes)
    for res in results:
        sym = res["symbol"]
        status = res["status"]
        if status == "EXECUTED_EXIT":
            print(f"  🚨 [EXIT EXECUTED] {sym}: {res['exit_reason']} @ ₹{res['exit_price']} | Realized P&L: ₹{res.get('total_realized_pnl', 0):+.2f}")
        elif status == "ACTIVE_MONITORING":
            print(f"  • [TICK] {sym}: LTP=₹{res['ltp']:.2f} | Trailing SL=₹{res['stop_loss']:.2f} | High=₹{res['highest_watermark']:.2f} | Unrealized=₹{res['unrealized_pnl']:+.2f}")


def simulate_ticks_sequence(trailing_engine: TrailingStopEngine):
    """Simulates realistic sequential tick stream demonstrating ratchet, breakeven lock, and square-off."""
    print("🚀 Simulating Real-Time Tick Stream & Dynamic Ratchet Trailing Stops...")
    
    # Tick simulation steps:
    # 1. Price moves up +0.8% (ratchet begins)
    # 2. Price moves up +1.8% (breakeven triggers and locks stop at entry)
    # 3. Price peaks at +2.5% (trailing stop ratchets higher behind peak)
    # 4. Pullback touches trailing stop -> triggers automated exit!
    
    guards = list(trailing_engine.guards.values())
    if not guards:
        print("No guards found.")
        return

    for g in guards:
        if g.is_closed:
            continue
        entry = g.entry_price
        sym = g.symbol
        print(f"\n--- Testing Ratchet & Trailing Stop on {sym} (Entry: ₹{entry:.2f}) ---")
        
        # Step 1: Up 0.8%
        p1 = round(entry * 1.008, 2)
        r1 = trailing_engine.process_tick(sym, p1)
        print(f"  Tick 1 (+0.8%): Price=₹{p1} | SL=₹{r1['stop_loss']} | BE Locked={r1['breakeven_locked']}")

        # Step 2: Up 1.8% -> Breakeven lock
        p2 = round(entry * 1.018, 2)
        r2 = trailing_engine.process_tick(sym, p2)
        print(f"  Tick 2 (+1.8%): Price=₹{p2} | SL=₹{r2['stop_loss']} | BE Locked={r2['breakeven_locked']}")

        # Step 3: Up 2.5% -> Ratchet stop higher
        p3 = round(entry * 1.025, 2)
        r3 = trailing_engine.process_tick(sym, p3)
        print(f"  Tick 3 (+2.5%): Price=₹{p3} | High=₹{r3['highest_watermark']} | SL=₹{r3['stop_loss']}")

        # Step 4: Drop below trailing stop -> Trigger exit!
        pullback = round(r3['stop_loss'] - 1.0, 2)
        print(f"  Tick 4 (Pullback to ₹{pullback} <= SL ₹{r3['stop_loss']}):")
        r4 = trailing_engine.process_tick(sym, pullback)
        print(f"  Result: Status={r4['status']} | Exit Reason={r4.get('exit_reason')} | Updated Cash=₹{r4.get('updated_cash')}")

    print("\n✅ Simulation sequence completed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Algo Lab Intraday Paper Trading Monitor")
    parser.add_argument("--session-id", default="sess_e22e8042bc25", help="Session ID to monitor")
    parser.add_argument("--cycle", action="store_true", help="Run a single live tick cycle")
    parser.add_argument("--simulate-ticks", action="store_true", help="Run simulated tick stream demonstration")
    parser.add_argument("--square-off", action="store_true", help="Auto square-off all open positions immediately")
    args = parser.parse_args()

    engine = inspect_intraday_session(args.session_id)

    if args.cycle:
        print("\n[Executing Live Market Tick Cycle]")
        run_tick_cycle(engine, fetch_live=True)
        print("\n[Post-Cycle Session State]")
        inspect_intraday_session(args.session_id)
    elif args.simulate_ticks:
        simulate_ticks_sequence(engine)
        print("\n[Post-Simulation Session State]")
        inspect_intraday_session(args.session_id)
    elif args.square_off:
        print("\n[Initiating 15:15 IST Auto Square-off for All Positions]")
        results = engine.auto_square_off_all_positions(reason="AUTO_SQUARE_OFF_1515_IST")
        for r in results:
            print(f"  Squared off: {r['symbol']} | Reason: {r['exit_reason']} | Price: ₹{r['exit_price']}")
        print("\n[Post Square-Off Session State]")
        inspect_intraday_session(args.session_id)
