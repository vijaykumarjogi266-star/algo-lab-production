"""
Statutory Indian Equity Cost Model (NSE/BSE).
Implements precise Decimal arithmetic conforming to Indian regulatory schedules:
- SEBI (Stock Brokers) Regulations, 1992 (Turnover Fees)
- NSE Cash Market Transaction Charges (NSE Circulars)
- Chapter VII of Finance (No. 2) Act, 2004 (Securities Transaction Tax - STT)
- Indian Stamp Act, 1899 (as amended by Finance Act 2019, eff. July 1, 2020)
- Central Goods and Services Tax (CGST) Act, 2017 & IGST Act, 2017 (18% on services)
- Standard Discount Broker Tariff (min(₹20, 0.03%) per executed order for Intraday)
- Depository Participant (DP) Charges on Delivery/CNC Sell (Flat ₹15.34)

CRITICAL TAX SEPARATION INVARIANT (Plan Phase 1):
- Brokerage, Exchange Fees, SEBI Turnover fees, and DP charges are taxable supplies of financial services subject to 18% GST.
- STT and Stamp Duty are statutory taxes/duties levied by Central/State governments and are EXCLUDED from the GST taxable base.
- Execution Slippage (market impact / bid-ask bounce) is embedded in the executed fill price and is tracked separately from explicit broker/statutory debits.
"""

from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass
from typing import Dict, Any, Optional
from enum import Enum


class OrderLeg(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class ProductType(str, Enum):
    INTRADAY = "INTRADAY"   # MIS / Product Type Intraday
    DELIVERY = "DELIVERY"   # CNC / Product Type Delivery Cash (Swing Trading)


@dataclass(frozen=True)
class ExecutionFrictionBreakdown:
    turnover: Decimal
    brokerage: Decimal
    stt: Decimal
    exchange_txn_fee: Decimal
    sebi_turnover_fee: Decimal
    stamp_duty: Decimal
    gst: Decimal
    total_statutory_and_brokerage: Decimal
    slippage_cost_inr: Decimal
    all_in_total_friction: Decimal
    dp_charge: Decimal = Decimal("0.00")

    def to_dict(self) -> Dict[str, float]:
        return {
            "turnover": float(self.turnover),
            "brokerage": float(self.brokerage),
            "stt": float(self.stt),
            "exchange_txn_fee": float(self.exchange_txn_fee),
            "sebi_turnover_fee": float(self.sebi_turnover_fee),
            "stamp_duty": float(self.stamp_duty),
            "gst": float(self.gst),
            "dp_charge": float(self.dp_charge),
            "total_statutory_and_brokerage": float(self.total_statutory_and_brokerage),
            "slippage_cost_inr": float(self.slippage_cost_inr),
            "all_in_total_friction": float(self.all_in_total_friction),
        }


class IndianStatutoryCostModel:
    """
    Statutory rate schedule and tariff calculations for Indian Cash Equities.
    Uses Decimal with 2 decimal places (ROUND_HALF_UP) for all currency representations.
    """

    # Statutory Rates
    NSE_TXN_RATE = Decimal("0.0000297")        # 0.00297% (₹2.97 per lakh)
    SEBI_RATE = Decimal("0.0000010")           # 0.0001% (₹10 per crore)
    GST_RATE = Decimal("0.18")                 # 18.0% GST on taxable services
    
    # Intraday (MIS)
    INTRADAY_BROKERAGE_PCT = Decimal("0.0003") # 0.03%
    BROKERAGE_CAP_PER_ORDER = Decimal("20.00") # ₹20 max per executed order
    INTRADAY_STT_SELL_RATE = Decimal("0.00025")# 0.025% on sell leg only
    INTRADAY_STAMP_BUY_RATE = Decimal("0.00003")# 0.003% (₹300 per crore) on buy leg only

    # Delivery (CNC / Swing Trading)
    DELIVERY_BROKERAGE_PCT = Decimal("0.0")    # ₹0 delivery brokerage (standard discount model)
    DELIVERY_STT_RATE = Decimal("0.0010")      # 0.1% on buy and sell
    DELIVERY_STAMP_BUY_RATE = Decimal("0.00015")# 0.015% (₹1500 per crore) on buy leg only
    DP_CHARGE_FLAT_SELL = Decimal("15.34")     # Flat ₹15.34 DP charge on Sell leg only

    @classmethod
    def round_inr(cls, val: Decimal) -> Decimal:
        return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @classmethod
    def calculate_delivery_friction(
        cls,
        leg: OrderLeg,
        price: Decimal,
        quantity: int,
        brokerage: Decimal = Decimal("0.00"),
        dp_charge_flat: Decimal = Decimal("15.34"),
        slippage_bps: Decimal = Decimal("0.0"),
    ) -> ExecutionFrictionBreakdown:
        """
        Calculates authoritative Indian Equity Delivery (CNC / Swing Trading) statutory friction:
        - STT: 0.1% on both Buy and Sell legs
        - Stamp Duty: 0.015% on Buy leg only
        - DP Charge: Flat ₹15.34 applied only on Sell leg
        - GST: 18% applied to Brokerage, Exchange, SEBI, and DP charges
        - Slippage: Basis point execution market impact
        """
        turnover = cls.round_inr(price * Decimal(quantity))
        if turnover <= Decimal("0.00"):
            return ExecutionFrictionBreakdown(
                turnover=Decimal("0.00"),
                brokerage=Decimal("0.00"),
                stt=Decimal("0.00"),
                exchange_txn_fee=Decimal("0.00"),
                sebi_turnover_fee=Decimal("0.00"),
                stamp_duty=Decimal("0.00"),
                gst=Decimal("0.00"),
                total_statutory_and_brokerage=Decimal("0.00"),
                slippage_cost_inr=Decimal("0.00"),
                all_in_total_friction=Decimal("0.00"),
                dp_charge=Decimal("0.00"),
            )

        # 1. Brokerage (₹0 standard discount delivery brokerage or flat)
        round_brokerage = cls.round_inr(brokerage)

        # 2. STT: 0.1% on both Buy and Sell
        stt = cls.round_inr(turnover * cls.DELIVERY_STT_RATE)

        # 3. Exchange Turnover Charge (NSE: 0.00297%)
        exchange_txn_fee = cls.round_inr(turnover * cls.NSE_TXN_RATE)

        # 4. SEBI Regulatory Turnover Fee (₹10/crore = 0.0001%)
        sebi_turnover_fee = cls.round_inr(turnover * cls.SEBI_RATE)

        # 5. Stamp Duty: 0.015% on BUY leg only
        stamp_duty = cls.round_inr(turnover * cls.DELIVERY_STAMP_BUY_RATE) if leg == OrderLeg.BUY else Decimal("0.00")

        # 6. DP Charge: Flat ₹15.34 on SELL leg only
        dp_charge = cls.round_inr(dp_charge_flat) if leg == OrderLeg.SELL else Decimal("0.00")

        # 7. GST: 18% applied to Brokerage, Exchange, SEBI, and DP charges
        taxable_services_base = round_brokerage + exchange_txn_fee + sebi_turnover_fee + dp_charge
        gst = cls.round_inr(taxable_services_base * cls.GST_RATE)

        total_statutory_and_brokerage = (
            round_brokerage + stt + exchange_txn_fee + sebi_turnover_fee + stamp_duty + dp_charge + gst
        )

        # 8. Slippage
        slippage_cost = cls.round_inr(turnover * (slippage_bps / Decimal("10000.0")))
        all_in_total_friction = total_statutory_and_brokerage + slippage_cost

        return ExecutionFrictionBreakdown(
            turnover=turnover,
            brokerage=round_brokerage,
            stt=stt,
            exchange_txn_fee=exchange_txn_fee,
            sebi_turnover_fee=sebi_turnover_fee,
            stamp_duty=stamp_duty,
            gst=gst,
            total_statutory_and_brokerage=total_statutory_and_brokerage,
            slippage_cost_inr=slippage_cost,
            all_in_total_friction=all_in_total_friction,
            dp_charge=dp_charge,
        )

    @classmethod
    def calculate_order_friction(
        cls,
        leg: OrderLeg,
        price: Decimal,
        quantity: int,
        product: ProductType = ProductType.INTRADAY,
        brokerage_cap: Decimal = Decimal("20.00"),
        slippage_bps: Decimal = Decimal("0.0"),
        dp_charge_flat: Decimal = Decimal("15.34"),
    ) -> ExecutionFrictionBreakdown:
        """
        Calculates exact statutory friction for a single executed order leg (BUY or SELL).
        Dispatches to calculate_delivery_friction for DELIVERY products.
        """
        if product == ProductType.DELIVERY:
            return cls.calculate_delivery_friction(
                leg=leg,
                price=price,
                quantity=quantity,
                brokerage=Decimal("0.00"),
                dp_charge_flat=dp_charge_flat,
                slippage_bps=slippage_bps,
            )

        turnover = cls.round_inr(price * Decimal(quantity))
        if turnover <= Decimal("0.00"):
            return ExecutionFrictionBreakdown(
                turnover=Decimal("0.00"),
                brokerage=Decimal("0.00"),
                stt=Decimal("0.00"),
                exchange_txn_fee=Decimal("0.00"),
                sebi_turnover_fee=Decimal("0.00"),
                stamp_duty=Decimal("0.00"),
                gst=Decimal("0.00"),
                total_statutory_and_brokerage=Decimal("0.00"),
                slippage_cost_inr=Decimal("0.00"),
                all_in_total_friction=Decimal("0.00"),
                dp_charge=Decimal("0.00"),
            )

        # 1. Brokerage (Intraday)
        raw_brokerage = turnover * cls.INTRADAY_BROKERAGE_PCT
        brokerage = cls.round_inr(min(brokerage_cap, raw_brokerage))

        # 2. STT (Securities Transaction Tax)
        stt = cls.round_inr(turnover * cls.INTRADAY_STT_SELL_RATE) if leg == OrderLeg.SELL else Decimal("0.00")

        # 3. Exchange Turnover Charge
        exchange_txn_fee = cls.round_inr(turnover * cls.NSE_TXN_RATE)

        # 4. SEBI Regulatory Turnover Fee
        sebi_turnover_fee = cls.round_inr(turnover * cls.SEBI_RATE)

        # 5. Stamp Duty (State levy on BUY orders only)
        stamp_duty = cls.round_inr(turnover * cls.INTRADAY_STAMP_BUY_RATE) if leg == OrderLeg.BUY else Decimal("0.00")

        # 6. Goods & Services Tax (18% on Taxable Financial Services ONLY)
        taxable_services_base = brokerage + exchange_txn_fee + sebi_turnover_fee
        gst = cls.round_inr(taxable_services_base * cls.GST_RATE)

        total_statutory_and_brokerage = (
            brokerage + stt + exchange_txn_fee + sebi_turnover_fee + stamp_duty + gst
        )

        # 7. Slippage Friction
        slippage_cost = cls.round_inr(turnover * (slippage_bps / Decimal("10000.0")))
        all_in_total_friction = total_statutory_and_brokerage + slippage_cost

        return ExecutionFrictionBreakdown(
            turnover=turnover,
            brokerage=brokerage,
            stt=stt,
            exchange_txn_fee=exchange_txn_fee,
            sebi_turnover_fee=sebi_turnover_fee,
            stamp_duty=stamp_duty,
            gst=gst,
            total_statutory_and_brokerage=total_statutory_and_brokerage,
            slippage_cost_inr=slippage_cost,
            all_in_total_friction=all_in_total_friction,
            dp_charge=Decimal("0.00"),
        )
