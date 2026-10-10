import re

with open('oms_project/database.py', 'r') as f:
    content = f.read()

# Add table to CREATE_TABLES_SQL
new_tables = """
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
"""

content = content.replace("CREATE INDEX IF NOT EXISTS idx_capres_order_id ON capital_reservations(order_id);", 
                          "CREATE INDEX IF NOT EXISTS idx_capres_order_id ON capital_reservations(order_id);\n" + new_tables)

# Update ALLOWED_TRANSITIONS
new_transitions = """ALLOWED_TRANSITIONS = {
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
}"""

content = re.sub(r'ALLOWED_TRANSITIONS = \{.*?\}', new_transitions, content, flags=re.DOTALL)

with open('oms_project/database.py', 'w') as f:
    f.write(content)
