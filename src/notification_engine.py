#!/usr/bin/env python3
"""
Algo Lab Institutional Notification Engine.
Supports Discord Webhook and Telegram Webhook alerts with graceful fallback to console.

Message Types:
1. INFO: System status, startup, EOD scan notifications.
2. TRADE: High-conviction entry & exit executions (BUY / SELL with Stops, Targets, and PnL).
3. SUMMARY: EOD session summary with active positions, cash solvency, and equity metrics.
4. TEST: Standalone test notifications for verification.

Fails closed and safe: Never crashes the calling daemon if webhooks fail or URLs are missing.
"""

import os
import sys
import json
import logging
import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import urllib.request
import urllib.error

logger = logging.getLogger("algolab.notification_engine")

# Institutional Color Palette for Discord Embeds (Decimal Integers)
COLOR_EMERALD_GREEN = 0x10B981  # 1096065 (BUY, Take Profit, Positive P&L)
COLOR_ROSE_RED = 0xEF4444       # 15680580 (SELL, Stop Loss, Negative P&L)
COLOR_SKY_BLUE = 0x38BDF8       # 3718648 (INFO, Wakeup, Ingestion)
COLOR_AMBER = 0xF59E0B          # 16096779 (SUMMARY, Warnings)
COLOR_INDIGO = 0x6366F1         # 6514417 (System Governance, Neutral)


def load_env_vars(env_file_paths: Optional[List[Path]] = None) -> Dict[str, str]:
    """
    Lightweight zero-dependency .env loader.
    Searches standard project paths and populates os.environ without overwriting existing vars.
    """
    if env_file_paths is None:
        curr_dir = Path.cwd()
        script_dir = Path(__file__).resolve().parent
        parent_dir = script_dir.parent
        env_file_paths = [
            curr_dir / ".env",
            parent_dir / ".env",
            Path("/home/ubuntu/algolab-sandbox/disposable_sandbox/.env"),
            Path("/home/ubuntu/algolab/.env"),
            Path("/home/ubuntu/.env"),
        ]

    loaded = {}
    for p in env_file_paths:
        if p and p.is_file():
            try:
                for line in p.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = val
                        loaded[key] = val
                    elif key:
                        loaded[key] = os.environ[key]
            except Exception as e:
                logger.warning(f"Could not read .env file {p}: {e}")
    return loaded


class DiscordWebhookNotifier:
    """
    Institutional Webhook Notifier for Discord and Telegram.
    Formatted specifically for Algo Lab EOD Swing Trading Desk.
    """

    def __init__(
        self,
        discord_webhook_url: Optional[str] = None,
        telegram_webhook_url: Optional[str] = None,
        bot_name: str = "Algo Lab Institutional Desk",
        avatar_url: str = "https://cdn-icons-png.flaticon.com/512/2953/2953363.png",
        account_id: str = "ACC-FORWARD-CANONICAL-100K-01",
        timeout: int = 5,
    ):
        # 1. Load from environment / .env files
        load_env_vars()
        self.discord_webhook_url = (
            discord_webhook_url
            or os.getenv("DISCORD_WEBHOOK_URL")
            or os.getenv("WEBHOOK_URL")
            or ""
        ).strip()
        self.telegram_webhook_url = (
            telegram_webhook_url
            or os.getenv("TELEGRAM_WEBHOOK_URL")
            or ""
        ).strip()

        self.bot_name = bot_name
        self.avatar_url = avatar_url
        self.account_id = account_id
        self.timeout = timeout

        self.has_active_webhook = bool(self.discord_webhook_url or self.telegram_webhook_url)

    def _send_http_json(self, url: str, payload: dict) -> bool:
        """Sends JSON payload over HTTP/HTTPS with strict timeout and exception fencing."""
        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=req_data,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "AlgoLab-NotificationEngine/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status = resp.status
                return 200 <= status < 300
        except urllib.error.HTTPError as e:
            print(f"[NOTIFICATION WARNING] Webhook HTTP Error: {e.code} - {e.reason}")
            return False
        except urllib.error.URLError as e:
            print(f"[NOTIFICATION WARNING] Webhook URL Error: {e.reason}")
            return False
        except Exception as e:
            print(f"[NOTIFICATION WARNING] Webhook delivery exception: {e}")
            return False

    def send_raw_discord(self, content: str, embed: Optional[Dict[str, Any]] = None) -> bool:
        """Dispatches an institutional embed and plain-text notification to Discord."""
        if not self.discord_webhook_url:
            return False

        payload: Dict[str, Any] = {
            "username": self.bot_name,
            "avatar_url": self.avatar_url,
            "content": content,
        }
        if embed:
            payload["embeds"] = [embed]

        return self._send_http_json(self.discord_webhook_url, payload)

    def send_raw_telegram(self, text: str) -> bool:
        """Dispatches a formatted message to Telegram if configured."""
        if not self.telegram_webhook_url:
            return False

        # If it's a standard Telegram bot API URL without chat_id in query, fallback to text json
        payload = {"text": text}
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if chat_id:
            payload["chat_id"] = chat_id
            payload["parse_mode"] = "HTML"

        return self._send_http_json(self.telegram_webhook_url, payload)

    def send_info(self, message: str, title: str = "EOD Operational Update", details: Optional[Dict[str, Any]] = None) -> bool:
        """
        Sends an INFO level alert.
        Example: 'EOD Scan Initiated for 50 Nifty Universe...'
        """
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        now_ist_str = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)).strftime("%H:%M:%S IST")
        plain_text = f"ℹ️ **[INFO]** {message}"

        embed = {
            "title": f"ℹ️ {title}",
            "description": message,
            "color": COLOR_SKY_BLUE,
            "fields": [
                {"name": "Timestamp", "value": now_ist_str, "inline": True},
                {"name": "Execution Mode", "value": "PAPER TRADING (GATED)", "inline": True},
                {"name": "Account", "value": f"`{self.account_id}`", "inline": True},
            ],
            "footer": {
                "text": "Algo Lab Swing Trading Desk • Zero Live Broker Invariant Enforced"
            },
            "timestamp": now_utc,
        }

        if details:
            for k, v in details.items():
                embed["fields"].append({"name": str(k), "value": str(v), "inline": True})

        print(f"[NOTIFICATION INFO] {message}")

        sent_discord = self.send_raw_discord(plain_text, embed)
        sent_tg = self.send_raw_telegram(plain_text)
        return sent_discord or sent_tg or not self.has_active_webhook

    def send_trade_alert(
        self,
        action: str,
        symbol: str,
        quantity: int,
        price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        net_pnl: Optional[float] = None,
        gross_pnl: Optional[float] = None,
        exit_reason: Optional[str] = None,
        sector: Optional[str] = None,
        holding_period_days: Optional[int] = None,
        friction: Optional[float] = None,
    ) -> bool:
        """
        Sends an institutional formatted TRADE execution alert.
        BUY Example: '🟢 EXECUTION: BUY 10 RELIANCE @ ₹2500 | Stop: ₹2400 | Target: ₹2800'
        SELL Example: '🔴 EXECUTION: SELL 10 RELIANCE @ ₹2400 | Reason: STOP_LOSS_HIT | Net P&L: -₹1,000.00'
        """
        action = action.upper()
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        now_ist_str = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)).strftime("%H:%M:%S IST")

        if action == "BUY":
            emoji = "🟢"
            color = COLOR_EMERALD_GREEN
            stop_str = f"₹{stop_loss:,.2f}" if stop_loss is not None else "N/A"
            target_str = f"₹{take_profit:,.2f}" if take_profit is not None else "N/A"
            title = f"{emoji} EXECUTION: BUY {quantity} {symbol} @ ₹{price:,.2f}"
            plain_text = f"{emoji} **EXECUTION: BUY {quantity} {symbol} @ ₹{price:,.2f}** | Stop: {stop_str} | Target: {target_str}"

            fields = [
                {"name": "Symbol", "value": f"**{symbol}**", "inline": True},
                {"name": "Direction", "value": "LONG (CNC)", "inline": True},
                {"name": "Quantity", "value": str(quantity), "inline": True},
                {"name": "Entry Price", "value": f"₹{price:,.2f}", "inline": True},
                {"name": "Stop Loss (2.5×ATR)", "value": stop_str, "inline": True},
                {"name": "Target (3.5×Risk)", "value": target_str, "inline": True},
                {"name": "Sector", "value": sector or "GENERAL", "inline": True},
                {"name": "Allocated Capital", "value": f"₹{(quantity * price):,.2f}", "inline": True},
                {"name": "Execution Time", "value": now_ist_str, "inline": True},
            ]
        else:
            # SELL / Exit
            pnl_val = net_pnl if net_pnl is not None else 0.0
            is_profitable = pnl_val >= 0
            emoji = "🟢" if is_profitable else "🔴"
            color = COLOR_EMERALD_GREEN if is_profitable else COLOR_ROSE_RED
            pnl_formatted = f"+₹{pnl_val:,.2f}" if pnl_val > 0 else (f"-₹{abs(pnl_val):,.2f}" if pnl_val < 0 else "₹0.00")
            reason_str = exit_reason or "MANUAL_EXIT"

            title = f"{emoji} EXECUTION: SELL {quantity} {symbol} @ ₹{price:,.2f}"
            plain_text = f"{emoji} **EXECUTION: SELL {quantity} {symbol} @ ₹{price:,.2f}** | Reason: {reason_str} | Net P&L: {pnl_formatted}"

            fields = [
                {"name": "Symbol", "value": f"**{symbol}**", "inline": True},
                {"name": "Direction", "value": "CLOSE (DELIVERY)", "inline": True},
                {"name": "Quantity", "value": str(quantity), "inline": True},
                {"name": "Exit Price", "value": f"₹{price:,.2f}", "inline": True},
                {"name": "Exit Reason", "value": f"`{reason_str}`", "inline": True},
                {"name": "Net Realized P&L", "value": f"**{pnl_formatted}**", "inline": True},
                {"name": "Holding Period", "value": f"{holding_period_days or 1} day(s)", "inline": True},
                {"name": "Total Statutory Friction", "value": f"₹{friction:,.2f}" if friction is not None else "₹15.34+ DP", "inline": True},
                {"name": "Execution Time", "value": now_ist_str, "inline": True},
            ]

        embed = {
            "title": title,
            "description": f"Swing Trading Order Executed for Account `{self.account_id}`.",
            "color": color,
            "fields": fields,
            "footer": {
                "text": "Algo Lab Swing Engine • Product: DELIVERY (CNC) • ALLOW_LIVE_TRADING=FALSE"
            },
            "timestamp": now_utc,
        }

        print(f"[NOTIFICATION TRADE] {plain_text}")

        sent_discord = self.send_raw_discord(plain_text, embed)
        sent_tg = self.send_raw_telegram(plain_text)
        return sent_discord or sent_tg or not self.has_active_webhook

    def send_summary(
        self,
        active_positions_count: int,
        cash: float,
        equity: Optional[float] = None,
        net_pnl: Optional[float] = None,
        completed_trades_count: Optional[int] = None,
        market_date: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Sends an EOD session summary alert.
        Example: 'EOD Session Closed. Active Positions: 1 | Cash Solvency: ₹75,000.'
        """
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        now_ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
        date_str = market_date or now_ist.strftime("%Y-%m-%d")

        plain_text = f"📊 **EOD Session Closed. Active Positions: {active_positions_count} | Cash Solvency: ₹{cash:,.2f}**"
        if equity is not None:
            plain_text += f" | Equity: ₹{equity:,.2f}"
        if net_pnl is not None:
            pnl_formatted = f"+₹{net_pnl:,.2f}" if net_pnl > 0 else (f"-₹{abs(net_pnl):,.2f}" if net_pnl < 0 else "₹0.00")
            plain_text += f" | Realized P&L: {pnl_formatted}"

        fields = [
            {"name": "Session Date", "value": date_str, "inline": True},
            {"name": "Active Positions", "value": str(active_positions_count), "inline": True},
            {"name": "Cash Solvency", "value": f"₹{cash:,.2f}", "inline": True},
        ]
        if equity is not None:
            fields.append({"name": "Total Equity", "value": f"₹{equity:,.2f}", "inline": True})
        if net_pnl is not None:
            pnl_formatted = f"+₹{net_pnl:,.2f}" if net_pnl > 0 else (f"-₹{abs(net_pnl):,.2f}" if net_pnl < 0 else "₹0.00")
            fields.append({"name": "Net Realized P&L", "value": f"{pnl_formatted}", "inline": True})
        if completed_trades_count is not None:
            fields.append({"name": "Completed Trades", "value": str(completed_trades_count), "inline": True})

        fields.append({"name": "Overnight Holdings", "value": "Protected with 2.5×ATR Stops", "inline": True})
        fields.append({"name": "Next Session Wakeup", "value": "Next Trading Day @ 15:00 IST", "inline": True})

        embed = {
            "title": "🏛️ Algo Lab EOD Trading Session Summary",
            "description": f"End-of-day market cycle concluded for `{date_str}`. Portfolio state locked in SQLite overnight ledger.",
            "color": COLOR_AMBER,
            "fields": fields,
            "footer": {
                "text": f"Algo Lab Institutional Desk • {self.account_id} • ALLOW_LIVE_TRADING=FALSE"
            },
            "timestamp": now_utc,
        }

        if details:
            for k, v in details.items():
                embed["fields"].append({"name": str(k), "value": str(v), "inline": True})

        print(f"[NOTIFICATION SUMMARY] {plain_text}")

        sent_discord = self.send_raw_discord(plain_text, embed)
        sent_tg = self.send_raw_telegram(plain_text)
        return sent_discord or sent_tg or not self.has_active_webhook

    def send_test_notification(self) -> bool:
        """Dispatches a multi-stage test alert to verify webhook integration and phone push."""
        print("[NOTIFICATION ENGINE] Dispatching test alerts...")
        info_ok = self.send_info(
            message="EOD Scan Initiated for 50 Nifty Universe. Daily candle ingestion online.",
            title="System Verification Test"
        )
        trade_ok = self.send_trade_alert(
            action="BUY",
            symbol="RELIANCE.NS",
            quantity=10,
            price=2500.0,
            stop_loss=2400.0,
            take_profit=2800.0,
            sector="ENERGY_POWER"
        )
        summary_ok = self.send_summary(
            active_positions_count=1,
            cash=75000.0,
            equity=100500.0,
            net_pnl=500.0,
            completed_trades_count=1,
        )
        return info_ok or trade_ok or summary_ok or not self.has_active_webhook


# Convenience Aliases
NotificationEngine = DiscordWebhookNotifier
