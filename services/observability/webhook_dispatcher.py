"""
Algo Lab — Zero-Intervention Webhook Telemetry & Alerting Dispatcher.
Supports Discord, Telegram, and Slack incoming webhooks for fully autonomous trading.
Includes dedicated handlers for live trading calls (Stock Name, Entry, Exit, Target).
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import requests

logger = logging.getLogger("WebhookDispatcher")


class WebhookDispatcher:
    """Dispatches asynchronous alerts to Discord, Slack, or Telegram."""

    def __init__(
        self,
        discord_webhook_url: Optional[str] = None,
        slack_webhook_url: Optional[str] = None,
        telegram_bot_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
    ):
        self.discord_url = discord_webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
        self.slack_url = slack_webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        self.tg_token = telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.tg_chat_id = telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID")

        # Fallback to TELEGRAM_WEBHOOK_URL if token not in TELEGRAM_BOT_TOKEN
        if not self.tg_token and os.getenv("TELEGRAM_WEBHOOK_URL"):
            url = os.getenv("TELEGRAM_WEBHOOK_URL", "")
            if "/bot" in url:
                try:
                    self.tg_token = url.split("/bot")[1].split("/")[0]
                except Exception:
                    pass

        # Fallback to telegram-bridge config.json
        if not self.tg_token or not self.tg_chat_id:
            cfg_path = Path("/home/ubuntu/telegram-bridge/config.json")
            if cfg_path.exists():
                try:
                    with open(cfg_path) as f:
                        cfg = json.load(f)
                        self.tg_token = self.tg_token or cfg.get("bot_token")
                        self.tg_chat_id = self.tg_chat_id or str(cfg.get("admin_chat_id"))
                except Exception:
                    pass

    def notify(self, title: str, message: str, level: str = "INFO", fields: Optional[Dict[str, Any]] = None) -> bool:
        """Sends an autonomous notification to configured channels."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        text = f"**[{level}] {title}**\n{message}\n_Timestamp: {timestamp}_"
        
        if fields:
            field_lines = "\n".join([f"• **{k}**: {v}" for k, v in fields.items()])
            text += f"\n\n{field_lines}"

        sent = False
        # 1. Discord Webhook
        if self.discord_url:
            try:
                payload = {
                    "content": text[:1900],
                    "username": "AlgoLab Sentinel",
                }
                resp = requests.post(self.discord_url, json=payload, timeout=5)
                if resp.status_code in (200, 204):
                    sent = True
            except Exception as e:
                logger.warning(f"Discord webhook failed: {e}")

        # 2. Slack Webhook
        if self.slack_url:
            try:
                payload = {"text": text}
                resp = requests.post(self.slack_url, json=payload, timeout=5)
                if resp.status_code == 200:
                    sent = True
            except Exception as e:
                logger.warning(f"Slack webhook failed: {e}")

        # 3. Telegram Bot API
        if self.tg_token and self.tg_chat_id:
            try:
                url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
                payload = {
                    "chat_id": self.tg_chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                }
                resp = requests.post(url, json=payload, timeout=5)
                if resp.status_code == 200:
                    sent = True
            except Exception as e:
                logger.warning(f"Telegram alert failed: {e}")

        # Fallback to local structured log
        logger.info(f"[TELEMETRY {level}] {title} - {message}")
        return sent

    def notify_trade_entry(
        self,
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
        """Dispatches real-time Live Trading Call with Stock Name, Entry, Exit/SL, and Target."""
        try:
            from services.observability.trading_calls import broadcast_trade_entry
            return broadcast_trade_entry(
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
        except Exception as e:
            logger.warning(f"Failed to broadcast trade entry via trading_calls: {e}")
            fields = {
                "Stock": symbol,
                "Action": action,
                "Entry": f"₹{entry_price:,.2f}",
                "Stop Loss": f"₹{stop_loss:,.2f}",
                "Target": f"₹{target_price:,.2f}",
                "Quantity": str(quantity),
            }
            return self.notify(f"LIVE CALL: {action} {symbol}", f"Entry: ₹{entry_price:,.2f} | SL: ₹{stop_loss:,.2f} | TP: ₹{target_price:,.2f}", fields=fields)

    def notify_trade_exit(
        self,
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
        """Dispatches real-time Live Trading Call Exit with Stock Name, Entry, Exit, Target, and P&L."""
        try:
            from services.observability.trading_calls import broadcast_trade_exit
            return broadcast_trade_exit(
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
        except Exception as e:
            logger.warning(f"Failed to broadcast trade exit via trading_calls: {e}")
            fields = {
                "Stock": symbol,
                "Entry": f"₹{entry_price:,.2f}",
                "Exit": f"₹{exit_price:,.2f}",
                "Target": f"₹{target_price:,.2f}",
                "Net P&L": f"₹{pnl:,.2f}",
                "Reason": reason,
            }
            return self.notify(f"TRADE CLOSED: {symbol} ({reason})", f"Exit at ₹{exit_price:,.2f} | PnL: ₹{pnl:,.2f}", fields=fields)

    def notify_trailing_sl(
        self,
        symbol: str,
        entry_price: float,
        old_sl: float,
        new_sl: float,
        target_price: float,
        current_price: float,
        notes: str = "Breakeven Locked",
    ) -> bool:
        """Dispatches real-time notification when Stop Loss is ratcheted."""
        try:
            from services.observability.trading_calls import broadcast_trailing_sl
            return broadcast_trailing_sl(
                symbol=symbol,
                entry_price=entry_price,
                old_sl=old_sl,
                new_sl=new_sl,
                target_price=target_price,
                current_price=current_price,
                notes=notes,
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast trailing SL: {e}")
            return False


if __name__ == "__main__":
    dispatcher = WebhookDispatcher()
    dispatcher.notify("Test Ping", "Algo Lab Telemetry Dispatcher Online", level="INFO")
    print("WebhookDispatcher initialized successfully.")
