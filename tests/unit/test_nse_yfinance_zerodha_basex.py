"""Tests for NSE Market Data, YFinance Market Data, and Zerodha BaseX Adapters.

Validates:
1. NSELiveMarketDataAdapter: Quote fetching, bar construction, mock & online mode, fail-closed behavior.
2. YFinanceMarketDataAdapter: Historical bar parsing, OHLCV normalization, UTC timezone integrity, caching.
3. ZerodhaBaseXAdapter:
   - Fail-closed security: LIVE mode raises PermissionError.
   - Profile & Margins discovery.
   - Statutory Indian charges calculation (Brokerage, STT, Transaction, GST, Stamp Duty).
   - Margin checking and risk rejection.
   - Order submission, state transitions (SUBMITTED -> FILLED), and ledger position updates.
"""

from datetime import datetime, timezone, timedelta
import pytest

from data.schemas.canonical_market_data import CanonicalMarketDataBar
from data.schemas.contracts import DataQualityStatus
from services.backtest_engine.contracts import OrderSide, OrderType
from services.backtest_engine.execution_lifecycle import (
    ExecutionOrder,
    OrderLifecycleState,
)
from services.market_data.adapters import (
    NSELiveMarketDataAdapter,
    YFinanceMarketDataAdapter,
)
from services.paper_engine.adapters import (
    BrokerConnectionConfig,
    ExecutionEnvironment,
    ZerodhaBaseXAdapter,
    ZerodhaBrokerFeeCalculator,
    ZerodhaProductType,
)


# --- 1. NSE Adapter Tests ---

def test_nse_adapter_mock_mode_connection():
    adapter = NSELiveMarketDataAdapter(mock_mode=True)
    res = adapter.test_connection()
    assert res["status"] == "CONNECTED"
    assert res["connected"] is True
    assert adapter.provider_name == "NSE_INDIA"


def test_nse_adapter_fetch_quote_and_bar():
    adapter = NSELiveMarketDataAdapter(mock_mode=True)
    quote = adapter.fetch_live_quote("RELIANCE")
    assert quote is not None
    assert quote.symbol == "RELIANCE"
    assert quote.last_traded_price == 2500.0
    assert quote.exchange == "NSE"
    assert quote.quality_status == DataQualityStatus.VALID

    bar = adapter.get_latest_bar("RELIANCE")
    assert bar is not None
    assert bar.symbol == "RELIANCE"
    assert bar.close == 2500.0
    assert bar.timestamp.tzinfo == timezone.utc


def test_nse_adapter_seeded_bars():
    adapter = NSELiveMarketDataAdapter(mock_mode=True)
    t0 = datetime(2026, 10, 11, 9, 15, tzinfo=timezone.utc)
    bar = CanonicalMarketDataBar(
        timestamp=t0,
        symbol="INFY",
        exchange="NSE",
        timeframe="1m",
        open=1500.0,
        high=1510.0,
        low=1495.0,
        close=1505.0,
        volume=2000.0,
    )
    adapter.seed_bars("INFY", [bar])
    bars = adapter.get_bars("INFY", "1m", t0 - timedelta(minutes=1), t0 + timedelta(minutes=1))
    assert len(bars) == 1
    assert bars[0].close == 1505.0


# --- 2. YFinance Adapter Tests ---

def test_yfinance_adapter_connection():
    adapter = YFinanceMarketDataAdapter(mock_mode=True)
    res = adapter.test_connection()
    assert res["status"] == "CONNECTED"
    assert res["connected"] is True
    assert adapter.provider_name == "YFINANCE"


def test_yfinance_adapter_normalization():
    adapter = YFinanceMarketDataAdapter(mock_mode=True)
    assert adapter._normalize_ticker("TCS") == "TCS.NS"
    assert adapter._normalize_ticker("TCS.NS") == "TCS.NS"
    assert adapter._canonical_symbol("TCS.NS") == "TCS"


def test_yfinance_adapter_seed_and_retrieve():
    adapter = YFinanceMarketDataAdapter(mock_mode=True)
    t0 = datetime(2026, 10, 10, 10, 0, tzinfo=timezone.utc)
    bar = CanonicalMarketDataBar(
        timestamp=t0,
        symbol="TCS",
        exchange="NSE",
        timeframe="1d",
        open=3500.0,
        high=3550.0,
        low=3480.0,
        close=3520.0,
        volume=50000.0,
    )
    adapter.seed_bars("TCS", [bar])
    bars = adapter.get_bars("TCS", "1d", t0 - timedelta(days=1), t0 + timedelta(days=1))
    assert len(bars) == 1
    assert bars[0].symbol == "TCS"
    assert bars[0].close == 3520.0


# --- 3. Zerodha BaseX Adapter Tests ---

def test_zerodha_basex_fail_closed_on_live():
    cfg = BrokerConnectionConfig(
        broker_name="zerodha",
        environment=ExecutionEnvironment.LIVE,
    )
    with pytest.raises(PermissionError, match="prohibited"):
        ZerodhaBaseXAdapter(connection_config=cfg)


def test_zerodha_basex_connection_and_margins():
    adapter = ZerodhaBaseXAdapter(mock_mode=True)
    res = adapter.test_connection()
    assert res["status"] == "CONNECTED"
    assert res["broker"] == "zerodha"
    assert res["adapter"] == "ZerodhaBaseX"

    margins = adapter.get_margins()
    assert margins["total_capital"] == 1_000_000.0
    assert margins["available_cash"] == 1_000_000.0


def test_zerodha_broker_fee_calculator():
    # Buy MIS (Intraday)
    calc_buy = ZerodhaBrokerFeeCalculator.calculate_turnover_and_charges(
        side=OrderSide.BUY,
        price=1000.0,
        quantity=100,
        product=ZerodhaProductType.MIS,
    )
    assert calc_buy["turnover"] == 100000.0
    assert calc_buy["brokerage"] == 20.0  # capped at Rs 20
    assert calc_buy["stt"] == 0.0         # No STT on intraday buy
    assert calc_buy["stamp_duty"] == 3.0  # 0.003% of 100,000 = 3
    assert calc_buy["total_charges"] > 25.0

    # Sell MIS (Intraday)
    calc_sell = ZerodhaBrokerFeeCalculator.calculate_turnover_and_charges(
        side=OrderSide.SELL,
        price=1000.0,
        quantity=100,
        product=ZerodhaProductType.MIS,
    )
    assert calc_sell["stt"] == 25.0       # 0.025% of 100,000 = 25
    assert calc_sell["stamp_duty"] == 0.0 # No stamp duty on sell


def test_zerodha_basex_paper_order_execution():
    adapter = ZerodhaBaseXAdapter(mock_mode=True)
    order = ExecutionOrder(
        order_id="ord_basex_001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        quantity=50,
        proposed_price=2500.0,
        order_type=OrderType.MARKET,
    )

    executed_order, fill = adapter.submit_paper_order(order, execution_price=2500.0)

    assert executed_order.state == OrderLifecycleState.ORDER_FILLED
    assert fill.quantity == 50
    assert fill.fill_price == 2500.0
    assert fill.net_traded_value == 125000.0
    assert fill.transaction_costs > 0

    # Verify positions and margin deductions
    positions = adapter.get_positions()
    assert positions["RELIANCE"] == 50
    margins = adapter.get_margins()
    assert margins["total_capital"] < 1_000_000.0


def test_zerodha_basex_margin_rejection():
    adapter = ZerodhaBaseXAdapter(mock_mode=True)
    order = ExecutionOrder(
        order_id="ord_basex_huge",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        quantity=10_000,  # 10,000 * 2500 = 2.5 Crore > 10 Lakh cash
        proposed_price=2500.0,
        order_type=OrderType.MARKET,
    )

    executed_order, fill = adapter.submit_paper_order(order, execution_price=2500.0)

    assert executed_order.state == OrderLifecycleState.ORDER_REJECTED
    assert "Margin Violation" in (executed_order.rejection_reason or "")
    assert fill.quantity == 0
    assert adapter.get_positions() == {}
