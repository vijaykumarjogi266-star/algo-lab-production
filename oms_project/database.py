"""
OMS Project - Database Ledger & Order State Machine
Tracks order transitions through immutable states in PostgreSQL/SQLite ledger.
"""

import sqlite3
import json
import time
from typing import Dict, Any, List, Optional
from oms_project.schemas import OrderState, OrderIntent, OrderResult


CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS order_ledger (
    order_id TEXT PRIMARY KEY,
    request_id TEXT UNIQUE NOT NULL,
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    price REAL NOT NULL,
    state TEXT NOT NULL,
    reserved_value REAL DEFAULT 0.0,
    broker_order_id TEXT,
    execution_id TEXT,
    executed_qty REAL DEFAULT 0.0,
    execution_price REAL,
    execution_timestamp REAL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    reconciliation_required INTEGER DEFAULT 0,
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS state_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    timestamp REAL NOT NULL,
    reason TEXT,
    FOREIGN KEY(order_id) REFERENCES order_ledger(order_id)
);

CREATE TABLE IF NOT EXISTS executions_ledger (
    execution_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    qty REAL NOT NULL,
    price REAL NOT NULL,
    timestamp REAL NOT NULL,
    FOREIGN KEY(order_id) REFERENCES order_ledger(order_id)
);

CREATE TABLE IF NOT EXISTS capital_reservations (
    reservation_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    order_id TEXT,
    strategy_id TEXT,
    idempotency_key TEXT NOT NULL,
    requested_notional REAL NOT NULL,
    reserved_cash REAL NOT NULL,
    reserved_margin REAL NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    released_at REAL,
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE(account_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_capres_acc_status ON capital_reservations(account_id, status);
CREATE INDEX IF NOT EXISTS idx_capres_order_id ON capital_reservations(order_id);

CREATE TABLE IF NOT EXISTS broker_uncertainty_records (
    resolution_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    uncertainty_type TEXT NOT NULL,
    current_state TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    broker_order_id TEXT,
    correlation_id TEXT,
    detected_at REAL NOT NULL,
    lookup_attempts INTEGER DEFAULT 0,
    latest_lookup_error TEXT,
    resolution_status TEXT NOT NULL,
    evidence_ref TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    resolved_at REAL,
    metadata_json TEXT,
    UNIQUE(order_id, uncertainty_type)
);

CREATE TABLE IF NOT EXISTS shutdown_sessions (
    shutdown_session_id TEXT PRIMARY KEY,
    requested_at REAL NOT NULL,
    initiated_by TEXT,
    status TEXT NOT NULL,
    reason TEXT,
    started_at REAL NOT NULL,
    completed_at REAL,
    recovery_required INTEGER DEFAULT 1,
    recovery_completed_at REAL,
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS shutdown_events (
    shutdown_event_id TEXT PRIMARY KEY,
    shutdown_session_id TEXT NOT NULL,
    order_id TEXT,
    execution_id TEXT,
    event_type TEXT NOT NULL,
    correlation_id TEXT,
    occurred_at REAL NOT NULL,
    metadata_json TEXT,
    FOREIGN KEY(shutdown_session_id) REFERENCES shutdown_sessions(shutdown_session_id)
);
CREATE TABLE IF NOT EXISTS paper_accounts (
    account_id TEXT PRIMARY KEY,
    account_reference TEXT NOT NULL,
    account_type TEXT NOT NULL,
    base_currency TEXT NOT NULL,
    initial_capital TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS cash_ledger (
    cash_entry_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    currency TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    amount TEXT NOT NULL,
    related_execution_id TEXT,
    related_order_id TEXT,
    idempotency_key TEXT,
    correlation_id TEXT,
    occurred_at REAL NOT NULL,
    created_at REAL NOT NULL,
    metadata_json TEXT,
    FOREIGN KEY(account_id) REFERENCES paper_accounts(account_id)
);
CREATE INDEX IF NOT EXISTS idx_cash_ledger_execution ON cash_ledger(related_execution_id) WHERE related_execution_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_cash_ledger_idemp ON cash_ledger(idempotency_key) WHERE idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS positions (
    position_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    strategy_id TEXT,
    symbol TEXT NOT NULL,
    asset_class TEXT NOT NULL,
    currency TEXT NOT NULL,
    net_quantity TEXT NOT NULL,
    average_entry_price TEXT NOT NULL,
    realized_pnl TEXT NOT NULL,
    cumulative_fees TEXT NOT NULL,
    last_mark_price TEXT,
    mark_timestamp REAL,
    market_value TEXT NOT NULL,
    unrealized_pnl TEXT NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(account_id, strategy_id, symbol, currency)
);

CREATE TABLE IF NOT EXISTS position_lots (
    lot_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    strategy_id TEXT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    original_quantity TEXT NOT NULL,
    open_quantity TEXT NOT NULL,
    entry_price TEXT NOT NULL,
    opening_execution_id TEXT NOT NULL,
    opened_at REAL NOT NULL,
    closed_at REAL,
    metadata_json TEXT
);
CREATE TABLE IF NOT EXISTS reconciliation_runs (
    reconciliation_run_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    started_at REAL NOT NULL,
    completed_at REAL,
    status TEXT NOT NULL,
    snapshot_reference TEXT,
    internal_ledger_version TEXT,
    broker_cash TEXT,
    internal_cash TEXT,
    broker_equity TEXT,
    internal_equity TEXT,
    correlation_id TEXT,
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS reconciliation_breaks (
    break_id TEXT PRIMARY KEY,
    reconciliation_run_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    break_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    symbol TEXT,
    external_reference TEXT,
    internal_reference TEXT,
    expected_value TEXT,
    observed_value TEXT,
    currency TEXT,
    status TEXT NOT NULL,
    detected_at REAL NOT NULL,
    resolved_at REAL,
    evidence_reference TEXT,
    operator_rationale TEXT,
    correlation_id TEXT,
    metadata_json TEXT,
    FOREIGN KEY(reconciliation_run_id) REFERENCES reconciliation_runs(reconciliation_run_id)
);

CREATE TABLE IF NOT EXISTS dataset_registry (
    dataset_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    provider TEXT NOT NULL,
    acquisition_date TEXT NOT NULL,
    symbols_json TEXT NOT NULL,
    market TEXT NOT NULL,
    timezone TEXT NOT NULL,
    start_timestamp REAL NOT NULL,
    end_timestamp REAL NOT NULL,
    record_count INTEGER NOT NULL,
    schema_version TEXT NOT NULL,
    sha256_checksum TEXT NOT NULL,
    quality_status TEXT NOT NULL,
    owner TEXT NOT NULL,
    file_path TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS dataset_quality_reports (
    report_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    validated_at REAL NOT NULL,
    is_valid INTEGER NOT NULL,
    error_count INTEGER NOT NULL,
    warning_count INTEGER NOT NULL,
    details_json TEXT NOT NULL,
    FOREIGN KEY(dataset_id) REFERENCES dataset_registry(dataset_id)
);

CREATE TABLE IF NOT EXISTS replay_runs (
    replay_run_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    dataset_checksum TEXT NOT NULL,
    configuration_hash TEXT NOT NULL,
    started_at REAL NOT NULL,
    completed_at REAL,
    status TEXT NOT NULL,
    metadata_json TEXT,
    FOREIGN KEY(dataset_id) REFERENCES dataset_registry(dataset_id)
);

CREATE TABLE IF NOT EXISTS replay_execution_reports (
    report_id TEXT PRIMARY KEY,
    replay_run_id TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    dataset_checksum TEXT NOT NULL,
    total_ticks INTEGER NOT NULL,
    total_decisions INTEGER NOT NULL,
    total_orders INTEGER NOT NULL,
    total_fills INTEGER NOT NULL,
    total_rejections INTEGER NOT NULL,
    initial_cash TEXT NOT NULL,
    final_equity TEXT NOT NULL,
    net_pnl TEXT NOT NULL,
    max_drawdown_pct TEXT NOT NULL,
    turnover TEXT NOT NULL,
    total_fees TEXT NOT NULL,
    total_slippage TEXT NOT NULL,
    reconciliation_status TEXT NOT NULL,
    regimes_summary_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY(replay_run_id) REFERENCES replay_runs(replay_run_id),
    FOREIGN KEY(dataset_id) REFERENCES dataset_registry(dataset_id)
);
"""

# Valid state machine transitions
ALLOWED_TRANSITIONS = {
    OrderState.RECEIVED: {OrderState.VALIDATED, OrderState.REJECTED},
    OrderState.VALIDATED: {OrderState.RISK_RESERVED, OrderState.REJECTED},
    OrderState.RISK_RESERVED: {OrderState.SUBMITTING, OrderState.SUBMITTED, OrderState.SUBMISSION_UNKNOWN, OrderState.REJECTED},
    OrderState.SUBMITTING: {OrderState.SUBMITTED, OrderState.SUBMISSION_UNKNOWN, OrderState.REJECTED},
    OrderState.SUBMITTED: {OrderState.ACKNOWLEDGED, OrderState.SUBMISSION_UNKNOWN, OrderState.REJECTED, OrderState.FILLED, OrderState.LIVE},
    OrderState.SUBMISSION_UNKNOWN: {OrderState.ACKNOWLEDGED, OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED, OrderState.LIVE, OrderState.PARTIALLY_FILLED},
    OrderState.ACKNOWLEDGED: {OrderState.LIVE, OrderState.FILLED, OrderState.CANCEL_PENDING, OrderState.CANCELLED, OrderState.REJECTED},
    OrderState.LIVE: {OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.CANCEL_PENDING, OrderState.CANCEL_UNKNOWN, OrderState.CANCELLED},
    OrderState.PARTIALLY_FILLED: {OrderState.FILLED, OrderState.CANCEL_PENDING, OrderState.CANCEL_UNKNOWN, OrderState.CANCELLED},
    OrderState.CANCEL_PENDING: {OrderState.CANCELLED, OrderState.CANCEL_UNKNOWN, OrderState.FILLED, OrderState.PARTIALLY_FILLED, OrderState.LIVE},
    OrderState.CANCEL_UNKNOWN: {OrderState.CANCELLED, OrderState.FILLED, OrderState.PARTIALLY_FILLED, OrderState.LIVE},
    OrderState.FILLED: set(),
    OrderState.CANCELLED: set(),
    OrderState.REJECTED: set(),
}


class OrderLedgerDB:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        with self.conn:
            self.conn.executescript(CREATE_TABLES_SQL)

    def record_received_order(self, intent: OrderIntent) -> str:
        order_id = f"ORD_{intent.request_id}"
        now = time.time()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO order_ledger 
                (order_id, request_id, strategy_id, symbol, side, qty, price, state, reserved_value, broker_order_id, execution_id, executed_qty, execution_price, execution_timestamp, created_at, updated_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    intent.request_id,
                    intent.strategy_id,
                    intent.symbol,
                    intent.side.value,
                    intent.qty,
                    intent.price,
                    OrderState.RECEIVED.value,
                    0.0,
                    None,
                    None,
                    0.0,
                    None,
                    None,
                    now,
                    now,
                    json.dumps({"signature": intent.signature}),
                )
            )
            self.conn.execute(
                "INSERT INTO state_transitions (order_id, from_state, to_state, timestamp, reason) VALUES (?, ?, ?, ?, ?)",
                (order_id, "NONE", OrderState.RECEIVED.value, now, "Order Intent Received")
            )
        return order_id

    def transition_state(self, order_id: str, new_state: OrderState, reason: str = "", reserved_value: float = 0.0, broker_order_id: Optional[str] = None, execution_id: Optional[str] = None, executed_qty: Optional[float] = None, execution_price: Optional[float] = None) -> bool:
        now = time.time()
        with self.conn:
            cur = self.conn.execute("SELECT state, reserved_value FROM order_ledger WHERE order_id = ?", (order_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Order {order_id} not found")

            current_state = OrderState(row["state"])
            valid_next = ALLOWED_TRANSITIONS.get(current_state, set())

            if new_state not in valid_next and current_state != new_state:
                raise ValueError(f"Invalid state transition from {current_state} to {new_state}")

            reconciliation_flag = 1 if new_state == OrderState.SUBMISSION_UNKNOWN else 0
            res_val = reserved_value if reserved_value > 0 else row["reserved_value"]

            # Update additional fields if provided
            updates = ["state = ?", "reserved_value = ?", "updated_at = ?", "reconciliation_required = MAX(reconciliation_required, ?)"]
            params = [new_state.value, res_val, now, reconciliation_flag]
            
            if broker_order_id is not None:
                updates.append("broker_order_id = ?")
                params.append(broker_order_id)
            if execution_id is not None:
                updates.append("execution_id = ?")
                params.append(execution_id)
            if executed_qty is not None:
                updates.append("executed_qty = executed_qty + ?")
                params.append(executed_qty)
            if execution_price is not None:
                updates.append("execution_price = ?")
                params.append(execution_price)
                updates.append("execution_timestamp = ?")
                params.append(now)

            params.append(order_id)
            update_sql = f"UPDATE order_ledger SET {', '.join(updates)} WHERE order_id = ?"
            
            self.conn.execute(update_sql, tuple(params))
            self.conn.execute(
                "INSERT INTO state_transitions (order_id, from_state, to_state, timestamp, reason) VALUES (?, ?, ?, ?, ?)",
                (order_id, current_state.value, new_state.value, now, reason)
            )
        return True

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.execute("SELECT * FROM order_ledger WHERE order_id = ?", (order_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def get_reconciliation_orders(self) -> List[Dict[str, Any]]:
        cur = self.conn.execute("SELECT * FROM order_ledger WHERE reconciliation_required = 1")
        return [dict(r) for r in cur.fetchall()]

    def reset_ledger(self):
        """Wipes order ledger and state transitions for clean-slate simulation resets."""
        with self.conn:
            self.conn.execute("DELETE FROM executions_ledger")
            self.conn.execute("DELETE FROM state_transitions")
            self.conn.execute("DELETE FROM order_ledger")

    def record_execution(self, execution_id: str, order_id: str, qty: float, price: float) -> bool:
        """Records a unique execution event. Returns False if duplicate."""
        now = time.time()
        try:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO executions_ledger (execution_id, order_id, qty, price, timestamp) VALUES (?, ?, ?, ?, ?)",
                    (execution_id, order_id, qty, price, now)
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def record_uncertainty(self, resolution_id: str, order_id: str, account_id: str, uncertainty_type: str, current_state: str, idempotency_key: str, broker_order_id: Optional[str] = None):
        now = time.time()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO broker_uncertainty_records 
                (resolution_id, order_id, account_id, uncertainty_type, current_state, idempotency_key, broker_order_id, detected_at, resolution_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(order_id, uncertainty_type) DO UPDATE SET 
                updated_at=excluded.updated_at,
                current_state=excluded.current_state
                """,
                (resolution_id, order_id, account_id, uncertainty_type, current_state, idempotency_key, broker_order_id, now, "OPEN", now, now)
            )

    def resolve_uncertainty(self, order_id: str, uncertainty_type: str, evidence_ref: str):
        now = time.time()
        with self.conn:
            self.conn.execute(
                """
                UPDATE broker_uncertainty_records
                SET resolution_status = 'RESOLVED', evidence_ref = ?, resolved_at = ?, updated_at = ?
                WHERE order_id = ? AND uncertainty_type = ?
                """,
                (evidence_ref, now, now, order_id, uncertainty_type)
            )
