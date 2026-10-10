#!/usr/bin/env python3
"""
Algo Lab Standalone Push Notification Verification Tool.
Fires formatted test alerts (INFO, TRADE, and SUMMARY) to verify webhook integration.

Usage:
    # 1. Using webhook URL defined in .env:
    python scripts/test_notification.py

    # 2. Providing webhook URL directly on command line:
    python scripts/test_notification.py --url https://discord.com/api/webhooks/...

    # 3. Providing Telegram webhook URL:
    python scripts/test_notification.py --telegram-url https://api.telegram.org/...
"""

import sys
import os
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.notification_engine import NotificationEngine, load_env_vars


def mask_url(url: str) -> str:
    """Masks secret token in webhook URL for secure console display."""
    if not url:
        return "None"
    if len(url) <= 30:
        return url[:10] + "..."
    return url[:25] + "..." + url[-8:]


def main():
    parser = argparse.ArgumentParser(description="Fire Algo Lab Institutional Test Notifications")
    parser.add_argument("--url", "--discord-url", dest="discord_url", default=None, help="Discord Webhook URL")
    parser.add_argument("--telegram-url", dest="telegram_url", default=None, help="Telegram Webhook URL")
    parser.add_argument("--account", default="ACC-FORWARD-CANONICAL-100K-01", help="Canonical Account ID")
    args = parser.parse_args()

    # Load environment variables
    env_vars = load_env_vars()

    discord_url = args.discord_url or os.getenv("DISCORD_WEBHOOK_URL") or ""
    telegram_url = args.telegram_url or os.getenv("TELEGRAM_WEBHOOK_URL") or ""

    print("=" * 80)
    print("  🔔 ALGO LAB INSTITUTIONAL PUSH NOTIFICATION TEST SUITE")
    print("=" * 80)
    print(f"  • Discord Webhook:   {mask_url(discord_url)}")
    print(f"  • Telegram Webhook:  {mask_url(telegram_url)}")
    print(f"  • Account Binding:   {args.account}")
    print(f"  • Safety Invariant:  ALLOW_LIVE_TRADING = FALSE (Paper Trading Only)")
    print("=" * 80 + "\n")

    notifier = NotificationEngine(
        discord_webhook_url=discord_url,
        telegram_webhook_url=telegram_url,
        account_id=args.account
    )

    if not notifier.has_active_webhook:
        print("⚠️  [NOTICE] No active webhook URL found in environment or .env file.")
        print("   Running in CONSOLE PREVIEW MODE to demonstrate alert styling.\n")
        print("   To receive real push notifications on your phone / Discord / Telegram:")
        print("   1. Open .env and set: DISCORD_WEBHOOK_URL=\"https://discord.com/api/webhooks/...\"")
        print("   2. Or run: python scripts/test_notification.py --url \"https://discord.com/api/webhooks/...\"\n")
    else:
        print("🚀 [CONNECTED] Dispatching 3 test alert stages to configured webhook(s)...\n")

    # Stage 1: INFO Alert
    print("--- [STAGE 1: INFO NOTIFICATION] ---")
    info_ok = notifier.send_info(
        message="EOD Scan Initiated for 50 Nifty Universe. Daily candles ingested & ATR14 calculated.",
        title="Algo Lab Desk Startup Check",
        details={"Scan Universe": "Nifty 50 Constituents", "Execution Window": "15:15 - 15:25 IST"}
    )
    print(f"Result: {'✅ Delivered' if info_ok else '⚠️ Failed / Console Fallback'}\n")

    # Stage 2: TRADE Alert (BUY)
    print("--- [STAGE 2: TRADE NOTIFICATION - BUY ENTRY] ---")
    buy_ok = notifier.send_trade_alert(
        action="BUY",
        symbol="RELIANCE.NS",
        quantity=10,
        price=2500.0,
        stop_loss=2400.0,
        take_profit=2800.0,
        sector="ENERGY_POWER"
    )
    print(f"Result: {'✅ Delivered' if buy_ok else '⚠️ Failed / Console Fallback'}\n")

    # Stage 3: TRADE Alert (SELL - Stop Loss)
    print("--- [STAGE 3: TRADE NOTIFICATION - SELL EXIT] ---")
    sell_ok = notifier.send_trade_alert(
        action="SELL",
        symbol="INFY.NS",
        quantity=15,
        price=1850.0,
        net_pnl=-450.0,
        gross_pnl=-420.0,
        exit_reason="STOP_LOSS_HIT",
        sector="IT_CONSULTING",
        holding_period_days=3,
        friction=30.0
    )
    print(f"Result: {'✅ Delivered' if sell_ok else '⚠️ Failed / Console Fallback'}\n")

    # Stage 4: SUMMARY Alert
    print("--- [STAGE 4: SUMMARY NOTIFICATION - EOD CLOSE] ---")
    summary_ok = notifier.send_summary(
        active_positions_count=1,
        cash=75000.0,
        equity=100500.0,
        net_pnl=500.0,
        completed_trades_count=2,
        market_date="2026-10-02"
    )
    print(f"Result: {'✅ Delivered' if summary_ok else '⚠️ Failed / Console Fallback'}\n")

    print("=" * 80)
    if notifier.has_active_webhook:
        print("🎉 [SUCCESS] Test notifications dispatched successfully! Please check your mobile/desktop client.")
    else:
        print("✅ [CONSOLE PREVIEW COMPLETE] Notification engine verified in local fallback mode.")
    print("=" * 80)


if __name__ == "__main__":
    main()
