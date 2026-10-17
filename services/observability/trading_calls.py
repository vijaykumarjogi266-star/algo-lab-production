#!/usr/bin/env python3
"""
AlgoLab Live Trading Calls Telegram Broadcaster
Dispatches and formats real-time trading calls (Stock Name, Entry, Exit, Target)
for Intraday (MIS), Swing (CNC), and Institutional Paper Engines.
"""

import os
import json
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
import requests

IST = timezone(timedelta(hours=5, minutes=30))
BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
DEFAULT_TOKEN = "8989185736:AAHDlRR2fBCYLL4_8E_CzGyHTOKJyXlIvhU"
DEFAULT_CHAT_ID = "7308387554"

logger = logging.getLogger("trading_calls")


def get_telegram_creds() -> tuple[str, str]:
    """Resolves Telegram Bot Token and Admin Chat ID with fail-safe fallbacks."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    # Fallback to TELEGRAM_WEBHOOK_URL if token not directly in TELEGRAM_BOT_TOKEN
    if not token and os.getenv("TELEGRAM_WEBHOOK_URL"):
        url = os.getenv("TELEGRAM_WEBHOOK_URL", "")
        if "/bot" in url and "/sendMessage" in url:
            try:
                token = url.split("/bot")[1].split("/")[0]
            except Exception:
                pass

    # Fallback to bridge config.json
    if (not token or not chat_id) and CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
                token = token or cfg.get("bot_token")
                chat_id = chat_id or str(cfg.get("admin_chat_id"))
        except Exception as e:
            logger.warning(f"Failed to load bridge config.json: {e}")

    # Fallback to defaults
    token = token or DEFAULT_TOKEN
    chat_id = str(chat_id) if chat_id else DEFAULT_CHAT_ID
    return token, chat_id


def send_telegram_alert(message: str, parse_mode: str = "HTML") -> bool:
    """Dispatches a formatted trading message to Telegram admin chat."""
    token, chat_id = get_telegram_creds()
    if not token or not chat_id:
        logger.error("Telegram credentials missing, alert aborted.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    try:
        resp = requests.post(url, json=payload, timeout=12)
        data = resp.json()
        if data.get("ok"):
            return True
        else:
            logger.warning(f"Telegram alert failed with HTML: {data}. Retrying with plain text.")
            # Fallback plain text if markdown/HTML fails
            payload.pop("parse_mode", None)
            resp2 = requests.post(url, json=payload, timeout=12)
            return resp2.json().get("ok", False)
    except Exception as e:
        logger.error(f"Telegram network exception: {e}")
        return False


def format_live_entry_call(
    symbol: str,
    action: str = "BUY",
    entry_price: float = 0.0,
    stop_loss: float = 0.0,
    target_price: float = 0.0,
    quantity: int = 1,
    allocated_margin: Optional[float] = None,
    strategy: str = "AlgoLab Momentum",
    segment: str = "INTRADAY (MIS)",
    notes: str = ""
) -> str:
    """
    Formats a high-conviction live trading call with Stock Name, Entry, Exit/SL, and Target.
    """
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    clean_sym = symbol.replace(".NS", "").upper()
    margin = allocated_margin if allocated_margin is not None else (entry_price * quantity)

    # Risk & Reward calculation
    risk_pts = abs(entry_price - stop_loss) if stop_loss > 0 else 0.0
    reward_pts = abs(target_price - entry_price) if target_price > 0 else 0.0
    risk_pct = (risk_pts / entry_price * 100) if entry_price > 0 else 0.0
    reward_pct = (reward_pts / entry_price * 100) if entry_price > 0 else 0.0
    rr_ratio = f"1 : {(reward_pts / risk_pts):.1f}" if risk_pts > 0 else "N/A"

    badge_emoji = "🟢" if action.upper() == "BUY" else "🔴"

    lines = [
        f"🎯 <b>LIVE TRADING CALL: {action.upper()}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🏢 <b>Stock Name:</b> <code>{clean_sym}</code> (NSE)",
        f"⚡ <b>Action:</b> {badge_emoji} <b>{action.upper()}</b> | <b>{segment}</b>",
        f"💰 <b>Entry Price:</b> <b>₹{entry_price:,.2f}</b>",
        f"🎯 <b>Target Price:</b> <b>₹{target_price:,.2f}</b> (+{reward_pct:.2f}%)",
        f"🛑 <b>Exit / Stop Loss:</b> <b>₹{stop_loss:,.2f}</b> (-{risk_pct:.2f}%)",
        f"⚖️ <b>Risk:Reward:</b> {rr_ratio}",
        f"📦 <b>Quantity:</b> {quantity} shares",
        f"💼 <b>Capital / Margin:</b> ₹{margin:,.2f}",
        f"📊 <b>Strategy:</b> {strategy}",
        f"⏰ <b>Trigger Time:</b> {now_ist}",
    ]

    if notes:
        lines.append(f"📝 <b>Notes:</b> {notes}")

    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "Status: 🟢 <b>ACTIVE IN MARKET</b>",
    ])

    return "\n".join(lines)


def format_live_exit_call(
    symbol: str,
    action: str = "SELL",
    entry_price: float = 0.0,
    exit_price: float = 0.0,
    stop_loss: float = 0.0,
    target_price: float = 0.0,
    quantity: int = 1,
    pnl: float = 0.0,
    return_pct: Optional[float] = None,
    reason: str = "TARGET_HIT",
    segment: str = "INTRADAY (MIS)",
    friction: float = 0.0,
) -> str:
    """
    Formats a closed trading call with Entry, Exit, Target, and realized P&L.
    """
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    clean_sym = symbol.replace(".NS", "").upper()

    if return_pct is None and entry_price > 0:
        return_pct = ((exit_price - entry_price) / entry_price) * 100

    pnl_emoji = "🎉 🟢" if pnl >= 0 else "🛑 🔴"
    status_emoji = "🎯" if "TARGET" in reason.upper() else ("🛡️" if "STOP" in reason.upper() else "⏰")

    lines = [
        f"{status_emoji} <b>LIVE TRADING CALL UPDATE: CLOSED</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🏢 <b>Stock Name:</b> <code>{clean_sym}</code> (NSE)",
        f"⚡ <b>Action:</b> <b>{action.upper()} ({segment})</b>",
        f"🔔 <b>Exit Reason:</b> <code>{reason}</code>",
        f"💰 <b>Entry Price:</b> ₹{entry_price:,.2f}",
        f"🏁 <b>Exit Price:</b> <b>₹{exit_price:,.2f}</b>",
        f"🎯 <b>Original Target:</b> ₹{target_price:,.2f}",
        f"🛑 <b>Original Stop Loss:</b> ₹{stop_loss:,.2f}",
        f"📦 <b>Quantity:</b> {quantity} shares",
        f"{pnl_emoji} <b>Net P&L:</b> <b>{'₹+' if pnl >= 0 else '₹'}{pnl:,.2f}</b> ({return_pct:+.2f}%)",
    ]

    if friction > 0:
        lines.append(f"🧾 <b>Statutory Frictions:</b> ₹{friction:,.2f}")

    lines.extend([
        f"⏰ <b>Exit Time:</b> {now_ist}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "Status: 🏁 <b>COMPLETED & SETTLED</b>",
    ])

    return "\n".join(lines)


def format_trailing_sl_call(
    symbol: str,
    entry_price: float,
    old_sl: float,
    new_sl: float,
    target_price: float,
    current_price: float,
    notes: str = "Breakeven Locked (+1.0R Reached)",
) -> str:
    """Formats an update when Stop Loss is tightened / ratcheted."""
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    clean_sym = symbol.replace(".NS", "").upper()

    return "\n".join([
        "🛡️ <b>LIVE CALL UPDATE: STOP LOSS RATCHETED</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🏢 <b>Stock Name:</b> <code>{clean_sym}</code> (NSE)",
        f"⚡ <b>Event:</b> {notes}",
        f"💰 <b>Entry Price:</b> ₹{entry_price:,.2f}",
        f"📈 <b>Current LTP:</b> ₹{current_price:,.2f}",
        f"🛑 <b>Old Stop Loss:</b> ₹{old_sl:,.2f}",
        f"🔒 <b>New Stop Loss (Exit):</b> <b>₹{new_sl:,.2f} (Risk Free)</b>",
        f"🎯 <b>Target Price:</b> ₹{target_price:,.2f}",
        f"⏰ <b>Ratchet Time:</b> {now_ist}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "Status: 🟢 <b>POSITION PROTECTED</b>",
    ])


def fetch_all_active_calls() -> List[Dict[str, Any]]:
    """Gathers open positions from intraday ledger and paper trading databases."""
    active_calls = []

    # 1. Query Intraday Ledger Database
    ledger_candidates = [
        Path("/home/ubuntu/all-in-one/data/intraday_ledger.db"),
        Path("/home/ubuntu/algolab/data/intraday_ledger.db"),
        Path("/home/ubuntu/data/intraday_ledger.db"),
    ]

    for db_file in ledger_candidates:
        if db_file.exists():
            try:
                conn = sqlite3.connect(str(db_file))
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute("""
                    SELECT symbol, side, strategy_phase, quantity, entry_price, 
                           current_price, stop_loss, target_price, allocated_margin, 
                           breakeven_locked, opened_at, status 
                    FROM intraday_positions 
                    WHERE status = 'OPEN' 
                    ORDER BY opened_at DESC;
                """)
                rows = c.fetchall()
                for r in rows:
                    active_calls.append({
                        "source": "INTRADAY (MIS)",
                        "symbol": r["symbol"],
                        "side": r["side"] or "BUY",
                        "strategy": r["strategy_phase"] or "Intraday Momentum",
                        "quantity": r["quantity"],
                        "entry_price": float(r["entry_price"]),
                        "current_price": float(r["current_price"] or r["entry_price"]),
                        "stop_loss": float(r["stop_loss"]),
                        "target_price": float(r["target_price"]),
                        "margin": float(r["allocated_margin"]),
                        "breakeven_locked": bool(r["breakeven_locked"]),
                        "opened_at": r["opened_at"],
                    })
                conn.close()
                if active_calls:
                    break
            except Exception as e:
                logger.warning(f"Error reading intraday positions from {db_file}: {e}")

    # 2. Query Algopro paper_trading.db
    paper_db = Path("/home/ubuntu/algopro/data/paper_trading.db")
    if paper_db.exists():
        try:
            conn = sqlite3.connect(str(paper_db))
            c = conn.cursor()
            c.execute("SELECT portfolio_data FROM paper_sessions WHERE status = 'RUNNING' ORDER BY rowid DESC LIMIT 1;")
            row = c.fetchone()
            if row and row[0]:
                p_data = json.loads(row[0])
                positions = p_data.get("positions", {})
                for sym, pos in positions.items():
                    qty = pos.get("quantity", 0)
                    if qty > 0:
                        entry = pos.get("average_entry_price", 0.0)
                        ltp = pos.get("current_price", entry)
                        sl = pos.get("stop_loss", round(entry * 0.98, 2))
                        tp = pos.get("target_price", round(entry * 1.03, 2))
                        active_calls.append({
                            "source": "PAPER LAB (MIS)",
                            "symbol": sym,
                            "side": "BUY",
                            "strategy": "Institutional Sentinel",
                            "quantity": qty,
                            "entry_price": float(entry),
                            "current_price": float(ltp),
                            "stop_loss": float(sl),
                            "target_price": float(tp),
                            "margin": float(entry * qty),
                            "breakeven_locked": False,
                            "opened_at": datetime.now(IST).strftime("%H:%M:%S"),
                        })
            conn.close()
        except Exception as e:
            logger.warning(f"Error reading paper_trading.db: {e}")

    return active_calls


def format_active_calls_summary() -> str:
    """Generates the Telegram message detailing all live calls with entry, exit, target."""
    calls = fetch_all_active_calls()
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")

    if not calls:
        return (
            "🎯 <b>LIVE TRADING CALLS STATUS</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📊 <b>Active Positions:</b> <code>0 Open Calls</code>\n"
            "🛡️ <b>Risk Status:</b> Capital 100% Preserved / Overnight Protected\n"
            "⏱️ <b>Auto Cutoff:</b> 15:15:00 IST (Strict MIS Square-off)\n\n"
            "🔍 <b>Market Scanner:</b> Active\n"
            "The system is monitoring the NSE universe for high-conviction breakout and pullback setups.\n\n"
            "<i>When a trade setup triggers, you will receive an automatic push alert with Stock Name, Entry Price, Stop Loss (Exit), and Target!</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ <i>As of: {now_ist}</i>"
        )

    lines = [
        "🎯 <b>ACTIVE LIVE TRADING CALLS</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📊 <b>Open Calls Count:</b> <b>{len(calls)} Active</b>",
        f"⏰ <b>Market Time:</b> {now_ist}",
        "",
    ]

    for idx, c in enumerate(calls, 1):
        sym = c["symbol"].replace(".NS", "").upper()
        entry = c["entry_price"]
        ltp = c["current_price"]
        sl = c["stop_loss"]
        tp = c["target_price"]
        qty = c["quantity"]
        pnl = (ltp - entry) * qty
        ret_pct = ((ltp - entry) / entry * 100) if entry > 0 else 0.0

        dist_tp = max(0.0, tp - ltp)
        dist_sl = max(0.0, ltp - sl)
        be_tag = " [🔒 Breakeven Locked]" if c.get("breakeven_locked") else ""

        pnl_badge = f"+₹{pnl:,.2f}" if pnl >= 0 else f"-₹{abs(pnl):,.2f}"

        lines.extend([
            f"<b>{idx}. {sym}</b> ({c['source']}){be_tag}",
            f"  • <b>Action:</b> 🟢 <b>{c['side']}</b> ({qty} shares)",
            f"  • <b>Entry Price:</b> ₹{entry:,.2f}",
            f"  • <b>Current LTP:</b> ₹{ltp:,.2f} (P&L: <b>{pnl_badge}</b> / {ret_pct:+.2f}%)",
            f"  • 🎯 <b>Target:</b> <b>₹{tp:,.2f}</b> (₹{dist_tp:,.2f} away)",
            f"  • 🛑 <b>Exit / Stop Loss:</b> <b>₹{sl:,.2f}</b> (Buffer: ₹{dist_sl:,.2f})",
            f"  • 💼 <b>Margin Deployed:</b> ₹{c['margin']:,.2f}",
            "",
        ])

    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "⏱️ <i>Mandatory Square-off: 15:15 IST</i>",
    ])

    return "\n".join(lines)


# Public helper notification functions for daemons
def broadcast_trade_entry(
    symbol: str,
    action: str = "BUY",
    entry_price: float = 0.0,
    stop_loss: float = 0.0,
    target_price: float = 0.0,
    quantity: int = 1,
    allocated_margin: Optional[float] = None,
    strategy: str = "AlgoLab Engine",
    segment: str = "INTRADAY (MIS)",
    notes: str = ""
) -> bool:
    msg = format_live_entry_call(
        symbol=symbol,
        action=action,
        entry_price=entry_price,
        stop_loss=stop_loss,
        target_price=target_price,
        quantity=quantity,
        allocated_margin=allocated_margin,
        strategy=strategy,
        segment=segment,
        notes=notes,
    )
    return send_telegram_alert(msg)


def broadcast_trade_exit(
    symbol: str,
    action: str = "SELL",
    entry_price: float = 0.0,
    exit_price: float = 0.0,
    stop_loss: float = 0.0,
    target_price: float = 0.0,
    quantity: int = 1,
    pnl: float = 0.0,
    return_pct: Optional[float] = None,
    reason: str = "TARGET_HIT",
    segment: str = "INTRADAY (MIS)",
    friction: float = 0.0,
) -> bool:
    msg = format_live_exit_call(
        symbol=symbol,
        action=action,
        entry_price=entry_price,
        exit_price=exit_price,
        stop_loss=stop_loss,
        target_price=target_price,
        quantity=quantity,
        pnl=pnl,
        return_pct=return_pct,
        reason=reason,
        segment=segment,
        friction=friction,
    )
    return send_telegram_alert(msg)


def broadcast_trailing_sl(
    symbol: str,
    entry_price: float,
    old_sl: float,
    new_sl: float,
    target_price: float,
    current_price: float,
    notes: str = "Breakeven Locked (+1.0R Reached)",
) -> bool:
    msg = format_trailing_sl_call(
        symbol=symbol,
        entry_price=entry_price,
        old_sl=old_sl,
        new_sl=new_sl,
        target_price=target_price,
        current_price=current_price,
        notes=notes,
    )
    return send_telegram_alert(msg)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AlgoLab Live Trading Calls Telegram Broadcaster")
    parser.add_argument("--test-entry", action="store_true", help="Send a test live entry call")
    parser.add_argument("--test-exit", action="store_true", help="Send a test trade exit alert")
    parser.add_argument("--summary", action="store_true", help="Print or send active calls summary")
    parser.add_argument("--send-summary", action="store_true", help="Send summary to Telegram")
    args = parser.parse_args()

    if args.test_entry:
        print("Sending test live entry call to Telegram...")
        res = broadcast_trade_entry(
            symbol="RELIANCE",
            action="BUY",
            entry_price=2850.50,
            stop_loss=2820.00,
            target_price=2911.50,
            quantity=15,
            allocated_margin=42757.50,
            strategy="Intraday Trend Pullback (ORB_15)",
            segment="INTRADAY (MIS)",
            notes="Breakout above 15m high with institutional volume spike",
        )
        print("Result:", res)

    elif args.test_exit:
        print("Sending test trade exit alert to Telegram...")
        res = broadcast_trade_exit(
            symbol="RELIANCE",
            action="SELL",
            entry_price=2850.50,
            exit_price=2911.50,
            stop_loss=2820.00,
            target_price=2911.50,
            quantity=15,
            pnl=915.00,
            return_pct=2.14,
            reason="TARGET_HIT",
            segment="INTRADAY (MIS)",
            friction=22.40,
        )
        print("Result:", res)

    elif args.summary or args.send_summary:
        summary_text = format_active_calls_summary()
        print(summary_text)
        if args.send_summary:
            print("Sending to Telegram...")
            send_telegram_alert(summary_text)
    else:
        print("Telegram Trading Calls Broadcaster Ready.")
        print(format_active_calls_summary())
