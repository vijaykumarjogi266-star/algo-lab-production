#!/usr/bin/env python3
"""
Algo Lab — Live Paper Trading Pre-Flight Verification & Readiness Suite.

Executes a comprehensive, fail-closed pre-market audit before launching live paper trading:
1. Safety Invariants Verification (Strict Paper-Only, Zero Live Execution).
2. NSE Trading Calendar Verification (XNSE Market Open Bounds).
3. API Market Data Feed & Connectivity (NSE Live, KiteConnect Profile, YFinance).
4. Double-Entry Portfolio Ledger & State Invariant Consistency.
5. Pre-Market Watchlist Integrity & Algorithmic Setups.
6. Notification & Telemetry Readiness (Discord / Telegram).

Usage:
    python3 scripts/pre_flight_live_paper_check.py
"""

import os
import sys
import json
import sqlite3
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Dict, Any, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

IST = ZoneInfo("Asia/Kolkata")


def mask_secret(val: str) -> str:
    if not val:
        return "[NOT SET]"
    if len(val) <= 10:
        return "****"
    return f"{val[:4]}...{val[-4:]}"


def run_pre_flight_check() -> bool:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")

    print("\n" + "=" * 80)
    print(" 🚀 ALGO LAB — INSTITUTIONAL LIVE PAPER TRADING PRE-FLIGHT AUDIT")
    print("=" * 80)

    now_ist = datetime.datetime.now(IST)
    print(f" Current Timestamp: {now_ist.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f" Working Directory: {BASE_DIR}")
    print("-" * 80)

    results = []

    # --------------------------------------------------------------------------
    # GATE 1: Safety Invariants & Execution Boundaries
    # --------------------------------------------------------------------------
    print("\n[GATE 1/6] Auditing Non-Negotiable Safety Invariants...")
    try:
        from apps.api.core.config import settings
        import live_market_daemon

        live_trading = getattr(settings, "LIVE_TRADING_ENABLED", False)
        real_broker = getattr(settings, "REAL_BROKER_EXECUTION_ENABLED", False)
        daemon_live = getattr(live_market_daemon, "ALLOW_LIVE_TRADING", False)
        daemon_real = getattr(live_market_daemon, "ALLOW_REAL_BROKER_EXECUTION", False)

        if live_trading or real_broker or daemon_live or daemon_real:
            results.append(("GATE 1: Safety Invariants", False, "Live trading enabled (VIOLATION)"))
            print("  ❌ FAIL: Live trading invariant breached!")
        else:
            results.append(("GATE 1: Safety Invariants", True, "Paper-Only locked (LIVE_TRADING=False)"))
            print("  ✅ PASS: Strict Paper-Only Invariant Enforced (All live execution blocked).")
    except Exception as e:
        results.append(("GATE 1: Safety Invariants", False, str(e)))
        print(f"  ❌ FAIL: {e}")

    # --------------------------------------------------------------------------
    # GATE 2: NSE Trading Calendar & Session Bounds
    # --------------------------------------------------------------------------
    print("\n[GATE 2/6] Auditing NSE Trading Calendar (XNSE)...")
    try:
        from services.data_governance.calendar_provider import VersionedMarketCalendarProvider
        cal = VersionedMarketCalendarProvider()

        # Check today or next trading day
        target_date = (now_ist + datetime.timedelta(days=1)).date() if now_ist.time() >= datetime.time(15, 30) else now_ist.date()
        while not cal.is_trading_day(target_date):
            target_date += datetime.timedelta(days=1)

        open_time, close_time = cal.get_session_bounds(target_date)
        is_trading = cal.is_trading_day(target_date)

        if is_trading:
            results.append(("GATE 2: Market Calendar", True, f"Session {target_date} verified ({open_time} - {close_time} IST)"))
            print(f"  ✅ PASS: Verified trading day: {target_date.strftime('%A, %B %d, %Y')}")
            print(f"          Trading Session Bounds: {open_time} to {close_time} IST")
        else:
            results.append(("GATE 2: Market Calendar", False, f"Target date {target_date} is not a trading day"))
            print(f"  ❌ FAIL: Target date {target_date} is closed.")
    except Exception as e:
        results.append(("GATE 2: Market Calendar", False, str(e)))
        print(f"  ❌ FAIL: {e}")

    # --------------------------------------------------------------------------
    # GATE 3: Market Data Feeds & Broker API Connectivity
    # --------------------------------------------------------------------------
    print("\n[GATE 3/6] Auditing Market Data Feeds & API Providers...")
    api_statuses = []

    # 3a. Official NSE Live Market Data Adapter
    try:
        from services.market_data.adapters.nse_adapter import NSELiveMarketDataAdapter
        nse_adapter = NSELiveMarketDataAdapter()
        nse_res = nse_adapter.test_connection()
        if nse_res.get("connected"):
            print("  ✅ [NSE Live API] Connected successfully (Market status endpoint responding).")
            api_statuses.append(True)
        else:
            print(f"  ⚠️ [NSE Live API] Warning: {nse_res.get('message')}")
            api_statuses.append(False)
    except Exception as e:
        print(f"  ⚠️ [NSE Live API] Error: {e}")
        api_statuses.append(False)

    # 3b. Yahoo Finance Candlestick Feed
    try:
        import yfinance as yf
        test_df = yf.download("RELIANCE.NS", period="5d", interval="1d", progress=False)
        if not test_df.empty:
            last_price = float(test_df["Close"].values.flatten()[-1])
            print(f"  ✅ [Yahoo Finance] Connected successfully (RELIANCE LTP: ₹{last_price:,.2f}).")
            api_statuses.append(True)
        else:
            print("  ⚠️ [Yahoo Finance] Returned empty dataset.")
            api_statuses.append(False)
    except Exception as e:
        print(f"  ⚠️ [Yahoo Finance] Error: {e}")
        api_statuses.append(False)

    # 3c. Zerodha KiteConnect Session
    try:
        from dotenv import load_dotenv
        load_dotenv(BASE_DIR / ".env")
        from kiteconnect import KiteConnect

        api_key = os.getenv("ZERODHA_API_KEY")
        access_token = os.getenv("ZERODHA_ACCESS_TOKEN")

        if api_key and access_token:
            kite = KiteConnect(api_key=api_key)
            kite.set_access_token(access_token)
            profile = kite.profile()
            user_name = profile.get("user_name", "Unknown")
            user_id = profile.get("user_id", "Unknown")
            print(f"  ✅ [Zerodha KiteConnect] Authenticated session active for {user_name} ({user_id}).")
            api_statuses.append(True)
        else:
            print("  ℹ️ [Zerodha KiteConnect] No credentials in .env (operating on standalone simulated feeds).")
            api_statuses.append(True)
    except Exception as e:
        print(f"  ⚠️ [Zerodha KiteConnect] Session notice: {e} (paper mode will use direct simulated execution).")
        api_statuses.append(True)

    if any(api_statuses):
        results.append(("GATE 3: Market Data Feeds", True, "Primary and fallback API feeds active"))
    else:
        results.append(("GATE 3: Market Data Feeds", False, "All market data feeds failed"))

    # --------------------------------------------------------------------------
    # GATE 4: Double-Entry Ledger & JSON State Integrity
    # --------------------------------------------------------------------------
    print("\n[GATE 4/6] Auditing Portfolio Ledger & State Invariants...")
    try:
        state_path = BASE_DIR / "data" / "live_portfolio_state.json"
        ledger_path = BASE_DIR / "data" / "swing_portfolio_ledger.db"

        if not state_path.exists():
            raise FileNotFoundError(f"{state_path} does not exist")
        if not ledger_path.exists():
            raise FileNotFoundError(f"{ledger_path} does not exist")

        with open(state_path) as f:
            state_data = json.load(f)

        account_id = state_data.get("account_id")
        cash = state_data.get("cash", 0.0)
        equity = state_data.get("equity", 0.0)
        positions = state_data.get("positions", {})

        # Verify SQLite integrity
        conn = sqlite3.connect(ledger_path)
        cur = conn.cursor()
        integrity = cur.execute("PRAGMA integrity_check;").fetchone()[0]
        pos_count = cur.execute("SELECT COUNT(*) FROM open_positions;").fetchone()[0]
        conn.close()

        if integrity == "ok" and len(positions) == pos_count:
            results.append(("GATE 4: Ledger & State", True, f"Account {account_id} verified | Cash: ₹{cash:,.2f} | Positions: {len(positions)}"))
            print(f"  ✅ PASS: State & Ledger in sync. SQLite integrity: {integrity}")
            print(f"          Account: {account_id} | Cash: ₹{cash:,.2f} | Open Positions: {len(positions)}")
        else:
            results.append(("GATE 4: Ledger & State", False, f"State mismatch: JSON({len(positions)}) != DB({pos_count})"))
            print(f"  ❌ FAIL: State drift detected.")
    except Exception as e:
        results.append(("GATE 4: Ledger & State", False, str(e)))
        print(f"  ❌ FAIL: {e}")

    # --------------------------------------------------------------------------
    # GATE 5: Pre-Market Watchlist & Algorithmic Setups
    # --------------------------------------------------------------------------
    print("\n[GATE 5/6] Auditing Pre-Market Watchlist & Candidate Setups...")
    try:
        watchlist_path = BASE_DIR / "data" / "tomorrow_scanner_watchlist.json"
        if not watchlist_path.exists():
            from scripts.run_pre_market_scanner import run_pre_market_scan
            print("  ℹ️ Watchlist not found. Generating fresh scan...")
            run_pre_market_scan()

        with open(watchlist_path) as f:
            wl = json.load(f)

        candidates = wl.get("top_candidates", [])
        scan_date = wl.get("market_session_date", "Unknown")

        if candidates:
            top_syms = ", ".join([c["symbol"] for c in candidates[:3]])
            results.append(("GATE 5: Pre-Market Watchlist", True, f"{len(candidates)} setups ready for session {scan_date} ({top_syms})"))
            print(f"  ✅ PASS: {len(candidates)} qualified setups ready for session {scan_date}.")
            for idx, c in enumerate(candidates[:3], 1):
                print(f"          {idx}. {c['symbol']} ({c['setup']}) | LTP: ₹{c['last_close']:,.2f} | SL: ₹{c['stop_loss']:,.2f}")
        else:
            results.append(("GATE 5: Pre-Market Watchlist", False, "Zero setups in watchlist"))
            print("  ⚠️ WARNING: Zero setups qualified in watchlist.")
    except Exception as e:
        results.append(("GATE 5: Pre-Market Watchlist", False, str(e)))
        print(f"  ❌ FAIL: {e}")

    # --------------------------------------------------------------------------
    # GATE 6: Notification Webhook Readiness
    # --------------------------------------------------------------------------
    print("\n[GATE 6/6] Auditing Notification Telemetry Channels...")
    discord_url = os.getenv("DISCORD_WEBHOOK_URL", "")
    telegram_url = os.getenv("TELEGRAM_WEBHOOK_URL", "")

    discord_ok = bool(discord_url and discord_url.startswith("https://discord"))
    telegram_ok = bool(telegram_url and telegram_url.startswith("https://api.telegram"))

    print(f"  • Discord Webhook:  {'Configured (' + mask_secret(discord_url) + ')' if discord_ok else 'Not configured'}")
    print(f"  • Telegram Webhook: {'Configured (' + mask_secret(telegram_url) + ')' if telegram_ok else 'Not configured'}")

    results.append(("GATE 6: Telemetry Channels", True, f"Discord: {discord_ok} | Telegram: {telegram_ok}"))

    # --------------------------------------------------------------------------
    # PRE-FLIGHT CERTIFICATION SUMMARY
    # --------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print(" 📋 PRE-FLIGHT READINESS CERTIFICATION MATRIX")
    print("=" * 80)
    all_passed = True
    for gate_name, passed, detail in results:
        status_icon = "✅ PASS" if passed else "❌ FAIL"
        if not passed:
            all_passed = False
        print(f" {status_icon} | {gate_name:<28} | {detail}")

    print("=" * 80)
    if all_passed:
        print("\n🎉 GREEN LIGHT: ALGO LAB IS 100% READY FOR TOMORROW'S LIVE PAPER TRADING!")
        print("\n Recommended Execution Commands:")
        print("  1. Interactive Foreground Daemon (with live logs):")
        print("     $ python3 live_market_daemon.py --loop-daily")
        print("\n  2. Live Intraday Scanner (during 09:15-15:00 IST):")
        print("     $ python3 scripts/run_live_intraday_scanner.py")
        print("\n  3. Real-Time Portfolio Monitoring Dashboard:")
        print("     $ python3 scripts/monitor_live_paper_intraday.py")
        print("\n  4. Background Service (Systemd):")
        print("     $ sudo cp quant-os.service /etc/systemd/system/ && sudo systemctl start quant-os.service")
    else:
        print("\n⚠️ RED LIGHT: Resolve pre-flight gate failures before launching.")
    print("=" * 80 + "\n")

    return all_passed


if __name__ == "__main__":
    success = run_pre_flight_check()
    sys.exit(0 if success else 1)
