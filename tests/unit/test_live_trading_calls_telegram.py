"""
Unit tests for Live Trading Calls Telegram Broadcaster & WebhookDispatcher
Verifies formatting of Stock Name, Entry, Exit, Target, Stop-Loss, and fail-safe dispatch.
"""

import os
import json
import pytest
from unittest.mock import patch, MagicMock
from services.observability.trading_calls import (
    format_live_entry_call,
    format_live_exit_call,
    format_trailing_sl_call,
    format_active_calls_summary,
    broadcast_trade_entry,
    broadcast_trade_exit,
    broadcast_trailing_sl,
)
from services.observability.webhook_dispatcher import WebhookDispatcher


def test_format_live_entry_call_contains_required_fields():
    msg = format_live_entry_call(
        symbol="TCS",
        action="BUY",
        entry_price=3500.0,
        stop_loss=3465.0,
        target_price=3570.0,
        quantity=10,
        allocated_margin=35000.0,
        strategy="Intraday ORB",
        segment="INTRADAY (MIS)",
    )
    assert "TCS" in msg
    assert "BUY" in msg
    assert "₹3,500.00" in msg
    assert "Target Price" in msg
    assert "₹3,570.00" in msg
    assert "Exit / Stop Loss" in msg
    assert "₹3,465.00" in msg
    assert "Quantity:</b> 10 shares" in msg


def test_format_live_exit_call_contains_required_fields():
    msg = format_live_exit_call(
        symbol="INFY",
        action="SELL",
        entry_price=1000.0,
        exit_price=1020.0,
        stop_loss=990.0,
        target_price=1020.0,
        quantity=20,
        pnl=400.0,
        return_pct=2.0,
        reason="TARGET_HIT",
        segment="INTRADAY (MIS)",
        friction=12.50,
    )
    assert "INFY" in msg
    assert "SELL" in msg
    assert "TARGET_HIT" in msg
    assert "Entry Price:</b> ₹1,000.00" in msg
    assert "Exit Price:</b> <b>₹1,020.00</b>" in msg
    assert "Original Target:</b> ₹1,020.00" in msg
    assert "Net P&L:</b> <b>₹+400.00</b>" in msg


def test_format_trailing_sl_call():
    msg = format_trailing_sl_call(
        symbol="RELIANCE",
        entry_price=2800.0,
        old_sl=2760.0,
        new_sl=2805.0,
        target_price=2880.0,
        current_price=2845.0,
    )
    assert "RELIANCE" in msg
    assert "₹2,805.00" in msg
    assert "Target Price:</b> ₹2,880.00" in msg


@patch("requests.post")
def test_broadcast_trade_entry_network_mock(mock_post):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"ok": True, "result": {"message_id": 101}}
    mock_post.return_value = mock_resp

    success = broadcast_trade_entry(
        symbol="SBIN",
        action="BUY",
        entry_price=800.0,
        stop_loss=790.0,
        target_price=820.0,
        quantity=50,
    )
    assert success is True
    assert mock_post.called


@patch("requests.post")
def test_webhook_dispatcher_notify_trade_methods(mock_post):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"ok": True, "result": {"message_id": 102}}
    mock_post.return_value = mock_resp

    dispatcher = WebhookDispatcher()
    res_entry = dispatcher.notify_trade_entry(
        symbol="HDFCBANK",
        action="BUY",
        entry_price=1600.0,
        stop_loss=1580.0,
        target_price=1640.0,
        quantity=15,
    )
    assert res_entry is True

    res_exit = dispatcher.notify_trade_exit(
        symbol="HDFCBANK",
        action="SELL",
        entry_price=1600.0,
        exit_price=1640.0,
        stop_loss=1580.0,
        target_price=1640.0,
        quantity=15,
        pnl=600.0,
        reason="TARGET_HIT",
    )
    assert res_exit is True

    res_cancel = dispatcher.notify_trade_cancelled(
        symbol="HDFCBANK",
        action="BUY",
        entry_price=1600.0,
        reason="ORDER_TIMEOUT_EXPIRED",
        freed_margin=24000.0,
    )
    assert res_cancel is True


def test_format_live_entry_call_with_conviction_and_consensus():
    from services.observability.trading_calls import format_live_entry_call

    msg = format_live_entry_call(
        symbol="BAJFINANCE",
        action="BUY",
        entry_price=7200.0,
        stop_loss=7120.0,
        target_price=7380.0,
        quantity=5,
        confidence_score=0.91,
        regime="BULL_MOMENTUM",
        setup_factors={"Regime Alignment": "94%", "Volume": "2.8x EMA"},
        agent_consensus="✅ UNANIMOUS (92.5%) | Hermes • OpenClaw • Antigravity",
    )
    assert "BAJFINANCE" in msg
    assert "Conviction:" in msg
    assert "⭐⭐⭐⭐⭐" in msg
    assert "91.0%" in msg
    assert "ULTRA-HIGH CONVICTION" in msg
    assert "BULL_MOMENTUM" in msg
    assert "Setup Factors:" in msg
    assert "Multi-Agent Vote:" in msg
    assert "UNANIMOUS" in msg


def test_format_live_cancellation_call():
    from services.observability.trading_calls import format_live_cancellation_call

    msg = format_live_cancellation_call(
        symbol="WIPRO",
        action="BUY",
        entry_price=540.0,
        reason="ORDER_TIMEOUT_EXPIRED",
        freed_margin=10800.0,
        notes="Unfilled after 30 mins, entry invalidated",
    )
    assert "WIPRO" in msg
    assert "CANCELLED / EXPIRED" in msg
    assert "ORDER_TIMEOUT_EXPIRED" in msg
    assert "Capital Freed:" in msg
    assert "₹10,800.00" in msg
    assert "Unfilled after 30 mins" in msg


@patch("requests.post")
def test_broadcast_trade_cancelled_network_mock(mock_post):
    from services.observability.trading_calls import broadcast_trade_cancelled

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"ok": True, "result": {"message_id": 103}}
    mock_post.return_value = mock_resp

    success = broadcast_trade_cancelled(
        symbol="ICICIBANK",
        action="BUY",
        entry_price=1250.0,
        reason="REGIME_INVALIDATED",
        freed_margin=25000.0,
    )
    assert success is True
    assert mock_post.called


def test_agent_consensus_engine_unanimous():
    from services.orchestrator.agent_consensus import AgentConsensusEngine

    engine = AgentConsensusEngine()
    verdict = engine.run_consensus(
        symbol="RELIANCE",
        action="BUY",
        entry_price=2800.0,
        stop_loss=2780.0,  # 20 pts risk * 5 shares = 100 risk <= 150
        target_price=2850.0,  # 50 pts reward -> R:R 2.5
        quantity=5,
        capital=10000.0,
        regime="BULL_MOMENTUM",
        adx=32.0,
        india_vix=13.5,
    )
    assert verdict.status == "APPROVED"
    assert verdict.unanimous is True
    assert verdict.composite_score >= 0.80
    assert "Hermes" in verdict.votes
    assert "OpenClaw" in verdict.votes
    assert "Antigravity" in verdict.votes
    assert "UNANIMOUS" in verdict.summary


def test_agent_consensus_engine_veto_rejection():
    from services.orchestrator.agent_consensus import AgentConsensusEngine

    engine = AgentConsensusEngine()
    # Violates OpenClaw Max Risk Invariant #2: risk is 200 pts * 10 = 2000 INR >> 150 INR
    verdict = engine.run_consensus(
        symbol="RELIANCE",
        action="BUY",
        entry_price=2800.0,
        stop_loss=2600.0,  # Risk = 200 * 10 = 2000 INR
        target_price=2900.0,
        quantity=10,
        capital=10000.0,
        regime="BULL_MOMENTUM",
        max_risk_inr=150.0,
    )
    assert verdict.status == "REJECTED"
    assert verdict.unanimous is False
    assert "OpenClaw" in verdict.summary
    assert verdict.votes["OpenClaw"]["status"] == "REJECTED"

