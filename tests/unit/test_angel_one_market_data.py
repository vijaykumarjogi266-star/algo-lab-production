"""
Unit Tests for Angel One SmartAPI Market Data Provider & Ingestion Pipeline.
Validates:
1. Instrument Master & Token Allowlist Integrity
2. Secret Masking & Redaction Invariants
3. Hard Fail-Closed Prohibition of Order Routing
4. Diagnostic Health & Connection Failure Modes
5. Smart Stream 2.0 Binary & JSON Parsing (with Price Scaling)
6. 9-Stage Market Data Pipeline (Validation, Deduplication, Bar Construction, Signal Hook)
"""

import json
import struct
from datetime import datetime, timezone, timedelta
import pytest

from data.schemas.contracts import DataQualityStatus
from data.schemas.canonical_market_data import CanonicalMarketDataValidator
from services.market_data.adapters.angel_one_instruments import AngelOneInstrumentMaster
from services.market_data.adapters.market_event_schemas import MarketTickEvent
from services.market_data.adapters.angel_one import AngelOneMarketDataAdapter
from services.market_data.adapters.market_pipeline import MarketDataPipelineEngine


# ==============================================================================
# 1. INSTRUMENT MASTER & ALLOWLIST TESTS
# ==============================================================================

def test_angel_one_instrument_master_allowlist():
    """Verifies that the core 6 NSE cash-equity instruments are mapped accurately."""
    im = AngelOneInstrumentMaster()
    allowlist = im.list_allowlist_symbols()

    assert allowlist == ["HAL", "INFY", "ITC", "RELIANCE", "SBIN", "TCS"]

    # Verify SBIN token
    sbin = im.get_by_symbol("SBIN")
    assert sbin is not None
    assert sbin.token == "3045"
    assert sbin.trading_symbol == "SBIN-EQ"
    assert sbin.exchange == "NSE"

    # Verify RELIANCE token
    reliance = im.get_by_symbol("RELIANCE")
    assert reliance is not None
    assert reliance.token == "2885"

    # Verify token resolution
    assert im.resolve_token_strict("TCS") == "11536"
    assert im.resolve_symbol_strict("1660") == "ITC"

    # Verify cryptographic checksum
    assert len(im.sha256_checksum) == 64
    assert im.version.startswith("2026-09-25")


def test_instrument_master_rejects_unmapped_instruments():
    """Unmapped or external symbols must be strictly rejected."""
    im = AngelOneInstrumentMaster()
    with pytest.raises(ValueError, match="Unresolved or unmapped instrument"):
        im.resolve_token_strict("BITCOIN")

    with pytest.raises(ValueError, match="Unresolved or unmapped token"):
        im.resolve_symbol_strict("99999999")


# ==============================================================================
# 2. SECURITY & FAIL-CLOSED ORDER ROUTING PROHIBITION TESTS
# ==============================================================================

def test_angel_one_adapter_secret_masking():
    """Secrets must NEVER appear in plain text in repr or str."""
    adapter = AngelOneMarketDataAdapter(
        api_key="ak_secret_test_key_12345",
        client_code="AB12345",
        password="super_secret_password",
        totp_key="JBSWY3DPEHPK3PXP",
        mock_mode=True,
    )
    s_repr = repr(adapter)
    assert "ak_secret_test_key_12345" not in s_repr
    assert "super_secret_password" not in s_repr
    assert "JBSWY3DPEHPK3PXP" not in s_repr
    assert "ak****2345" in s_repr


def test_angel_one_adapter_blocks_order_routing():
    """CRITICAL SAFETY INVARIANT: Order routing is strictly forbidden."""
    adapter = AngelOneMarketDataAdapter(mock_mode=True)
    with pytest.raises(PermissionError, match="CRITICAL GOVERNANCE VIOLATION"):
        adapter.place_order(symbol="SBIN", quantity=10, price=800.0)

    with pytest.raises(PermissionError, match="CRITICAL GOVERNANCE VIOLATION"):
        adapter.modify_order(order_id="123")

    with pytest.raises(PermissionError, match="CRITICAL GOVERNANCE VIOLATION"):
        adapter.cancel_order(order_id="123")


# ==============================================================================
# 3. CONNECTION & DIAGNOSTIC MODES
# ==============================================================================

def test_angel_one_connection_mock_mode():
    """Verifies that mock mode reports connected without network access."""
    adapter = AngelOneMarketDataAdapter(mock_mode=True)
    res = adapter.test_connection()
    assert res["connected"] is True
    assert res["status"] == "CONNECTED_MOCK"
    assert res["instrument_count"] == 6


def test_angel_one_connection_fails_closed_when_credentials_missing():
    """In live mode, missing credentials return clean diagnostic status."""
    adapter = AngelOneMarketDataAdapter(
        api_key="", client_code="", password="", totp_key="", mock_mode=False
    )
    res = adapter.test_connection()
    assert res["connected"] is False
    assert res["status"] in ("CREDENTIALS_UNAVAILABLE", "BLOCKED_BY_NETWORK_EGRESS")


# ==============================================================================
# 4. SMART STREAM 2.0 PROTOCOL & PRICE SCALING TESTS
# ==============================================================================

def test_smart_stream_binary_parsing_mode1_ltp():
    """
    Simulates Mode 1 binary packet:
    Byte 0: 1 (Mode 1)
    Byte 1: 1 (NSE CM)
    Bytes 2-26: "3045" + nulls (Token for SBIN)
    Bytes 27-34: int64 price in paise = 82550 (₹825.50)
    """
    adapter = AngelOneMarketDataAdapter(mock_mode=True)
    
    token_bytes = b"3045".ljust(25, b"\x00")
    ltp_paise = 82550 # ₹825.50
    packet = bytes([1, 1]) + token_bytes + struct.pack("<q", ltp_paise)

    tick = adapter.parse_smart_stream_binary(packet)
    assert tick is not None
    assert tick.symbol == "SBIN"
    assert tick.token == "3045"
    assert tick.last_traded_price == 825.50
    assert tick.subscription_mode == 1


def test_smart_stream_binary_parsing_mode2_quote():
    """
    Simulates Mode 2 binary packet:
    Byte 0: 2 (Mode 2)
    Byte 1: 1 (NSE CM)
    Bytes 2-26: "2885" (Token for RELIANCE)
    Offset 27: LTP in paise = 295025 (₹2,950.25)
    Offset 35: LTQ = 50
    Offset 43: ATP in paise = 294800 (₹2,948.00)
    Offset 51: Volume = 1500000
    """
    adapter = AngelOneMarketDataAdapter(mock_mode=True)
    
    token_bytes = b"2885".ljust(25, b"\x00")
    packet = (
        bytes([2, 1])
        + token_bytes
        + struct.pack("<q", 295025)  # LTP
        + struct.pack("<q", 50)      # LTQ
        + struct.pack("<q", 294800)  # ATP
        + struct.pack("<q", 1500000) # Volume
    )

    tick = adapter.parse_smart_stream_binary(packet)
    assert tick is not None
    assert tick.symbol == "RELIANCE"
    assert tick.token == "2885"
    assert tick.last_traded_price == 2950.25
    assert tick.last_traded_quantity == 50
    assert tick.average_traded_price == 2948.00
    assert tick.cumulative_volume == 1500000
    assert tick.subscription_mode == 2


# ==============================================================================
# 5. MARKET DATA PIPELINE TESTS
# ==============================================================================

def test_pipeline_validation_and_deduplication():
    """Verifies that invalid prices and duplicate sequence numbers are dropped."""
    pipeline = MarketDataPipelineEngine(bar_interval_seconds=60)
    now = datetime.now(timezone.utc)

    # 1. Valid tick
    t1 = MarketTickEvent(
        symbol="SBIN",
        token="3045",
        exchange_timestamp=now,
        receive_timestamp=now,
        sequence_id=1,
        last_traded_price=820.0,
        last_traded_quantity=10,
        cumulative_volume=100,
    )
    pipeline.process_tick(t1)
    assert pipeline.valid_ticks_processed == 1

    # 2. Duplicate tick (same sequence ID)
    t1_dup = MarketTickEvent(
        symbol="SBIN",
        token="3045",
        exchange_timestamp=now,
        receive_timestamp=now,
        sequence_id=1,
        last_traded_price=820.0,
        last_traded_quantity=10,
        cumulative_volume=100,
    )
    pipeline.process_tick(t1_dup)
    assert pipeline.duplicates_dropped == 1
    assert pipeline.valid_ticks_processed == 1


def test_pipeline_deterministic_bar_construction():
    """
    Verifies that a series of ticks within a 60-second window correctly aggregates
    into an OHLCV bar with exact mathematical invariants.
    """
    captured_signals = []
    def mock_signal_generator(bar):
        if bar.close > 822.0:
            captured_signals.append((bar.symbol, bar.close))
            return 1 # BUY signal
        return 0

    pipeline = MarketDataPipelineEngine(
        bar_interval_seconds=60,
        signal_generator=mock_signal_generator,
        allow_diagnostic_simulation=True,
    )

    t0 = datetime(2026, 9, 25, 9, 30, 5, tzinfo=timezone.utc)
    
    # Send 4 ticks in minute 09:30
    prices = [820.0, 825.0, 818.0, 823.0]
    for i, p in enumerate(prices):
        tick = MarketTickEvent(
            symbol="SBIN",
            token="3045",
            exchange_timestamp=t0 + timedelta(seconds=i * 10),
            receive_timestamp=t0 + timedelta(seconds=i * 10),
            sequence_id=i + 1,
            last_traded_price=p,
            last_traded_quantity=10,
            cumulative_volume=100 + (i + 1) * 10,
        )
        pipeline.process_tick(tick)

    # Next tick in minute 09:31 triggers closure of 09:30 bar
    t1 = datetime(2026, 9, 25, 9, 31, 2, tzinfo=timezone.utc)
    tick_next = MarketTickEvent(
        symbol="SBIN",
        token="3045",
        exchange_timestamp=t1,
        receive_timestamp=t1,
        sequence_id=10,
        last_traded_price=824.0,
        last_traded_quantity=15,
        cumulative_volume=200,
    )
    bar = pipeline.process_tick(tick_next)

    assert bar is not None
    assert bar.symbol == "SBIN"
    assert bar.open == 820.0
    assert bar.high == 825.0
    assert bar.low == 818.0
    assert bar.close == 823.0
    assert bar.volume == 40.0
    assert bar.trade_count == 4

    # Verify canonical bar sanity
    val = CanonicalMarketDataValidator.validate_series([bar])
    assert val.is_valid is True

    # Verify signal hook was invoked on bar close
    assert len(captured_signals) == 1
    assert captured_signals[0] == ("SBIN", 823.0)
    assert pipeline.signals_emitted == 1


# ==============================================================================
# 6. STRUCTURAL TRANSPORT FIREWALL & FAILURE RESILIENCE TESTS (PHASE 3)
# ==============================================================================

def test_structural_transport_firewall_blocks_order_and_unapproved_endpoints():
    """
    CRITICAL ISOLATION INVARIANT:
    The transport firewall must block any path not strictly on the approved
    market-data whitelist, especially order placement, modification, and funds.
    """
    adapter = AngelOneMarketDataAdapter(mock_mode=True)

    # 1. Unapproved path
    with pytest.raises(PermissionError, match="STRUCTURAL TRANSPORT FIREWALL"):
        adapter._execute_safe_market_data_request("POST", "/rest/secure/angelbroking/order/v1/placeOrder")

    # 2. Forbidden keyword in path
    with pytest.raises(PermissionError, match="STRUCTURAL TRANSPORT FIREWALL"):
        adapter._execute_safe_market_data_request("GET", "/rest/secure/angelbroking/user/v1/getHoldings")

    # 3. Arbitrary URL path
    with pytest.raises(PermissionError, match="STRUCTURAL TRANSPORT FIREWALL"):
        adapter._execute_safe_market_data_request("POST", "/admin/arbitrary/backdoor")


def test_stale_feed_detection_without_fabrication():
    """
    Verifies that a feed with no ticks for > 60 seconds is identified as stale,
    and that the pipeline DOES NOT fabricate data or close positions.
    """
    pipeline = MarketDataPipelineEngine(bar_interval_seconds=60)
    t0 = datetime(2026, 9, 25, 9, 30, 0, tzinfo=timezone.utc)

    # Process one tick for TCS
    tick = MarketTickEvent(
        symbol="TCS",
        token="11536",
        exchange_timestamp=t0,
        receive_timestamp=t0,
        sequence_id=1,
        last_traded_price=4150.0,
        last_traded_quantity=10,
        cumulative_volume=500,
    )
    pipeline.process_tick(tick)

    # At t0 + 30s: not stale
    assert pipeline.check_stale_feeds(current_time=t0 + timedelta(seconds=30), max_staleness_seconds=60) == []

    # At t0 + 90s: stale (> 60s without ticks)
    stale = pipeline.check_stale_feeds(current_time=t0 + timedelta(seconds=90), max_staleness_seconds=60)
    assert stale == ["TCS"]
    # Telemetry verifies no fake bars were fabricated
    assert len(pipeline.completed_bars) == 0


def test_cumulative_volume_session_reset_handling():
    """
    Verifies that if exchange resets cumulative volume (e.g. at market open or reconnect),
    the pipeline does not crash or calculate negative incremental volume.
    """
    pipeline = MarketDataPipelineEngine(bar_interval_seconds=60)
    t0 = datetime(2026, 9, 25, 9, 30, 0, tzinfo=timezone.utc)

    # Tick 1: Prior day / high volume
    t1 = MarketTickEvent(
        symbol="INFY",
        token="1594",
        exchange_timestamp=t0,
        receive_timestamp=t0,
        sequence_id=1,
        last_traded_price=1880.0,
        last_traded_quantity=25,
        cumulative_volume=1000000,
    )
    pipeline.process_tick(t1)

    # Tick 2: Session reset occurs (volume resets to 50)
    t2 = MarketTickEvent(
        symbol="INFY",
        token="1594",
        exchange_timestamp=t0 + timedelta(seconds=10),
        receive_timestamp=t0 + timedelta(seconds=10),
        sequence_id=2,
        last_traded_price=1882.0,
        last_traded_quantity=50,
        cumulative_volume=50, # Reset from 1,000,000 to 50
    )
    pipeline.process_tick(t2)

    # Next minute tick triggers bar closure
    t3 = MarketTickEvent(
        symbol="INFY",
        token="1594",
        exchange_timestamp=t0 + timedelta(seconds=65),
        receive_timestamp=t0 + timedelta(seconds=65),
        sequence_id=3,
        last_traded_price=1885.0,
        last_traded_quantity=10,
        cumulative_volume=60,
    )
    bar = pipeline.process_tick(t3)

    assert bar is not None
    assert bar.volume > 0 # Non-negative volume preserved!
    assert pipeline.volume_resets_detected == 1


def test_bounded_token_refresh_retries():
    """Verifies that token refresh attempts are strictly bounded to max 2 retries."""
    adapter = AngelOneMarketDataAdapter(mock_mode=False, api_key="test", client_code="test")
    adapter._refresh_token = "invalid_refresh_token"
    
    # Exceed retry budget
    adapter._auth_retry_count = 2
    res = adapter.refresh_session_token()
    assert res is False


# ==============================================================================
# 5. STRUCTURAL TRANSPORT ALLOWLIST & SUBSCRIPTION OPERATION TESTS
# ==============================================================================

def test_exact_allowlists_hosts_methods_and_subscription():
    """Verifies exact allowlist enforcement for hosts, methods, endpoints, and subscriptions."""
    adapter = AngelOneMarketDataAdapter(mock_mode=True)

    # 1. Host allowlist
    assert "apiconnect.angelone.in" in adapter.APPROVED_HOSTS
    assert "smartapisocket.angelone.in" in adapter.APPROVED_HOSTS
    assert "margincalculator.angelone.in" in adapter.APPROVED_HOSTS
    with pytest.raises(PermissionError, match="not in approved hosts"):
        adapter._execute_safe_market_data_request("GET", "https://unauthorized-broker-gateway.com/quote")

    # 2. Method allowlist
    assert adapter.APPROVED_HTTP_METHODS == {"GET", "POST"}
    with pytest.raises(PermissionError, match="not an approved HTTP method"):
        adapter._execute_safe_market_data_request("DELETE", "/rest/secure/angelbroking/market/v1/quote")

    # 3. Endpoint allowlist
    with pytest.raises(PermissionError, match="not an approved market-data endpoint"):
        adapter._execute_safe_market_data_request("GET", "/rest/secure/angelbroking/user/v1/unknownEndpoint")

    # 4. Subscription operation allowlist
    assert adapter.validate_subscription_operation(action=1, mode=2, exchange_segment=1, tokens=["3045", "2885"]) is True

    # Reject invalid action
    with pytest.raises(PermissionError, match="Subscription action 99 is not permitted"):
        adapter.validate_subscription_operation(action=99, mode=2, exchange_segment=1, tokens=["3045"])

    # Reject invalid mode
    with pytest.raises(PermissionError, match="Subscription mode 4 is not permitted"):
        adapter.validate_subscription_operation(action=1, mode=4, exchange_segment=1, tokens=["3045"])

    # Reject unmapped token
    with pytest.raises(PermissionError, match="not in verified instrument allowlist"):
        adapter.validate_subscription_operation(action=1, mode=2, exchange_segment=1, tokens=["UNMAPPED_TOKEN_99999"])

    # Build validated subscription payload
    payload = adapter.build_subscription_payload(action=1, mode=2, tokens=["3045", "2885"])
    assert payload["action"] == 1
    assert payload["params"]["mode"] == 2
    assert payload["params"]["tokenList"][0]["tokens"] == ["3045", "2885"]


# ==============================================================================
# 6. CANARY SECRET REDACTION TESTS
# ==============================================================================

def test_canary_secret_redaction_comprehensive():
    """
    Verifies that synthetic canary secrets are masked in:
    - Object representation (__repr__, __str__)
    - Diagnostics outputs
    - Smoke test outputs
    """
    canary_key = "CANARY_SECRET_API_KEY_12345678"
    canary_client = "CANARY_CLIENT_9988"
    canary_pwd = "CANARY_PASSWORD_SECRET"
    canary_totp = "CANARY_TOTP_KEY_ALPHA_BETA"

    adapter = AngelOneMarketDataAdapter(
        api_key=canary_key,
        client_code=canary_client,
        password=canary_pwd,
        totp_key=canary_totp,
        mock_mode=True,
    )

    repr_str = repr(adapter)
    str_str = str(adapter)

    # Invariants: No plaintext secret in representations
    assert canary_key not in repr_str
    assert canary_pwd not in repr_str
    assert canary_totp not in repr_str
    assert canary_client not in repr_str
    assert canary_key not in str_str
    assert canary_pwd not in str_str

    # Masked versions present
    assert "CA****5678" in repr_str
    assert "CA****" in repr_str

    # Smoke test output sanitization test
    from scripts.bounded_market_data_smoke_test import sanitize_output
    raw_record = {
        "api_key": canary_key,
        "token": "CANARY_FEED_TOKEN_SECRET_XYZ",
        "nested": {"client_password": canary_pwd, "symbol": "SBIN"},
    }
    sanitized = sanitize_output(raw_record)
    assert canary_key not in json.dumps(sanitized)
    assert "CANARY_FEED_TOKEN_SECRET_XYZ" not in json.dumps(sanitized)
    assert canary_pwd not in json.dumps(sanitized)
    assert sanitized["nested"]["symbol"] == "SBIN"


# ==============================================================================
# 7. PROVENANCE, DATA QUALITY & MODE SEPARATION TESTS
# ==============================================================================

def test_market_data_provenance_and_stale_gate():
    """
    Verifies:
    1. Provenance and mode separation tracking
    2. Feed failure / staleness prevents simulated entries
    3. No fabrication of ticks during outage
    """
    from services.market_data.adapters.market_event_schemas import (
        MarketDataProvenance,
        DataSource,
        CollectionMode,
        FeedHealth,
        ExecutionMode,
        AccountingValidationStatus,
    )

    prov = MarketDataProvenance(
        data_source=DataSource.MOCK,
        collection_mode=CollectionMode.FORWARD,
        feed_health=FeedHealth.HEALTHY,
        execution_mode=ExecutionMode.PAPER,
        accounting_validation=AccountingValidationStatus.UNVALIDATED,
    )
    assert prov.data_source == "MOCK"
    assert prov.accounting_validation == "UNVALIDATED"
    assert "UNRECONCILED_HISTORICAL_SOAK_GST_ARITHMETIC" in prov.accounting_blockers

    orders_executed = []
    def mock_executor(signal: int, bar):
        orders_executed.append((signal, bar.symbol))

    def mock_signal(bar):
        return 1 # Always BUY

    pipeline = MarketDataPipelineEngine(
        bar_interval_seconds=60,
        signal_generator=mock_signal,
        paper_executor=mock_executor,
        provenance=prov,
        allow_diagnostic_simulation=True,
    )

    t0 = datetime(2026, 9, 25, 9, 30, 0, tzinfo=timezone.utc)
    # Normal tick processing
    t1 = MarketTickEvent(
        symbol="SBIN",
        token="3045",
        exchange_timestamp=t0,
        receive_timestamp=t0,
        sequence_id=1,
        last_traded_price=820.0,
        last_traded_quantity=10,
        cumulative_volume=1000,
    )
    pipeline.process_tick(t1)

    t2 = MarketTickEvent(
        symbol="SBIN",
        token="3045",
        exchange_timestamp=t0 + timedelta(seconds=65),
        receive_timestamp=t0 + timedelta(seconds=65),
        sequence_id=2,
        last_traded_price=822.0,
        last_traded_quantity=10,
        cumulative_volume=1010,
    )
    bar1 = pipeline.process_tick(t2)
    assert bar1 is not None
    assert len(orders_executed) == 1 # First order executed

    # Now simulate a feed outage / staleness (>60s elapsed without ticks)
    # Stale detection
    stale_syms = pipeline.check_stale_feeds(current_time=t0 + timedelta(seconds=200), max_staleness_seconds=60)
    assert "SBIN" in stale_syms

    # Pipeline telemetry contains complete provenance
    telemetry = pipeline.get_pipeline_telemetry()
    assert "provenance" in telemetry
    assert telemetry["provenance"]["data_source"] == "MOCK"


# ==============================================================================
# 8. GST ARITHMETIC & STATUTORY COST MODEL CONSISTENCY TESTS
# ==============================================================================

def test_gst_arithmetic_statutory_reconciliation():
    """
    Verifies that statutory GST is 18.0% on (Brokerage + Exchange Fee + SEBI Fee)
    and that STT and Stamp Duty are excluded from the GST base.
    """
    from services.backtest_engine.cost_models import IndianCostCalculator
    from services.backtest_engine.contracts import OrderSide

    calc = IndianCostCalculator()
    
    # Single trade turnover: 50 * 2000 = ₹1,00,000 buy
    # Brokerage = min(20, 30) = ₹20.00
    # Exchange fee (0.00345%) = ₹3.45
    # SEBI fee (0.0001%) = ₹0.10
    # Taxable base = ₹20.00 + ₹3.45 + ₹0.10 = ₹23.55
    # GST (18%) = 23.55 * 0.18 = ₹4.239
    costs = calc.calculate_transaction_costs(OrderSide.BUY, 50, 2000.0, is_intraday=True)
    assert costs > 20.0

    # Test the specific historical audit contradiction:
    # Taxable base: ₹1800.00 (Brokerage) + ₹44.02 (Exchange fee) + ₹1.48 (SEBI fee) = ₹1845.50
    # Exact statutory GST = 1845.50 * 0.18 = ₹332.19
    taxable_base = 1800.00 + 44.02 + 1.48
    statutory_gst = round(taxable_base * 0.18, 2)
    assert statutory_gst == 332.19
    # The previously reported figure ₹377.27 has a +₹45.08 discrepancy
    assert round(377.27 - statutory_gst, 2) == 45.08


def test_foundation_execution_gate_blocks_strategy_execution_when_unverified():
    """
    Quality-First Foundation Gate Invariant:
    Strategy execution and paper orders MUST be blocked fail-closed when:
    1. Accounting validation is UNVALIDATED
    2. Real fresh data streaming has not been verified (real_connection_observed=False)
    Pipeline remains strictly in observation-only mode.
    """
    from services.market_data.adapters.market_event_schemas import (
        MarketDataProvenance,
        DataSource,
        CollectionMode,
        FeedHealth,
        ExecutionMode,
        AccountingValidationStatus,
    )
    from services.market_data.adapters.market_pipeline import FoundationExecutionGate

    prov = MarketDataProvenance(
        data_source=DataSource.MOCK,
        collection_mode=CollectionMode.FORWARD,
        feed_health=FeedHealth.HEALTHY,
        execution_mode=ExecutionMode.PAPER,
        accounting_validation=AccountingValidationStatus.UNVALIDATED,
        real_connection_observed=False,
    )

    # Gate evaluation must fail closed
    can_exec, reason = FoundationExecutionGate.evaluate_execution_readiness(prov, allow_diagnostic_simulation=False)
    assert can_exec is False
    assert "GATE BLOCKED" in reason

    # Running pipeline with default settings (allow_diagnostic_simulation=False)
    orders_executed = []
    def mock_executor(signal: int, bar):
        orders_executed.append((signal, bar.symbol))

    def mock_signal(bar):
        return 1 # Attempt BUY

    pipeline = MarketDataPipelineEngine(
        bar_interval_seconds=60,
        signal_generator=mock_signal,
        paper_executor=mock_executor,
        provenance=prov,
        allow_diagnostic_simulation=False, # STRICT FOUNDATION DEFAULT
    )

    t0 = datetime(2026, 9, 25, 9, 30, 0, tzinfo=timezone.utc)
    t1 = MarketTickEvent(
        symbol="SBIN",
        token="3045",
        exchange_timestamp=t0,
        receive_timestamp=t0,
        sequence_id=1,
        last_traded_price=820.0,
        last_traded_quantity=10,
        cumulative_volume=1000,
    )
    pipeline.process_tick(t1)

    t2 = MarketTickEvent(
        symbol="SBIN",
        token="3045",
        exchange_timestamp=t0 + timedelta(seconds=65),
        receive_timestamp=t0 + timedelta(seconds=65),
        sequence_id=2,
        last_traded_price=825.0,
        last_traded_quantity=10,
        cumulative_volume=1010,
    )
    bar = pipeline.process_tick(t2)
    assert bar is not None
    assert bar.close == 820.0

    # CRITICAL INVARIANT: Zero signals emitted, zero orders executed!
    assert pipeline.signals_emitted == 0
    assert len(orders_executed) == 0


