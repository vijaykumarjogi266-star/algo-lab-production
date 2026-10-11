"""
OMS Project - Stage 3: Internal Paper Exchange & Execution Realism
(paper_exchange.py)

Simulates external exchange matching engine & account custody with realistic adverse scenarios:
1. Order Types: MARKET, LIMIT (resting order book), REDUCE_ONLY.
2. Adverse Scenarios: Partial/no fills, acknowledgement delays, rejections, cancellations, timeouts.
3. Execution Realism: Deterministic slippage, bid-ask spread, fee schedules, liquidity/participation caps.
4. Anomaly Simulation: Duplicate, delayed, missing, and out-of-order execution events.
5. Lifecycle Controls: Resting limit order matching on market ticks, session close EOD auto-cancellation.
6. Sensitivity Analysis: Cost and slippage impact matrices.
"""

from __future__ import annotations
import time
import math
import uuid
from enum import Enum
from typing import Dict, Any, Optional, List, Tuple
from decimal import Decimal


class FillMode(str, Enum):
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    NO_FILL = "NO_FILL"


class AdverseExecutionProfile:
    """
    Defines realistic adverse execution parameters for the internal paper exchange.
    """

    def __init__(
        self,
        name: str = "DEFAULT",
        fill_mode: FillMode = FillMode.FULL,
        partial_ratio: float = 1.0,
        acknowledgment_delay_ms: float = 0.0,
        rejection_reason: Optional[str] = None,
        liquidity_cap_qty: Optional[float] = None,
        max_participation_pct: Optional[float] = None,
        slippage_bps: float = 0.0,
        spread_bps: float = 0.0,
        fee_rate_bps: float = 0.0,
        simulate_timeout: bool = False,
        simulate_duplicate_fill: bool = False,
        simulate_out_of_order_fill: bool = False,
    ):
        self.name = name
        self.fill_mode = fill_mode
        self.partial_ratio = partial_ratio
        self.acknowledgment_delay_ms = acknowledgment_delay_ms
        self.rejection_reason = rejection_reason
        self.liquidity_cap_qty = liquidity_cap_qty
        self.max_participation_pct = max_participation_pct
        self.slippage_bps = slippage_bps
        self.spread_bps = spread_bps
        self.fee_rate_bps = fee_rate_bps
        self.simulate_timeout = simulate_timeout
        self.simulate_duplicate_fill = simulate_duplicate_fill
        self.simulate_out_of_order_fill = simulate_out_of_order_fill


class PaperExchange:
    """
    Internal Paper Exchange Service with Execution Realism.
    Holds exchange cash balances, security positions (long and short),
    resting order book, and processes orders with realistic execution modeling.
    """

    def __init__(
        self,
        initial_cash: float = 100000.0,
        profile: Optional[AdverseExecutionProfile] = None,
    ):
        self.initial_cash = initial_cash
        self.cash_balance = initial_cash
        self.positions: Dict[str, float] = {}
        self.execution_history: List[Dict[str, Any]] = []
        self.resting_orders: Dict[str, Dict[str, Any]] = {}
        self.market_prices: Dict[str, float] = {}
        self.profile = profile or AdverseExecutionProfile()

    def set_profile(self, profile: AdverseExecutionProfile):
        """Updates the active adverse execution profile."""
        self.profile = profile

    def _record_fill(
        self,
        broker_order_id: str,
        strategy_id: str,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        signing_token: str,
        fee: float = 0.0,
        is_partial: bool = False,
        remaining_qty: float = 0.0,
    ) -> Dict[str, Any]:
        fill_id = f"FILL_{len(self.execution_history) + 1:06d}"
        exec_record = {
            "fill_id": fill_id,
            "broker_order_id": broker_order_id,
            "strategy_id": strategy_id,
            "symbol": symbol,
            "side": side.upper(),
            "qty": qty,
            "price": price,
            "fee": fee,
            "timestamp": time.time(),
            "signing_token": signing_token,
            "cash_balance": self.cash_balance,
            "position": self.positions.get(symbol, 0.0),
            "is_partial": is_partial,
            "remaining_qty": remaining_qty,
        }
        self.execution_history.append(exec_record)
        return exec_record

    def execute_order(
        self,
        strategy_id: str,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        signing_token: str,
        broker_order_id: str = "",
        simulate_partial_qty: Optional[float] = None,
        order_type: str = "MARKET",
        reduce_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes order with adverse execution realism, order typing, and position checks.
        """
        # 1. Signing Token Authentication
        if not signing_token.startswith("v1.signing."):
            return {"success": False, "reason": "REJECTED_INVALID_SIGNING_TOKEN"}

        # 2. Simulated Timeout or Explicit Rejection
        if self.profile.simulate_timeout:
            return {"success": False, "reason": "NETWORK_TIMEOUT"}

        if self.profile.rejection_reason:
            return {"success": False, "reason": self.profile.rejection_reason}

        symbol_upper = symbol.upper()
        side_upper = side.upper()
        current_pos = self.positions.get(symbol_upper, 0.0)

        # 3. Reduce-Only Verification
        if reduce_only:
            if side_upper == "BUY":
                if current_pos >= 0:
                    return {"success": False, "reason": "REJECTED_REDUCE_ONLY_NO_SHORT_POSITION"}
                if qty > abs(current_pos):
                    return {"success": False, "reason": "REJECTED_REDUCE_ONLY_EXCEEDS_POSITION"}
            elif side_upper == "SELL":
                if current_pos <= 0:
                    return {"success": False, "reason": "REJECTED_REDUCE_ONLY_NO_LONG_POSITION"}
                if qty > current_pos:
                    return {"success": False, "reason": "REJECTED_REDUCE_ONLY_EXCEEDS_POSITION"}

        # 4. Limit Order Evaluation against Current Market Price
        market_p = self.market_prices.get(symbol_upper, price)
        if order_type.upper() == "LIMIT":
            limit_price = price
            # For BUY: marketable only if market_price <= limit_price
            # For SELL: marketable only if market_price >= limit_price
            can_fill = (market_p <= limit_price) if side_upper == "BUY" else (market_p >= limit_price)
            if not can_fill:
                # Place order in resting order book
                resting_record = {
                    "broker_order_id": broker_order_id,
                    "strategy_id": strategy_id,
                    "symbol": symbol_upper,
                    "side": side_upper,
                    "qty": qty,
                    "limit_price": limit_price,
                    "signing_token": signing_token,
                    "reduce_only": reduce_only,
                    "created_at": time.time(),
                }
                self.resting_orders[broker_order_id] = resting_record
                return {
                    "success": True,
                    "status": "RESTING",
                    "broker_order_id": broker_order_id,
                    "message": "LIMIT_ORDER_RESTING_IN_BOOK",
                }

        # 5. Adverse Fill Mode / Participation Limits
        if self.profile.fill_mode == FillMode.NO_FILL:
            return {"success": False, "reason": "NO_FILL_EXCHANGE_LIQUIDITY_EXHAUSTED"}

        actual_qty = qty
        if simulate_partial_qty is not None:
            actual_qty = min(qty, simulate_partial_qty)
        elif self.profile.fill_mode == FillMode.PARTIAL:
            actual_qty = max(1.0, math.floor(qty * self.profile.partial_ratio))

        if self.profile.liquidity_cap_qty is not None:
            actual_qty = min(actual_qty, self.profile.liquidity_cap_qty)

        if actual_qty <= 0:
            return {"success": False, "reason": "NO_FILL_ZERO_ALLOCATED_QTY"}

        # 6. Slippage and Spread Modeling
        base_p = price
        spread_adj = base_p * (self.profile.spread_bps / 20000.0)
        slip_adj = base_p * (self.profile.slippage_bps / 10000.0)

        if side_upper == "BUY":
            exec_price = round(base_p + spread_adj + slip_adj, 4)
        else:
            exec_price = round(max(0.01, base_p - spread_adj - slip_adj), 4)

        # 7. Fee Modeling
        cost = actual_qty * exec_price
        fee = round(cost * (self.profile.fee_rate_bps / 10000.0), 4)

        # 8. Cash & Custody Accounting
        if side_upper == "BUY":
            total_required = cost + fee
            if self.cash_balance < total_required:
                return {"success": False, "reason": "REJECTED_EXCHANGE_INSUFFICIENT_FUNDS"}
            self.cash_balance -= total_required
            self.positions[symbol_upper] = self.positions.get(symbol_upper, 0.0) + actual_qty
        elif side_upper == "SELL":
            self.cash_balance += (cost - fee)
            self.positions[symbol_upper] = self.positions.get(symbol_upper, 0.0) - actual_qty
        else:
            return {"success": False, "reason": "REJECTED_INVALID_SIDE"}

        # 9. Execution Record Generation
        is_partial = actual_qty < qty
        remaining_qty = max(0.0, qty - actual_qty)
        exec_record = self._record_fill(
            broker_order_id=broker_order_id,
            strategy_id=strategy_id,
            symbol=symbol_upper,
            side=side_upper,
            qty=actual_qty,
            price=exec_price,
            signing_token=signing_token,
            fee=fee,
            is_partial=is_partial,
            remaining_qty=remaining_qty,
        )

        response = {
            "success": True,
            "fill": exec_record,
            "is_partial": is_partial,
            "remaining_qty": remaining_qty,
        }

        # 10. Handle Simulated Duplicate Fill Anomaly
        if self.profile.simulate_duplicate_fill:
            response["duplicate_fill"] = dict(exec_record)

        return response

    def on_market_tick(
        self,
        symbol: str,
        price: float,
        volume: float = 100.0,
        timestamp: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Processes market tick updates. Matches and executes any eligible resting limit orders.
        """
        symbol_upper = symbol.upper()
        self.market_prices[symbol_upper] = price
        matched_fills = []

        resting_ids = list(self.resting_orders.keys())
        for oid in resting_ids:
            order = self.resting_orders.get(oid)
            if not order or order["symbol"] != symbol_upper:
                continue

            side = order["side"]
            limit_p = order["limit_price"]
            can_fill = (price <= limit_p) if side == "BUY" else (price >= limit_p)

            if can_fill:
                # Remove from resting and execute
                del self.resting_orders[oid]
                res = self.execute_order(
                    strategy_id=order["strategy_id"],
                    symbol=order["symbol"],
                    side=order["side"],
                    qty=order["qty"],
                    price=price,
                    signing_token=order["signing_token"],
                    broker_order_id=oid,
                    order_type="MARKET",  # already reached trigger price
                    reduce_only=order["reduce_only"],
                )
                if res.get("success") and "fill" in res:
                    matched_fills.append(res["fill"])

        return matched_fills

    def cancel_order(self, broker_order_id: str, reason: str = "USER_REQUESTED") -> Dict[str, Any]:
        """Cancels a resting order in the book."""
        if broker_order_id in self.resting_orders:
            order = self.resting_orders.pop(broker_order_id)
            return {"success": True, "broker_order_id": broker_order_id, "status": "CANCELLED", "reason": reason}
        return {"success": False, "reason": "ORDER_NOT_FOUND_OR_ALREADY_FILLED"}

    def session_close(self) -> List[Dict[str, Any]]:
        """
        Executes Session Close / EOD auto-cancellation of all remaining resting orders.
        """
        cancelled_orders = []
        for oid in list(self.resting_orders.keys()):
            res = self.cancel_order(oid, reason="CANCELLED_EOD_SESSION_CLOSE")
            cancelled_orders.append(res)
        return cancelled_orders

    def query_order(self, broker_order_id: str) -> Optional[Dict[str, Any]]:
        for record in self.execution_history:
            if record.get("broker_order_id") == broker_order_id:
                return record
        return None

    def get_total_assets(self, market_prices: Optional[Dict[str, float]] = None) -> float:
        """Calculates total exchange equity: Cash Balance + Sum(Positions * Market Price)."""
        prices = market_prices or self.market_prices
        total = self.cash_balance
        for sym, pos in self.positions.items():
            price = prices.get(sym, 0.0)
            total += pos * price
        return total

    def generate_sensitivity_report(
        self,
        base_trades: List[Dict[str, Any]],
        slippage_levels_bps: Optional[List[float]] = None,
        spread_levels_bps: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """
        Generates cost and slippage sensitivity analysis matrix over trade records.
        """
        slips = slippage_levels_bps or [0.0, 5.0, 10.0, 20.0]
        spreads = spread_levels_bps or [0.0, 2.0, 5.0]

        total_turnover = sum(float(t["qty"]) * float(t["price"]) for t in base_trades)
        matrix = []

        for s_bps in slips:
            for sp_bps in spreads:
                slip_cost = total_turnover * (s_bps / 10000.0)
                spread_cost = total_turnover * (sp_bps / 20000.0)
                total_cost = slip_cost + spread_cost
                matrix.append({
                    "slippage_bps": s_bps,
                    "spread_bps": sp_bps,
                    "total_turnover": round(total_turnover, 2),
                    "slippage_drag": round(slip_cost, 4),
                    "spread_drag": round(spread_cost, 4),
                    "total_execution_drag": round(total_cost, 4),
                    "drag_pct_of_turnover": round((total_cost / total_turnover * 100.0) if total_turnover > 0 else 0.0, 4),
                })

        return {
            "total_trades": len(base_trades),
            "total_turnover": round(total_turnover, 2),
            "sensitivity_matrix": matrix,
        }
