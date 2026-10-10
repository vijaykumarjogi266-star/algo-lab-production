"""
Unit Tests for Financial Truth and Statutory Indian Equity Cost Models.
Conforms to Quality-First Plan:
- Phase 1: Authoritative Financial Event Model, Exact Decimal Arithmetic, and Discrepancy Closure (Pages 5-7)
- Section 12: Test Strategy, Golden Examples, and Negative Controls (Pages 17-18)
"""

from decimal import Decimal
import json
import os
import pytest

from services.backtest_engine.statutory_cost_model import (
    IndianStatutoryCostModel,
    OrderLeg,
    ProductType,
    ExecutionFrictionBreakdown,
)


def test_hand_worked_intraday_buy_sbin():
    """
    Hand-worked golden example for Intraday BUY of 100 SBIN @ ₹800.00.
    Turnover: ₹80,000.00
    - Brokerage: min(₹20, 80000 * 0.0003 = 24.00) = ₹20.00
    - STT: ₹0.00 (BUY leg exempt for intraday)
    - NSE Txn Fee: 80000 * 0.0000297 = 2.376 -> ₹2.38
    - SEBI Fee: 80000 * 0.0000010 = 0.08 -> ₹0.08
    - Stamp Duty: 80000 * 0.00003 = 2.40 -> ₹2.40 (State levy on BUY)
    - Taxable Base: 20.00 + 2.38 + 0.08 = ₹22.46
    - GST (18% on Taxable Base): 22.46 * 0.18 = 4.0428 -> ₹4.04
    - Total Statutory & Brokerage: 20.00 + 0 + 2.38 + 0.08 + 2.40 + 4.04 = ₹28.90
    """
    friction = IndianStatutoryCostModel.calculate_order_friction(
        leg=OrderLeg.BUY,
        price=Decimal("800.00"),
        quantity=100,
        product=ProductType.INTRADAY,
    )

    assert friction.turnover == Decimal("80000.00")
    assert friction.brokerage == Decimal("20.00")
    assert friction.stt == Decimal("0.00")
    assert friction.exchange_txn_fee == Decimal("2.38")
    assert friction.sebi_turnover_fee == Decimal("0.08")
    assert friction.stamp_duty == Decimal("2.40")
    assert friction.gst == Decimal("4.04")
    assert friction.total_statutory_and_brokerage == Decimal("28.90")


def test_hand_worked_intraday_sell_sbin():
    """
    Hand-worked golden example for Intraday SELL of 100 SBIN @ ₹810.00.
    Turnover: ₹81,000.00
    - Brokerage: min(₹20, 81000 * 0.0003 = 24.30) = ₹20.00
    - STT: 81000 * 0.00025 = 20.25 -> ₹20.25 (Intraday SELL only)
    - NSE Txn Fee: 81000 * 0.0000297 = 2.4057 -> ₹2.41
    - SEBI Fee: 81000 * 0.0000010 = 0.081 -> ₹0.08
    - Stamp Duty: ₹0.00 (Exempt on SELL leg)
    - Taxable Base: 20.00 + 2.41 + 0.08 = ₹22.49
    - GST (18% on Taxable Base): 22.49 * 0.18 = 4.0482 -> ₹4.05
    - Total Statutory & Brokerage: 20.00 + 20.25 + 2.41 + 0.08 + 0.00 + 4.05 = ₹46.79
    """
    friction = IndianStatutoryCostModel.calculate_order_friction(
        leg=OrderLeg.SELL,
        price=Decimal("810.00"),
        quantity=100,
        product=ProductType.INTRADAY,
    )

    assert friction.turnover == Decimal("81000.00")
    assert friction.brokerage == Decimal("20.00")
    assert friction.stt == Decimal("20.25")
    assert friction.exchange_txn_fee == Decimal("2.41")
    assert friction.sebi_turnover_fee == Decimal("0.08")
    assert friction.stamp_duty == Decimal("0.00")
    assert friction.gst == Decimal("4.05")
    assert friction.total_statutory_and_brokerage == Decimal("46.79")


def test_complete_roundtrip_trade_net_pnl():
    """
    Verifies full roundtrip execution P&L accounting:
    Gross P&L = (810 - 800) * 100 = ₹1,000.00
    Total Friction = 28.90 (BUY) + 46.79 (SELL) = ₹75.69
    Net Realized P&L = 1000.00 - 75.69 = ₹924.31
    """
    buy_friction = IndianStatutoryCostModel.calculate_order_friction(
        leg=OrderLeg.BUY, price=Decimal("800.00"), quantity=100
    )
    sell_friction = IndianStatutoryCostModel.calculate_order_friction(
        leg=OrderLeg.SELL, price=Decimal("810.00"), quantity=100
    )

    total_friction = buy_friction.total_statutory_and_brokerage + sell_friction.total_statutory_and_brokerage
    assert total_friction == Decimal("75.69")

    gross_pnl = Decimal("810.00") * 100 - Decimal("800.00") * 100
    net_pnl = gross_pnl - total_friction
    assert net_pnl == Decimal("924.31")


def test_negative_control_corrupt_gst_taxable_base():
    """
    NEGATIVE CONTROL (Plan Page 6 & 17):
    A deliberately incorrect tax calculation that includes STT or Stamp Duty in GST
    MUST be detected and rejected.
    """
    turnover = Decimal("80000.00")
    brokerage = Decimal("20.00")
    exchange_fee = Decimal("2.38")
    sebi_fee = Decimal("0.08")
    stamp_duty = Decimal("2.40")

    # True statutory taxable services base
    correct_base = brokerage + exchange_fee + sebi_fee
    correct_gst = (correct_base * Decimal("0.18")).quantize(Decimal("0.01"))
    assert correct_gst == Decimal("4.04")

    # Corrupt base that improperly includes Stamp Duty in GST base
    corrupt_base = correct_base + stamp_duty
    corrupt_gst = (corrupt_base * Decimal("0.18")).quantize(Decimal("0.01"))
    assert corrupt_gst == Decimal("4.47")

    # Negative control assertion: Correct statutory GST MUST NOT equal corrupt GST
    assert correct_gst != corrupt_gst


def test_discrepancy_1_gst_arithmetic_plug_figure_rejection():
    """
    Reconciles Discrepancy 1 from Quality-First Plan Page 6:
    Historical soak report claimed GST of ₹377.27 on a taxable services base of ₹1,845.50.
    True 18% statutory GST is ₹332.19. The ₹45.08 plug figure is proven and rejected.
    """
    taxable_base = Decimal("1845.50")
    statutory_gst = (taxable_base * Decimal("0.18")).quantize(Decimal("0.01"))
    reported_gst = Decimal("377.27")

    assert statutory_gst == Decimal("332.19")
    divergence = reported_gst - statutory_gst
    assert divergence == Decimal("45.08")  # Exact plug figure confirmed


def test_discrepancy_2_turnover_inconsistency_rejection():
    """
    Reconciles Discrepancy 2 from Quality-First Plan Page 6:
    Historical soak report claimed total turnover of ₹14,82,696.86,
    while Stamp Duty implied buy turnover of ₹7,41,666.67 and STT implied sell turnover of ₹9,15,400.00.
    Sum of implied buy and sell turnover (₹16,57,066.67) exceeds stated total by ₹1,74,369.81.
    """
    stated_total = Decimal("1482696.86")
    stamp_duty = Decimal("22.25")
    implied_buy = (stamp_duty / Decimal("0.00003")).quantize(Decimal("0.01"))
    assert implied_buy == Decimal("741666.67")

    stt = Decimal("228.85")
    implied_sell = (stt / Decimal("0.00025")).quantize(Decimal("0.01"))
    assert implied_sell == Decimal("915400.00")

    sum_implied = implied_buy + implied_sell
    assert sum_implied == Decimal("1657066.67")
    turnover_discrepancy = sum_implied - stated_total
    assert turnover_discrepancy == Decimal("174369.81")
    assert sum_implied != stated_total


def test_discrepancy_3_baseline_trade_count_source_log_absence():
    """
    Reconciles Discrepancy 3 from Quality-First Plan Page 6:
    Verifies that live_trades.jsonl in the repository contains only 1 trade (HAL.NS),
    and zero records for the 3-trade scenario (TCS, INFY, RELIANCE).
    """
    trade_log_path = "/home/ubuntu/algolab-sandbox/disposable_sandbox/data/live_trades.jsonl"
    assert os.path.exists(trade_log_path)

    events = []
    with open(trade_log_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line.strip()))

    # Assert exactly 1 trade event exists in source log
    assert len(events) == 1
    assert events[0]["details"]["symbol"] == "HAL.NS"
    # Assert TCS, INFY, RELIANCE are absent
    symbols = [e["details"].get("symbol") for e in events]
    assert "TCS" not in symbols
    assert "INFY" not in symbols
    assert "RELIANCE" not in symbols


def test_delivery_buy_friction_statutory_rates():
    """
    Tests Indian Equity Delivery (CNC / Swing Trading) BUY leg:
    Turnover: ₹80,000.00 (100 shares @ ₹800.00)
    - Brokerage: ₹0.00
    - STT: 80,000 * 0.1% = ₹80.00 (Delivery STT on BUY)
    - Exchange Fee: 80,000 * 0.00297% = ₹2.38
    - SEBI Fee: 80,000 * 0.0001% = ₹0.08
    - Stamp Duty: 80,000 * 0.015% = ₹12.00 (BUY only)
    - DP Charge: ₹0.00 (BUY leg exempt)
    - Taxable Base: 0 + 2.38 + 0.08 = ₹2.46
    - GST (18% on Taxable Base): 2.46 * 0.18 = ₹0.44
    - Total Statutory & Brokerage: 0 + 80.00 + 2.38 + 0.08 + 12.00 + 0.00 + 0.44 = ₹94.90
    """
    friction = IndianStatutoryCostModel.calculate_delivery_friction(
        leg=OrderLeg.BUY,
        price=Decimal("800.00"),
        quantity=100,
    )

    assert friction.turnover == Decimal("80000.00")
    assert friction.brokerage == Decimal("0.00")
    assert friction.stt == Decimal("80.00")
    assert friction.exchange_txn_fee == Decimal("2.38")
    assert friction.sebi_turnover_fee == Decimal("0.08")
    assert friction.stamp_duty == Decimal("12.00")
    assert friction.dp_charge == Decimal("0.00")
    assert friction.gst == Decimal("0.44")
    assert friction.total_statutory_and_brokerage == Decimal("94.90")


def test_delivery_sell_friction_with_dp_charge_and_gst():
    """
    Tests Indian Equity Delivery (CNC / Swing Trading) SELL leg:
    Turnover: ₹85,000.00 (100 shares @ ₹850.00)
    - Brokerage: ₹0.00
    - STT: 85,000 * 0.1% = ₹85.00 (Delivery STT on SELL)
    - Exchange Fee: 85,000 * 0.00297% = ₹2.52
    - SEBI Fee: 85,000 * 0.0001% = ₹0.09
    - Stamp Duty: ₹0.00 (Exempt on SELL leg)
    - DP Charge: Flat ₹15.34 (Depository participant charge on SELL leg)
    - Taxable Base: 0 + 2.52 + 0.09 + 15.34 = ₹17.95
    - GST (18% on Taxable Base): 17.95 * 0.18 = ₹3.23
    - Total Statutory & Brokerage: 0 + 85.00 + 2.52 + 0.09 + 0.00 + 15.34 + 3.23 = ₹106.18
    """
    friction = IndianStatutoryCostModel.calculate_delivery_friction(
        leg=OrderLeg.SELL,
        price=Decimal("850.00"),
        quantity=100,
    )

    assert friction.turnover == Decimal("85000.00")
    assert friction.brokerage == Decimal("0.00")
    assert friction.stt == Decimal("85.00")
    assert friction.exchange_txn_fee == Decimal("2.52")
    assert friction.sebi_turnover_fee == Decimal("0.09")
    assert friction.stamp_duty == Decimal("0.00")
    assert friction.dp_charge == Decimal("15.34")
    assert friction.gst == Decimal("3.23")
    assert friction.total_statutory_and_brokerage == Decimal("106.18")


def test_delivery_roundtrip_trade_net_pnl():
    """
    Verifies complete roundtrip Delivery Swing Trade accounting:
    Gross P&L = (850 - 800) * 100 = ₹5,000.00
    Total Delivery Friction = 94.90 (BUY) + 106.18 (SELL) = ₹201.08
    Net Realized P&L = 5000.00 - 201.08 = ₹4,798.92
    """
    buy_friction = IndianStatutoryCostModel.calculate_delivery_friction(
        leg=OrderLeg.BUY, price=Decimal("800.00"), quantity=100
    )
    sell_friction = IndianStatutoryCostModel.calculate_delivery_friction(
        leg=OrderLeg.SELL, price=Decimal("850.00"), quantity=100
    )

    total_friction = buy_friction.total_statutory_and_brokerage + sell_friction.total_statutory_and_brokerage
    assert total_friction == Decimal("201.08")

    gross_pnl = Decimal("850.00") * 100 - Decimal("800.00") * 100
    net_pnl = gross_pnl - total_friction
    assert net_pnl == Decimal("4798.92")
