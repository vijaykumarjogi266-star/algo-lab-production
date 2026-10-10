"""
OMS Project - Central Data Feed Test Suite
Tests for WebSocket connectivity, backoff reconnection, tick normalization (UTC ISO format),
Redis broadcast latency (<50ms limit), and Stale Heartbeat Fail-Closed trade rejection.
"""

import time
import pytest
from datetime import datetime, timezone
from oms_project.central_data_feed import MarketDataService
from oms_project.schemas import OrderIntent, OrderSide, OrderResult, OrderState
from oms_project.gateway import BrokerGateway


def test_connectivity_and_reconnect_logic():
    """Verify WebSocket initial connection and exponential backoff retry counter."""
    feed = MarketDataService(redis_host="localhost", redis_port=6379)
    assert not feed.is_connected

    # Connection attempt
    success = feed.connect_with_backoff(max_retries=3)
    assert success is True
    assert feed.is_connected is True
    assert feed.reconnect_attempts == 0


def test_tick_normalization_utc_iso():
    """Verify raw exchange JSON is normalized with strict UTC ISO timestamp and monotonic sequence."""
    feed = MarketDataService()
    feed.connect_with_backoff()

    raw_tick_1 = {
        "symbol": "reliance",
        "price": "1250.75",
        "volume": "100",
        "timestamp": 1700000000.0,
    }

    raw_tick_2 = {
        "s": "nifty",
        "p": "24100.0",
        "v": "25",
        "t": 1700000010.0,
    }

    tick1 = feed.normalize_raw_tick(raw_tick_1)
    assert tick1.symbol == "RELIANCE"
    assert tick1.price == 1250.75
    assert tick1.volume == 100.0
    assert tick1.timestamp == 1700000000.0
    assert tick1.sequence == 1
    # Verify UTC ISO string format
    expected_iso = datetime.fromtimestamp(1700000000.0, tz=timezone.utc).isoformat()
    assert tick1.utc_iso == expected_iso

    tick2 = feed.normalize_raw_tick(raw_tick_2)
    assert tick2.symbol == "NIFTY"
    assert tick2.price == 24100.0
    assert tick2.sequence == 2


def test_broadcast_latency_delta():
    """Verify Redis broadcast latency is recorded and delta is under 50ms threshold."""
    feed = MarketDataService()
    feed.connect_with_backoff()

    received_ticks = []

    def on_reliance_tick(tick):
        received_ticks.append(tick)

    feed.subscribe_market_data("RELIANCE", on_reliance_tick)

    current_ts = time.time()
    raw_payload = {
        "symbol": "RELIANCE",
        "price": 1205.0,
        "volume": 50,
        "timestamp": current_ts,
    }

    normalized_tick, latency_ms = feed.publish_tick_broadcast(raw_payload)

    # Latency should be under 50ms for freshly generated ticks
    assert latency_ms < 50.0
    assert len(received_ticks) == 1
    assert received_ticks[0].symbol == "RELIANCE"
    assert received_ticks[0].price == 1205.0
    assert len(feed.broadcast_log) == 1
    assert feed.broadcast_log[0]["channel"] == "market_data:RELIANCE"


def test_stale_heartbeat_halt_integration():
    """Verify Fail-Closed Halt: Broker Gateway rejects trades when market data feed/heartbeat is stale (>500ms)."""
    feed = MarketDataService()
    gateway = BrokerGateway(db_path=":memory:", max_market_data_staleness_ms=500.0)

    # Wire MarketDataService to BrokerGateway reference prices & timestamps
    def sync_gateway_market_data(tick):
        gateway.set_market_price(tick.symbol, tick.price, tick.timestamp)

    feed.subscribe_market_data("RELIANCE", sync_gateway_market_data)

    # 1. Publish fresh tick and heartbeat
    fresh_ts = time.time()
    feed.publish_tick_broadcast({
        "symbol": "RELIANCE",
        "price": 1200.0,
        "volume": 10,
        "timestamp": fresh_ts,
    })
    feed.emit_system_heartbeat()

    # Create valid order intent
    intent = OrderIntent(
        request_id="REQ_FEED_001",
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=10.0,
        price=1200.0,
        timestamp=fresh_ts,
        signature="test_signature_valid",
    )

    # Fresh market data: Order execution should succeed
    res_success = gateway.process_order_intent(intent)
    assert res_success.status == OrderState.FILLED

    # 2. Simulate heartbeat / feed stoppage (staleness > 500ms)
    stale_ts = time.time() - 0.600  # 600ms ago (exceeds 500ms max staleness)
    gateway.set_market_price("RELIANCE", 1200.0, timestamp=stale_ts)

    intent_stale = OrderIntent(
        request_id="REQ_FEED_002",
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=10.0,
        price=1200.0,
        timestamp=time.time(),
        signature="test_signature_valid",
    )

    # Stale market data: Gateway Fail-Closed Guard must REJECT the order
    res_stale = gateway.process_order_intent(intent_stale)
    assert res_stale.status == OrderState.REJECTED
    assert "REJECTED_STALE_MARKET_DATA" in res_stale.message
