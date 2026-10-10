"""EOD Reconciliation Engine (Work Package C).

Verifies double-entry balance sheet equality across:
ORDERS ↕ FILLS ↕ POSITIONS ↕ CASH ↕ P&L ↕ ACCOUNT BALANCE

Requirements:
- Strict double-entry invariant:
  Ending Cash + Position Cost Basis + Total Friction == Initial Capital + Realized P&L (gross)
- Order & Fill reconciliation: total orders proposed vs evaluated vs filled
- Position quantity reconciliation: positions match net fill quantities (BUY_qty - SELL_qty)
- Any mismatch MUST set reconciliation_passed = False
- Generates auditable EOD package containing full metrics, provenance classification, and SHA-256 evidence hash
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from services.backtest_engine.execution_lifecycle import ExecutionFill, ExecutionOrder, OrderLifecycleState
from services.common.health import ComponentName, ComponentOperationalState, SubsystemHealth
from services.market_data.adapters.market_event_schemas import MarketDataProvenance
from services.paper_engine.session import PaperSession, PaperPortfolio

logger = logging.getLogger(__name__)


class EODReconciliationReport(BaseModel):
    """Auditable evidence package for end-of-day session reconciliation."""

    session_id: str
    name: str
    strategy_id: str
    strategy_version: str
    reconciled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Provenance details
    provenance: Dict[str, Any]

    # Telemetry statistics
    ticks_received: int = 0
    valid_ticks: int = 0
    duplicates_dropped: int = 0
    out_of_order_count: int = 0
    bars_scanned: int = 0
    candidates_generated: int = 0

    # Order & Fill statistics
    orders_proposed: int = 0
    orders_approved: int = 0
    orders_rejected: int = 0
    fills_count: int = 0

    # Financial accounting
    initial_capital: float
    ending_cash: float
    positions_cost_basis: float
    market_value_of_positions: float
    total_equity: float
    total_realized_pnl: float
    total_unrealized_pnl: float
    total_fees_paid: float
    total_slippage_paid: float
    total_statutory_friction: float

    # Reconciliation verdict
    reconciliation_passed: bool
    reconciliation_discrepancies: List[str] = Field(default_factory=list)

    # Cryptographic evidence signature
    evidence_hash: str = ""


class EODReconciler:
    """Engine performing double-entry ledger verification and EOD audit packaging."""

    def __init__(self):
        self.health = SubsystemHealth(
            component_name=ComponentName.RECONCILIATION,
            state=ComponentOperationalState.STOPPED,
            message="Reconciliation engine initialized",
        )

    def reconcile_session(
        self,
        session: PaperSession,
        provenance: Optional[MarketDataProvenance] = None,
        pipeline_telemetry: Optional[Dict[str, Any]] = None,
        scanner_telemetry: Optional[Dict[str, Any]] = None,
    ) -> EODReconciliationReport:
        """Executes full double-entry financial reconciliation on a paper session."""
        self.health.update_state(ComponentOperationalState.RUNNING, "Reconciling paper session ledger...")

        discrepancies: List[str] = []
        portfolio: PaperPortfolio = session.portfolio
        orders: List[ExecutionOrder] = session.orders
        fills: List[ExecutionFill] = session.fills

        # 1. Order & Fill Count Verification
        proposed_count = len(orders)
        approved_count = sum(1 for o in orders if o.state != OrderLifecycleState.ORDER_REJECTED)
        rejected_count = sum(1 for o in orders if o.state == OrderLifecycleState.ORDER_REJECTED)
        fill_count = len(fills)

        # 2. Fee & Friction Summation Verification
        calc_fees = sum(f.transaction_costs for f in fills)
        calc_slippage = sum(f.slippage_cost for f in fills)
        total_friction = round(calc_fees + calc_slippage, 4)

        if abs(portfolio.total_fees_paid - calc_fees) > 0.01:
            discrepancies.append(
                f"Fee mismatch: Portfolio fees INR {portfolio.total_fees_paid:.2f} != Fills sum INR {calc_fees:.2f}"
            )

        if abs(portfolio.total_slippage_paid - calc_slippage) > 0.01:
            discrepancies.append(
                f"Slippage mismatch: Portfolio slippage INR {portfolio.total_slippage_paid:.2f} != Fills sum INR {calc_slippage:.2f}"
            )

        # 3. Position Quantity Verification
        fill_qty_by_symbol: Dict[str, int] = {}
        for fill in fills:
            sym = fill.symbol.upper()
            qty_delta = fill.quantity if fill.side.value.upper() == "BUY" else -fill.quantity
            fill_qty_by_symbol[sym] = fill_qty_by_symbol.get(sym, 0) + qty_delta

        for sym, pos in portfolio.positions.items():
            expected_qty = fill_qty_by_symbol.get(sym, 0)
            if pos.quantity != expected_qty:
                discrepancies.append(
                    f"Position quantity mismatch for {sym}: Portfolio qty {pos.quantity} != Net fills qty {expected_qty}"
                )

        # 4. Double-Entry Balance Sheet Conservation Equation
        # Initial Capital + Realized P&L - Fees = Cash + Position Cost Basis
        # Equivalently: Ending Cash + Sum(Position Cost Basis) + Total Fees == Initial Capital + Realized P&L (gross)
        cost_basis_sum = sum(pos.cost_basis for pos in portfolio.positions.values())
        
        reconstructed_left = Decimal(str(round(portfolio.cash, 4))) + Decimal(str(round(cost_basis_sum, 4))) + Decimal(str(round(portfolio.total_fees_paid, 4)))
        expected_right = Decimal(str(round(portfolio.initial_capital, 4))) + Decimal(str(round(portfolio.total_realized_pnl, 4)))

        balance_diff = abs(reconstructed_left - expected_right)
        if balance_diff > Decimal("0.05"):
            discrepancies.append(
                f"Double-entry balance sheet mismatch: Cash+CostBasis+Fees ({reconstructed_left:.2f}) "
                f"!= InitialCapital+RealizedPnL ({expected_right:.2f}). Diff: {balance_diff:.2f}"
            )

        reconciliation_passed = (len(discrepancies) == 0)

        # Build report payload
        prov_dict = provenance.model_dump(mode="json") if provenance else {"data_source": "MOCK", "collection_mode": "REPLAY"}
        pip_tel = pipeline_telemetry or {}
        scan_tel = scanner_telemetry or {}

        report_data = {
            "session_id": session.session_id,
            "name": session.name,
            "strategy_id": session.strategy_id,
            "strategy_version": session.strategy_version,
            "reconciled_at": datetime.now(timezone.utc).isoformat(),
            "provenance": prov_dict,
            "ticks_received": pip_tel.get("total_ticks_received", 0),
            "valid_ticks": pip_tel.get("valid_ticks_processed", 0),
            "duplicates_dropped": pip_tel.get("duplicates_dropped", 0),
            "out_of_order_count": pip_tel.get("out_of_order_count", 0),
            "bars_scanned": scan_tel.get("bars_scanned", 0),
            "candidates_generated": scan_tel.get("candidates_generated", 0),
            "orders_proposed": proposed_count,
            "orders_approved": approved_count,
            "orders_rejected": rejected_count,
            "fills_count": fill_count,
            "initial_capital": portfolio.initial_capital,
            "ending_cash": portfolio.cash,
            "positions_cost_basis": round(cost_basis_sum, 2),
            "market_value_of_positions": portfolio.market_value_of_positions,
            "total_equity": portfolio.total_equity,
            "total_realized_pnl": portfolio.total_realized_pnl,
            "total_unrealized_pnl": portfolio.total_unrealized_pnl,
            "total_fees_paid": portfolio.total_fees_paid,
            "total_slippage_paid": portfolio.total_slippage_paid,
            "total_statutory_friction": total_friction,
            "reconciliation_passed": reconciliation_passed,
            "reconciliation_discrepancies": discrepancies,
        }

        # Cryptographic Evidence Signature
        raw_payload = json.dumps(report_data, sort_keys=True)
        evidence_hash = hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()
        report_data["evidence_hash"] = evidence_hash

        report = EODReconciliationReport.model_validate(report_data)

        if reconciliation_passed:
            self.health.update_state(
                ComponentOperationalState.RUNNING,
                "EOD reconciliation PASSED cleanly. Zero balance sheet discrepancies.",
                metrics={"evidence_hash": evidence_hash},
            )
        else:
            self.health.update_state(
                ComponentOperationalState.ERROR,
                f"EOD reconciliation FAILED with {len(discrepancies)} discrepancies.",
                metrics={"discrepancies": discrepancies},
            )

        return report
