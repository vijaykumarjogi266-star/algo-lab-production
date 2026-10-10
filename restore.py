import os

database_content = '''"""
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
"""

# Valid state machine transitions
ALLOWED_TRANSITIONS = {
    OrderState.RECEIVED: {OrderState.VALIDATED, OrderState.REJECTED},
    OrderState.VALIDATED: {OrderState.RISK_RESERVED, OrderState.REJECTED},
    OrderState.RISK_RESERVED: {OrderState.SUBMITTED, OrderState.SUBMISSION_UNKNOWN, OrderState.REJECTED},
    OrderState.SUBMITTED: {OrderState.ACKNOWLEDGED, OrderState.SUBMISSION_UNKNOWN, OrderState.REJECTED, OrderState.FILLED},
    OrderState.SUBMISSION_UNKNOWN: {OrderState.ACKNOWLEDGED, OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED},
    OrderState.ACKNOWLEDGED: {OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED},
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
'''

with open('oms_project/database.py', 'w') as f:
    f.write(database_content)

