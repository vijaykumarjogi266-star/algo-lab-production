import sqlite3
import uuid
import time
import json
from decimal import Decimal
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from enum import Enum

class BreakType(str, Enum):
    POSITION_MISMATCH = "POSITION_MISMATCH"
    CASH_MISMATCH = "CASH_MISMATCH"
    FEE_MISMATCH = "FEE_MISMATCH"
    EXECUTION_MISMATCH = "EXECUTION_MISMATCH"
    ORDER_STATUS_MISMATCH = "ORDER_STATUS_MISMATCH"
    MISSING_EXECUTION_EVIDENCE = "MISSING_EXECUTION_EVIDENCE"
    MISSING_INTERNAL_ORDER = "MISSING_INTERNAL_ORDER"
    STALE_EXTERNAL_SNAPSHOT = "STALE_EXTERNAL_SNAPSHOT"

class BreakSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    MATERIAL = "MATERIAL"
    CRITICAL = "CRITICAL"

class BreakStatus(str, Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    ACCEPTED_ADJUSTMENT = "ACCEPTED_ADJUSTMENT"
    FALSE_POSITIVE = "FALSE_POSITIVE"

# DTOs
class ExternalAccountSnapshot(BaseModel):
    provider: str
    external_account_id: str
    snapshot_reference: str
    timestamp: float
    currency: str
    cash_balance: Optional[Decimal] = None
    equity: Optional[Decimal] = None
    margin_used: Optional[Decimal] = None
    available_margin: Optional[Decimal] = None
    source: str
    quality_status: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ExternalPositionSnapshot(BaseModel):
    provider: str
    account_id: str
    symbol: str
    asset_class: str
    currency: str
    quantity: Decimal
    average_price: Optional[Decimal] = None
    mark_price: Optional[Decimal] = None
    market_value: Optional[Decimal] = None
    timestamp: float
    source: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ExternalOrderSnapshot(BaseModel):
    provider: str
    external_order_id: str
    internal_order_id: Optional[str] = None
    client_reference: Optional[str] = None
    symbol: str
    side: str
    quantity: Decimal
    filled_quantity: Decimal
    pending_quantity: Decimal
    average_fill_price: Optional[Decimal] = None
    status: str
    timestamp: float
    source: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ExternalExecutionEvidence(BaseModel):
    provider: str
    external_execution_id: str
    external_order_id: Optional[str] = None
    internal_order_id: Optional[str] = None
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    fee: Optional[Decimal] = None
    execution_timestamp: float
    received_timestamp: float
    source: str
    raw_reference: str

class ReconciliationSnapshot(BaseModel):
    provider: str
    account_id: str
    collection_timestamp: float
    account_snapshot: ExternalAccountSnapshot
    positions: List[ExternalPositionSnapshot]
    orders: List[ExternalOrderSnapshot]
    executions: List[ExternalExecutionEvidence]
    quality_metadata: Dict[str, Any] = Field(default_factory=dict)


class ReconciliationService:
    def __init__(self, db_conn: sqlite3.Connection):
        self.db = db_conn

    def can_accept_new_entries(self, account_id: str) -> bool:
        cur = self.db.execute(
            "SELECT count(*) as c FROM reconciliation_breaks WHERE account_id=? AND status IN ('OPEN', 'INVESTIGATING') AND severity IN ('MATERIAL', 'CRITICAL')",
            (account_id,)
        )
        row = cur.fetchone()
        if row and row["c"] > 0:
            return False
        return True

    def get_open_breaks(self, account_id: str) -> List[Dict[str, Any]]:
        cur = self.db.execute("SELECT * FROM reconciliation_breaks WHERE account_id=? AND status IN ('OPEN', 'INVESTIGATING')", (account_id,))
        return [dict(row) for row in cur.fetchall()]

    def resolve_break(self, break_id: str, evidence: str, rationale: str = "", new_status: BreakStatus = BreakStatus.RESOLVED):
        if new_status not in (BreakStatus.RESOLVED, BreakStatus.ACCEPTED_ADJUSTMENT, BreakStatus.FALSE_POSITIVE):
            raise ValueError(f"Invalid terminal status for break resolution: {new_status}")
        with self.db:
            self.db.execute(
                "UPDATE reconciliation_breaks SET status=?, resolved_at=?, evidence_reference=?, operator_rationale=? WHERE break_id=? AND status IN ('OPEN', 'INVESTIGATING')",
                (new_status.value, time.time(), evidence, rationale, break_id)
            )

    def reconcile_account(self, account_id: str, snapshot: ReconciliationSnapshot) -> str:
        with self.db:
            run_id = str(uuid.uuid4())
            now = time.time()
            
            # Check if this exact snapshot is already running/done (idempotency by snapshot_reference)
            cur = self.db.execute("SELECT reconciliation_run_id FROM reconciliation_runs WHERE snapshot_reference=? AND account_id=?", (snapshot.account_snapshot.snapshot_reference, account_id))
            row = cur.fetchone()
            if row:
                return row["reconciliation_run_id"]
            
            self.db.execute(
                "INSERT INTO reconciliation_runs (reconciliation_run_id, account_id, provider, started_at, status, snapshot_reference) VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, account_id, snapshot.provider, now, "RUNNING", snapshot.account_snapshot.snapshot_reference)
            )
            
            self._reconcile_cash(run_id, account_id, snapshot.account_snapshot)
            self._reconcile_positions(run_id, account_id, snapshot.positions)
            self._reconcile_orders(run_id, account_id, snapshot.orders)
            self._reconcile_executions(run_id, account_id, snapshot.executions)
            
            # Update status
            cur = self.db.execute("SELECT count(*) as c FROM reconciliation_breaks WHERE reconciliation_run_id=?", (run_id,))
            c = cur.fetchone()["c"]
            status = "DISCREPANCY" if c > 0 else "CLEAN"
            
            self.db.execute("UPDATE reconciliation_runs SET status=?, completed_at=? WHERE reconciliation_run_id=?", (status, now, run_id))
            return run_id

    def _record_break(self, run_id: str, account_id: str, provider: str, b_type: BreakType, sev: BreakSeverity, exp: str, obs: str, symbol: str = None, ext_ref: str = None, int_ref: str = None):
        # Prevent identical open breaks
        cur = self.db.execute(
            "SELECT break_id FROM reconciliation_breaks WHERE account_id=? AND break_type=? AND external_reference=? AND expected_value=? AND observed_value=? AND status IN ('OPEN', 'INVESTIGATING')",
            (account_id, b_type.value, ext_ref, exp, obs)
        )
        if cur.fetchone():
            return
            
        self.db.execute(
            "INSERT INTO reconciliation_breaks (break_id, reconciliation_run_id, account_id, provider, break_type, severity, expected_value, observed_value, symbol, external_reference, internal_reference, status, detected_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), run_id, account_id, provider, b_type.value, sev.value, exp, obs, symbol, ext_ref, int_ref, "OPEN", time.time())
        )

    def _reconcile_cash(self, run_id: str, account_id: str, account_snap: ExternalAccountSnapshot):
        if account_snap.cash_balance is None:
            return
            
        cur = self.db.execute("SELECT SUM(CAST(amount AS REAL)) as total FROM cash_ledger WHERE account_id=?", (account_id,))
        row = cur.fetchone()
        internal_cash = Decimal(str(row["total"] or "0.0"))
        
        if internal_cash != account_snap.cash_balance:
            self._record_break(
                run_id, account_id, account_snap.provider, BreakType.CASH_MISMATCH, BreakSeverity.MATERIAL,
                str(internal_cash), str(account_snap.cash_balance), ext_ref=account_snap.external_account_id
            )

    def _reconcile_positions(self, run_id: str, account_id: str, ext_positions: List[ExternalPositionSnapshot]):
        # Internal positions
        cur = self.db.execute("SELECT symbol, net_quantity FROM positions WHERE account_id=?", (account_id,))
        int_pos = {row["symbol"]: Decimal(row["net_quantity"]) for row in cur.fetchall()}
        
        ext_pos_map = {p.symbol: p.quantity for p in ext_positions}
        
        all_symbols = set(int_pos.keys()).union(ext_pos_map.keys())
        for sym in all_symbols:
            iq = int_pos.get(sym, Decimal("0.0"))
            eq = ext_pos_map.get(sym, Decimal("0.0"))
            if iq != eq:
                self._record_break(
                    run_id, account_id, ext_positions[0].provider if ext_positions else "UNKNOWN",
                    BreakType.POSITION_MISMATCH, BreakSeverity.MATERIAL,
                    str(iq), str(eq), symbol=sym
                )

    def _reconcile_orders(self, run_id: str, account_id: str, ext_orders: List[ExternalOrderSnapshot]):
        for eo in ext_orders:
            if not eo.internal_order_id:
                # Missing internal order
                self._record_break(
                    run_id, account_id, eo.provider, BreakType.MISSING_INTERNAL_ORDER, BreakSeverity.MATERIAL,
                    "None", eo.external_order_id, symbol=eo.symbol, ext_ref=eo.external_order_id
                )
                continue
                
            cur = self.db.execute("SELECT state FROM order_ledger WHERE order_id=?", (eo.internal_order_id,))
            row = cur.fetchone()
            if not row:
                self._record_break(
                    run_id, account_id, eo.provider, BreakType.MISSING_INTERNAL_ORDER, BreakSeverity.MATERIAL,
                    "None", eo.external_order_id, symbol=eo.symbol, ext_ref=eo.external_order_id, int_ref=eo.internal_order_id
                )
            else:
                int_state = row["state"]
                if eo.status != int_state:
                    # Specific material checks
                    # external OPEN versus internal CANCELLED
                    # external CANCELLED versus internal LIVE
                    # external REJECTED versus internal active state
                    # external FILLED versus internal LIVE/PARTIALLY_FILLED
                    
                    is_material = False
                    if eo.status == "OPEN" and int_state == "CANCELLED":
                        is_material = True
                    elif eo.status == "CANCELLED" and int_state in ("OPEN", "PENDING", "LIVE", "PARTIALLY_FILLED"):
                        is_material = True
                    elif eo.status == "REJECTED" and int_state in ("OPEN", "PENDING", "LIVE", "PARTIALLY_FILLED"):
                        is_material = True
                    elif eo.status == "FILLED" and int_state in ("OPEN", "PENDING", "LIVE", "PARTIALLY_FILLED"):
                        is_material = True
                        
                    sev = BreakSeverity.MATERIAL if is_material else BreakSeverity.WARNING
                    
                    self._record_break(
                        run_id, account_id, eo.provider, BreakType.ORDER_STATUS_MISMATCH, sev,
                        int_state, eo.status, symbol=eo.symbol, ext_ref=eo.external_order_id, int_ref=eo.internal_order_id
                    )

    def _reconcile_executions(self, run_id: str, account_id: str, ext_execs: List[ExternalExecutionEvidence]):
        for ex in ext_execs:
            cur = self.db.execute("SELECT execution_id FROM executions_ledger WHERE execution_id=?", (ex.external_execution_id,))
            if not cur.fetchone():
                # Execution exists externally but not internally
                self._record_break(
                    run_id, account_id, ex.provider, BreakType.MISSING_EXECUTION_EVIDENCE, BreakSeverity.MATERIAL,
                    "None", ex.external_execution_id, symbol=ex.symbol, ext_ref=ex.external_execution_id, int_ref=ex.internal_order_id
                )
            else:
                if ex.fee is not None:
                    cur_fee = self.db.execute(
                        "SELECT SUM(CAST(amount AS REAL)) as total_fee FROM cash_ledger WHERE entry_type='FEE' AND related_execution_id=?",
                        (f"fee_{ex.external_execution_id}",)
                    )
                    row_fee = cur_fee.fetchone()
                    
                    # Internal fees are stored as negative numbers
                    internal_fee = Decimal(str(row_fee["total_fee"] or "0.0"))
                    internal_fee_abs = abs(internal_fee)
                    external_fee = abs(ex.fee)
                    
                    if internal_fee_abs != external_fee:
                        self._record_break(
                            run_id, account_id, ex.provider, BreakType.FEE_MISMATCH, BreakSeverity.MATERIAL,
                            str(internal_fee_abs), str(external_fee), symbol=ex.symbol, ext_ref=ex.external_execution_id, int_ref=ex.internal_order_id
                        )
