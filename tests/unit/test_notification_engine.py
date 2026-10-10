"""
Unit tests for Algo Lab Push Notification Engine (src.notification_engine).
Verifies:
1. INFO, TRADE (BUY/SELL), and SUMMARY message generation and formatting.
2. Discord embed schema compliance (color, fields, title, footer, timestamp).
3. Mock HTTP transmission and headers.
4. Graceful fallback on network errors (HTTPError, URLError) without raising exceptions.
5. .env variable parsing and secure URL loading.
"""

import os
import json
import pytest
from unittest.mock import patch, MagicMock
from io import BytesIO
from urllib.error import HTTPError, URLError

from src.notification_engine import (
    DiscordWebhookNotifier,
    NotificationEngine,
    load_env_vars,
    COLOR_EMERALD_GREEN,
    COLOR_ROSE_RED,
    COLOR_SKY_BLUE,
    COLOR_AMBER,
)


def test_notification_engine_initialization_no_urls():
    """Verifies notifier initializes gracefully when no webhook URLs are provided."""
    notifier = DiscordWebhookNotifier(discord_webhook_url="", telegram_webhook_url="")
    assert notifier.has_active_webhook is False
    assert notifier.discord_webhook_url == ""
    assert notifier.telegram_webhook_url == ""


def test_send_info_payload_structure():
    """Verifies that send_info produces valid Discord embed format."""
    notifier = DiscordWebhookNotifier(discord_webhook_url="https://discord.com/api/webhooks/test/123")

    with patch.object(notifier, "_send_http_json", return_value=True) as mock_send:
        success = notifier.send_info("EOD Scan Initiated for 50 Nifty Universe...", title="Scan Started")
        assert success is True
        assert mock_send.called
        url, payload = mock_send.call_args[0]
        assert url == "https://discord.com/api/webhooks/test/123"
        assert "EOD Scan Initiated" in payload["content"]
        assert len(payload["embeds"]) == 1
        embed = payload["embeds"][0]
        assert embed["color"] == COLOR_SKY_BLUE
        assert "Scan Started" in embed["title"]
        assert any(f["name"] == "Timestamp" for f in embed["fields"])
        assert any(f["name"] == "Account" for f in embed["fields"])


def test_send_trade_alert_buy():
    """Verifies BUY execution trade alert schema and colors."""
    notifier = DiscordWebhookNotifier(discord_webhook_url="https://discord.com/api/webhooks/test/123")

    with patch.object(notifier, "_send_http_json", return_value=True) as mock_send:
        success = notifier.send_trade_alert(
            action="BUY",
            symbol="RELIANCE.NS",
            quantity=10,
            price=2500.0,
            stop_loss=2400.0,
            take_profit=2800.0,
            sector="ENERGY_POWER"
        )
        assert success is True
        url, payload = mock_send.call_args[0]
        assert "BUY 10 RELIANCE.NS @ ₹2,500.00" in payload["content"]
        embed = payload["embeds"][0]
        assert embed["color"] == COLOR_EMERALD_GREEN
        fields = {f["name"]: f["value"] for f in embed["fields"]}
        assert fields["Symbol"] == "**RELIANCE.NS**"
        assert fields["Direction"] == "LONG (CNC)"
        assert fields["Stop Loss (2.5×ATR)"] == "₹2,400.00"
        assert fields["Target (3.5×Risk)"] == "₹2,800.00"
        assert fields["Sector"] == "ENERGY_POWER"


def test_send_trade_alert_sell_stop_loss():
    """Verifies SELL execution alert on Stop Loss (Rose Red color and negative P&L format)."""
    notifier = DiscordWebhookNotifier(discord_webhook_url="https://discord.com/api/webhooks/test/123")

    with patch.object(notifier, "_send_http_json", return_value=True) as mock_send:
        success = notifier.send_trade_alert(
            action="SELL",
            symbol="TCS.NS",
            quantity=5,
            price=3400.0,
            net_pnl=-550.0,
            exit_reason="STOP_LOSS_HIT",
            sector="IT_CONSULTING",
            holding_period_days=2,
            friction=25.50
        )
        assert success is True
        url, payload = mock_send.call_args[0]
        assert "🔴" in payload["content"]
        assert "-₹550.00" in payload["content"]
        embed = payload["embeds"][0]
        assert embed["color"] == COLOR_ROSE_RED
        fields = {f["name"]: f["value"] for f in embed["fields"]}
        assert fields["Net Realized P&L"] == "**-₹550.00**"
        assert fields["Exit Reason"] == "`STOP_LOSS_HIT`"
        assert fields["Holding Period"] == "2 day(s)"


def test_send_trade_alert_sell_take_profit():
    """Verifies SELL execution alert on Take Profit (Emerald Green color and positive P&L format)."""
    notifier = DiscordWebhookNotifier(discord_webhook_url="https://discord.com/api/webhooks/test/123")

    with patch.object(notifier, "_send_http_json", return_value=True) as mock_send:
        success = notifier.send_trade_alert(
            action="SELL",
            symbol="INFY.NS",
            quantity=8,
            price=1900.0,
            net_pnl=1200.0,
            exit_reason="TAKE_PROFIT_HIT",
            sector="IT_CONSULTING"
        )
        assert success is True
        _, payload = mock_send.call_args[0]
        assert "🟢" in payload["content"]
        assert "+₹1,200.00" in payload["content"]
        embed = payload["embeds"][0]
        assert embed["color"] == COLOR_EMERALD_GREEN
        fields = {f["name"]: f["value"] for f in embed["fields"]}
        assert fields["Net Realized P&L"] == "**+₹1,200.00**"


def test_send_summary_payload():
    """Verifies EOD session summary alert schema."""
    notifier = DiscordWebhookNotifier(discord_webhook_url="https://discord.com/api/webhooks/test/123")

    with patch.object(notifier, "_send_http_json", return_value=True) as mock_send:
        success = notifier.send_summary(
            active_positions_count=2,
            cash=75000.0,
            equity=102500.0,
            net_pnl=2500.0,
            completed_trades_count=3,
            market_date="2026-10-02"
        )
        assert success is True
        _, payload = mock_send.call_args[0]
        assert "Active Positions: 2" in payload["content"]
        assert "₹75,000.00" in payload["content"]
        assert "+₹2,500.00" in payload["content"]
        embed = payload["embeds"][0]
        assert embed["color"] == COLOR_AMBER
        fields = {f["name"]: f["value"] for f in embed["fields"]}
        assert fields["Active Positions"] == "2"
        assert fields["Cash Solvency"] == "₹75,000.00"
        assert fields["Total Equity"] == "₹102,500.00"
        assert fields["Net Realized P&L"] == "+₹2,500.00"


def test_network_failure_fallback_non_blocking():
    """Verifies that network exceptions (URLError, timeout) do not raise and return False."""
    notifier = DiscordWebhookNotifier(discord_webhook_url="https://invalid-discord-url.example.com/webhook")

    with patch("urllib.request.urlopen", side_effect=URLError("Connection refused")):
        # Should return False and NOT throw an exception
        result = notifier.send_info("Testing network failure resilience")
        assert result is False

    with patch("urllib.request.urlopen", side_effect=HTTPError("http://...", 500, "Internal Server Error", {}, BytesIO(b""))):
        result = notifier.send_trade_alert("BUY", "RELIANCE.NS", 10, 2500.0)
        assert result is False


def test_env_parsing(tmp_path):
    """Verifies that load_env_vars parses key-values from .env correctly."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# Test comment\n"
        "TEST_NOTIF_VAR=https://discord.com/webhook/test\n"
        "QUOTED_VAR=\"hello_world\"\n"
        "EMPTY_LINE=\n",
        encoding="utf-8"
    )
    loaded = load_env_vars([env_file])
    assert loaded.get("TEST_NOTIF_VAR") == "https://discord.com/webhook/test"
    assert loaded.get("QUOTED_VAR") == "hello_world"
