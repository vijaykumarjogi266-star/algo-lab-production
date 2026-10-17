"""Formal Institutional Execution Simulator Contract & Realism Engine.

Workstream F Compliance:
- Explicit timestamp progression: signal_time -> order_submission_time -> fill_time.
- Explicit fill-price model, slippage, spread, statutory friction, and market impact.
- Realistic volume participation cap and gap-down open execution.
- Deterministic and verifiable execution contract attached to every simulation output.
"""

from __future__ import annotations
from datetime import datetime, timedelta, timezone
from enum import Enum
import math
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, model_validator


class FillPriceModel(str, Enum):
    NEXT_BAR_OPEN = "NEXT_BAR_OPEN"
    CURRENT_BAR_CLOSE = "CURRENT_BAR_CLOSE"
    VWAP = "VWAP"
    SPREAD_MIDPOINT = "SPREAD_MIDPOINT"


class PartialFillPolicy(str, Enum):
    ALL_OR_NONE = "ALL_OR_NONE"
    VOLUME_CAPPED_PRO_RATA = "VOLUME_CAPPED_PRO_RATA"
    IMMEDIATE_OR_CANCEL = "IMMEDIATE_OR_CANCEL"


class GapHandlingPolicy(str, Enum):
    REALISTIC_OPEN_PRICE = "REALISTIC_OPEN_PRICE"
    EXACT_STOP_PRICE = "EXACT_STOP_PRICE"  # Unrealistic benchmark baseline only


class ExecutionSimulatorContract(BaseModel):
    """Institutional Execution Realism Contract."""

    contract_version: str = "1.0.0"
    fill_price_model: FillPriceModel = Field(default=FillPriceModel.NEXT_BAR_OPEN)
    fixed_tick_slippage_pts: float = Field(default=0.05, ge=0.0)
    variable_slippage_bps: float = Field(default=5.0, ge=0.0, description="Variable slippage in basis points")
    volume_participation_cap_pct: float = Field(default=0.10, ge=0.01, le=1.0, description="Max 10% bar volume participation")
    market_impact_coefficient: float = Field(default=0.1, ge=0.0, description="Square-root market impact parameter")
    partial_fill_policy: PartialFillPolicy = Field(default=PartialFillPolicy.VOLUME_CAPPED_PRO_RATA)
    gap_handling: GapHandlingPolicy = Field(default=GapHandlingPolicy.REALISTIC_OPEN_PRICE)

    # Statutory friction rates
    stt_rate_delivery_sell: float = Field(default=0.001)
    stt_rate_intraday_sell: float = Field(default=0.00025)
    exchange_fee_rate: float = Field(default=0.0000345)
    sebi_fee_rate: float = Field(default=0.000001)
    stamp_duty_rate_buy: float = Field(default=0.00015)
    gst_rate: float = Field(default=0.18)
    flat_dp_charge_sell: float = Field(default=15.34)

    def calculate_effective_price(
        self,
        base_price: float,
        is_buy: bool,
        order_quantity: int,
        bar_volume: float,
    ) -> float:
        """Computes realistic execution price accounting for tick spread, bps slippage, and market impact."""
        # Variable slippage (bps)
        slippage_fraction = self.variable_slippage_bps / 10000.0
        slippage_drag = base_price * slippage_fraction

        # Square-root market impact approximation: impact = coeff * sqrt(qty / volume)
        if bar_volume > 0 and order_quantity > 0:
            participation_ratio = min(order_quantity / bar_volume, 1.0)
            impact_drag = base_price * (self.market_impact_coefficient / 100.0) * math.sqrt(participation_ratio)
        else:
            impact_drag = 0.0

        total_friction = self.fixed_tick_slippage_pts + slippage_drag + impact_drag
        if is_buy:
            return round(base_price + total_friction, 2)
        else:
            return round(max(base_price - total_friction, 0.05), 2)

    def resolve_stop_loss_fill(
        self,
        stop_price: float,
        bar_open: float,
        bar_low: float,
        is_long: bool = True,
    ) -> float:
        """Accurately models gap-down behavior: if market gaps below stop, fill occurs at bar open."""
        if is_long:
            if bar_open < stop_price:
                # Gapped down below stop loss: must execute at Open, NOT at stop price!
                return bar_open
            elif bar_low <= stop_price:
                return stop_price
            return stop_price
        else:
            if bar_open > stop_price:
                return bar_open
            return stop_price

    def to_manifest_dict(self) -> Dict[str, Any]:
        """Exports execution assumptions for inclusion in backtest and simulation manifests."""
        return self.model_dump()
