import pytest
import time
from decimal import Decimal
from oms_project.gateway import BrokerGateway
from oms_project.schemas import OrderIntent, OrderSide
from oms_project.reconciliation import (
    ReconciliationSnapshot, ExternalAccountSnapshot, ExternalOrderSnapshot, ExternalExecutionEvidence,
    BreakType, BreakSeverity, BreakStatus
)

def create_snapshot(account_id="PAPER_DEFAULT", ref="snap_1", ext_orders=None, ext_execs=None):
    return ReconciliationSnapshot(
        provider="TEST", account_id=account_id, collection_timestamp=time.time(),
        account_snapshot=ExternalAccountSnapshot(
            provider="TEST", external_account_id="EXT1", snapshot_reference=ref, cash_balance=Decimal("100000.0"),
            timestamp=time.time(), currency="INR", source="TEST", quality_status="OK"
        ),
        positions=[], orders=ext_orders or [], executions=ext_execs or []
    )

def test_restart_reconciliation_hold_returns_explicit_code_and_has_no_side_effects():
    gw = BrokerGateway()
    gw.reset_simulation()
    gw.reconciliation._record_break("run1", "PAPER_DEFAULT", "TEST", BreakType.CASH_MISMATCH, BreakSeverity.MATERIAL, "1", "2")
    intent = OrderIntent(request_id="req1", strategy_id="S1", symbol="REL", side=OrderSide.BUY, qty=10.0, price=100.0, signature="X")
    res = gw.process_order_intent(intent)
    assert res.status.value == "REJECTED"
    assert "RECONCILIATION_HOLD" in res.message
    cur = gw.db.conn.execute("SELECT count(*) as c FROM order_ledger")
    assert cur.fetchone()["c"] == 0

def test_material_break_persists_after_restart_and_blocks_entry(tmp_path):
    gw1 = BrokerGateway(db_path=str(tmp_path / "test.db"))
    gw1.reset_simulation()
    gw1.reconciliation._record_break("run1", "PAPER_DEFAULT", "TEST", BreakType.CASH_MISMATCH, BreakSeverity.MATERIAL, "1", "2")
    gw1.db.conn.commit()
    gw1.db.conn.close()
    
    gw2 = BrokerGateway(db_path=str(tmp_path / "test.db"))
    assert not gw2.reconciliation.can_accept_new_entries("PAPER_DEFAULT")

def test_material_break_resolution_rejects_blank_evidence_and_rationale():
    gw = BrokerGateway()
    gw.reset_simulation()
    gw.reconciliation._record_break("run1", "PAPER_DEFAULT", "TEST", BreakType.CASH_MISMATCH, BreakSeverity.MATERIAL, "1", "2")
    b_id = gw.reconciliation.get_open_breaks("PAPER_DEFAULT")[0]["break_id"]
    with pytest.raises(ValueError):
        gw.reconciliation.resolve_break(b_id, "", "rationale")
    with pytest.raises(ValueError):
        gw.reconciliation.resolve_break(b_id, "evidence", "")

def test_material_break_valid_resolution_is_durable_and_idempotent():
    gw = BrokerGateway()
    gw.reset_simulation()
    gw.reconciliation._record_break("run1", "PAPER_DEFAULT", "TEST", BreakType.CASH_MISMATCH, BreakSeverity.MATERIAL, "1", "2")
    b_id = gw.reconciliation.get_open_breaks("PAPER_DEFAULT")[0]["break_id"]
    gw.reconciliation.resolve_break(b_id, "evidence", "rationale")
    assert gw.reconciliation.can_accept_new_entries("PAPER_DEFAULT")
    gw.reconciliation.resolve_break(b_id, "evidence", "rationale")
    assert gw.reconciliation.can_accept_new_entries("PAPER_DEFAULT")

def test_fee_reconciliation_uses_decimal_safe_aggregation():
    gw = BrokerGateway()
    gw.reset_simulation()
    gw.db.conn.execute("INSERT INTO cash_ledger (cash_entry_id, account_id, currency, entry_type, amount, related_execution_id, occurred_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("f1", "PAPER_DEFAULT", "INR", "FEE", "-0.3", "fee_E1", time.time(), time.time()))
    gw.db.conn.execute("INSERT INTO executions_ledger (execution_id, order_id, qty, price, timestamp) VALUES (?, ?, ?, ?, ?)",
        ("E1", "O1", 10.0, 100.0, time.time()))
    snap = create_snapshot(ext_execs=[
        ExternalExecutionEvidence(provider="T", external_execution_id="E1", symbol="REL", side="BUY", quantity=Decimal("10"), price=Decimal("100"), fee=Decimal("0.3"), execution_timestamp=time.time(), received_timestamp=time.time(), source="T", raw_reference="R")
    ])
    gw.reconciliation.reconcile_account("PAPER_DEFAULT", snap)
    assert len([b for b in gw.reconciliation.get_open_breaks("PAPER_DEFAULT") if b["break_type"] == BreakType.FEE_MISMATCH.value]) == 0

def test_fee_reconciliation_excludes_unrelated_fee_entries():
    gw = BrokerGateway()
    gw.reset_simulation()
    gw.db.conn.execute("INSERT INTO cash_ledger (cash_entry_id, account_id, currency, entry_type, amount, related_execution_id, occurred_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("f1", "PAPER_DEFAULT", "INR", "FEE", "-1.0", "fee_E1", time.time(), time.time()))
    gw.db.conn.execute("INSERT INTO cash_ledger (cash_entry_id, account_id, currency, entry_type, amount, related_execution_id, occurred_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("f2", "PAPER_DEFAULT", "INR", "FEE", "-5.0", "fee_E2_UN", time.time(), time.time()))
    gw.db.conn.execute("INSERT INTO executions_ledger (execution_id, order_id, qty, price, timestamp) VALUES (?, ?, ?, ?, ?)",
        ("E1", "O1", 10.0, 100.0, time.time()))
    snap = create_snapshot(ext_execs=[
        ExternalExecutionEvidence(provider="T", external_execution_id="E1", symbol="REL", side="BUY", quantity=Decimal("10"), price=Decimal("100"), fee=Decimal("1.0"), execution_timestamp=time.time(), received_timestamp=time.time(), source="T", raw_reference="R")
    ])
    gw.reconciliation.reconcile_account("PAPER_DEFAULT", snap)
    assert len([b for b in gw.reconciliation.get_open_breaks("PAPER_DEFAULT") if b["break_type"] == BreakType.FEE_MISMATCH.value]) == 0

def test_external_filled_without_execution_evidence_creates_break_without_fabricating_fill():
    gw = BrokerGateway()
    gw.reset_simulation()
    gw.db.conn.execute("INSERT INTO order_ledger (order_id, request_id, strategy_id, symbol, side, qty, price, state, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("int_ord_1", "R1", "S1", "REL", "BUY", 10.0, 100.0, "OPEN", time.time(), time.time()))
    snap = create_snapshot(ext_orders=[
        ExternalOrderSnapshot(provider="T", external_order_id="ext_ord_1", internal_order_id="int_ord_1", symbol="REL", side="BUY", quantity=Decimal("10"), filled_quantity=Decimal("10"), pending_quantity=Decimal("0"), status="FILLED", timestamp=time.time(), source="A")
    ])
    gw.reconciliation.reconcile_account("PAPER_DEFAULT", snap)
    breaks = gw.reconciliation.get_open_breaks("PAPER_DEFAULT")
    assert len([b for b in breaks if b["break_type"] == BreakType.ORDER_STATUS_MISMATCH.value]) == 1
    
    cur = gw.db.conn.execute("SELECT state FROM order_ledger WHERE order_id='int_ord_1'")
    assert cur.fetchone()["state"] == "OPEN"
    
    cur = gw.db.conn.execute("SELECT count(*) as c FROM executions_ledger")
    assert cur.fetchone()["c"] == 0
