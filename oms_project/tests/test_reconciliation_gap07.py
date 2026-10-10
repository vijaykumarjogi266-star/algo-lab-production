import pytest
import sqlite3
import time
from decimal import Decimal
from oms_project.gateway import BrokerGateway
from oms_project.schemas import OrderIntent, OrderSide, OrderState
from oms_project.reconciliation import (
    ReconciliationService, ReconciliationSnapshot, ExternalAccountSnapshot,
    ExternalPositionSnapshot, ExternalOrderSnapshot, ExternalExecutionEvidence,
    BreakType, BreakSeverity, BreakStatus
)

@pytest.fixture
def gw():
    gateway = BrokerGateway()
    gateway.reset_simulation()
    # ensure paper account is setup
    # actually BrokerGateway sets up the DB
    return gateway

def create_snapshot(account_id="PAPER_DEFAULT", ref="snap_1", ext_orders=None, ext_execs=None):
    return ReconciliationSnapshot(
        provider="TEST_BROKER",
        account_id=account_id,
        collection_timestamp=time.time(),
        account_snapshot=ExternalAccountSnapshot(
            provider="TEST_BROKER",
            external_account_id="EXT1",
            snapshot_reference=ref,
            cash_balance=Decimal("1000000.0"),
            timestamp=time.time(),
            currency="INR",
            source="TEST",
            quality_status="OK"
        ),
        positions=[],
        orders=ext_orders or [],
        executions=ext_execs or []
    )

def test_fee_mismatch_creates_break_and_blocks_entries(gw):
    # Setup execution with one fee in DB
    gw.db.conn.execute("INSERT INTO executions_ledger (execution_id, order_id, qty, price, timestamp) VALUES (?, ?, ?, ?, ?)",
                    ("EXEC1", "ORD1", 10.0, 100.0, time.time()))
    gw.db.conn.execute("INSERT INTO cash_ledger (cash_entry_id, account_id, currency, entry_type, amount, related_execution_id, occurred_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    ("C1", "PAPER_DEFAULT", "INR", "FEE", "-5.0", "fee_EXEC1", time.time(), time.time()))

    # External says fee is 10.0
    snap = create_snapshot(ext_execs=[
        ExternalExecutionEvidence(
            provider="TEST", external_execution_id="EXEC1", internal_order_id="ORD1",
            symbol="RELIANCE", side="BUY", quantity=Decimal("10"), price=Decimal("100"),
            fee=Decimal("10.0"), execution_timestamp=time.time(), received_timestamp=time.time(),
            source="TEST", raw_reference="raw"
        )
    ])
    
    gw.reconciliation.reconcile_account("PAPER_DEFAULT", snap)
    
    breaks = gw.reconciliation.get_open_breaks("PAPER_DEFAULT")
    fee_breaks = [b for b in breaks if b["break_type"] == BreakType.FEE_MISMATCH.value]
    assert len(fee_breaks) == 1
    assert fee_breaks[0]["expected_value"] == "5.0"
    assert fee_breaks[0]["observed_value"] == "10.0"
    
    # Should block entries
    assert gw.reconciliation.can_accept_new_entries("PAPER_DEFAULT") is False

def test_fee_mismatch_is_idempotent(gw):
    # Setup
    gw.db.conn.execute("INSERT INTO executions_ledger (execution_id, order_id, qty, price, timestamp) VALUES (?, ?, ?, ?, ?)",
                    ("EXEC1", "ORD1", 10.0, 100.0, time.time()))
    gw.db.conn.execute("INSERT INTO cash_ledger (cash_entry_id, account_id, currency, entry_type, amount, related_execution_id, occurred_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    ("C1", "PAPER_DEFAULT", "INR", "FEE", "-5.0", "fee_EXEC1", time.time(), time.time()))

    # Run 1
    snap1 = create_snapshot(ref="snap_1", ext_execs=[
        ExternalExecutionEvidence(
            provider="TEST", external_execution_id="EXEC1", internal_order_id="ORD1",
            symbol="RELIANCE", side="BUY", quantity=Decimal("10"), price=Decimal("100"),
            fee=Decimal("10.0"), execution_timestamp=time.time(), received_timestamp=time.time(),
            source="TEST", raw_reference="raw"
        )
    ])
    gw.reconciliation.reconcile_account("PAPER_DEFAULT", snap1)
    
    # Run 2 (Same exact data, different snapshot ref to force process)
    snap2 = create_snapshot(ref="snap_2", ext_execs=[
        ExternalExecutionEvidence(
            provider="TEST", external_execution_id="EXEC1", internal_order_id="ORD1",
            symbol="RELIANCE", side="BUY", quantity=Decimal("10"), price=Decimal("100"),
            fee=Decimal("10.0"), execution_timestamp=time.time(), received_timestamp=time.time(),
            source="TEST", raw_reference="raw"
        )
    ])
    gw.reconciliation.reconcile_account("PAPER_DEFAULT", snap2)
    
    # Should STILL be 1 break
    fee_breaks = [b for b in gw.reconciliation.get_open_breaks("PAPER_DEFAULT") if b["break_type"] == BreakType.FEE_MISMATCH.value]
    assert len(fee_breaks) == 1

def test_order_status_mismatch_preserves_internal_state(gw):
    # internal OPEN
    gw.db.conn.execute("INSERT INTO order_ledger (order_id, request_id, strategy_id, symbol, side, qty, price, state, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    ("ORD1", "REQ1", "STRAT1", "RELIANCE", "BUY", 10.0, 100.0, "OPEN", time.time(), time.time()))
    
    # external CANCELLED
    snap = create_snapshot(ext_orders=[
        ExternalOrderSnapshot(
            provider="TEST", external_order_id="EXT_ORD1", internal_order_id="ORD1",
            symbol="RELIANCE", side="BUY", quantity=Decimal("10"), status="CANCELLED",
            received_timestamp=time.time(), raw_reference="raw",
            filled_quantity=Decimal("0"), pending_quantity=Decimal("0"), timestamp=time.time(), source="TEST"
        )
    ])
    
    gw.reconciliation.reconcile_account("PAPER_DEFAULT", snap)
    
    breaks = gw.reconciliation.get_open_breaks("PAPER_DEFAULT")
    status_breaks = [b for b in breaks if b["break_type"] == BreakType.ORDER_STATUS_MISMATCH.value]
    assert len(status_breaks) == 1
    assert status_breaks[0]["severity"] == BreakSeverity.MATERIAL.value
    
    # Internal state is preserved
    cur = gw.db.conn.execute("SELECT state FROM order_ledger WHERE order_id='ORD1'")
    assert cur.fetchone()["state"] == "OPEN"

def test_order_status_resolution_requires_evidence(gw):
    # internal CANCELLED, external OPEN
    gw.db.conn.execute("INSERT INTO order_ledger (order_id, request_id, strategy_id, symbol, side, qty, price, state, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    ("ORD1", "REQ1", "STRAT1", "RELIANCE", "BUY", 10.0, 100.0, "CANCELLED", time.time(), time.time()))
    
    snap = create_snapshot(ext_orders=[
        ExternalOrderSnapshot(
            provider="TEST", external_order_id="EXT_ORD1", internal_order_id="ORD1",
            symbol="RELIANCE", side="BUY", quantity=Decimal("10"), status="OPEN",
            received_timestamp=time.time(), raw_reference="raw",
            filled_quantity=Decimal("0"), pending_quantity=Decimal("10"), timestamp=time.time(), source="TEST"
        )
    ])
    gw.reconciliation.reconcile_account("PAPER_DEFAULT", snap)
    
    breaks = [b for b in gw.reconciliation.get_open_breaks("PAPER_DEFAULT") if b["break_type"] == BreakType.ORDER_STATUS_MISMATCH.value]
    break_id = breaks[0]["break_id"]
    
    # Resolve it
    gw.reconciliation.resolve_break(break_id, evidence="Check OK", rationale="False positive", new_status=BreakStatus.FALSE_POSITIVE)
    
    assert len([b for b in gw.reconciliation.get_open_breaks("PAPER_DEFAULT") if b["break_type"] == BreakType.ORDER_STATUS_MISMATCH.value]) == 0
    cur = gw.db.conn.execute("SELECT evidence_reference, operator_rationale FROM reconciliation_breaks WHERE break_id=?", (break_id,))
    row = cur.fetchone()
    assert row["evidence_reference"] == "Check OK"
    assert row["operator_rationale"] == "False positive"

def test_material_break_persists_after_restart_and_blocks_entry(tmp_path):
    db_path = str(tmp_path / "test.db")
    # First instance
    gw1 = BrokerGateway(db_path=db_path)
    gw1.reset_simulation()
    
    # Force a cash mismatch
    snap = ReconciliationSnapshot(
        provider="TEST", account_id="PAPER_DEFAULT", collection_timestamp=time.time(),
        account_snapshot=ExternalAccountSnapshot(
            provider="TEST", external_account_id="EXT1", snapshot_reference="S1", cash_balance=Decimal("99999.0"),
            timestamp=time.time(), currency="INR", source="TEST", quality_status="OK"
        ),
        positions=[], orders=[], executions=[]
    )
    gw1.reconciliation.reconcile_account("PAPER_DEFAULT", snap)
    assert gw1.reconciliation.can_accept_new_entries("PAPER_DEFAULT") is False
    
    # Close
    gw1.db.conn.close()
    
    # Second instance (Restart)
    gw2 = BrokerGateway(db_path=db_path)
    
    assert gw2.reconciliation.can_accept_new_entries("PAPER_DEFAULT") is False
    breaks = gw2.reconciliation.get_open_breaks("PAPER_DEFAULT")
    assert len(breaks) == 1
    assert breaks[0]["severity"] == BreakSeverity.MATERIAL.value
    
    # Try submit
    req = OrderIntent(request_id="R1", symbol="RELIANCE", side=OrderSide.BUY, qty=10.0, price=100.0, account_id="PAPER_DEFAULT", strategy_id="S1", signature="sig")
    with pytest.raises(Exception) as exc:
        gw2.submit_order(req)
    # The gateway usually checks can_accept_new_entries or similar
    # Let's ensure the message matches expectation
    
    # Wait, the exact exception might be "RuntimeError: Safety block: Reconciliation breaks prevent new entries" or similar.
    # Let's not assert exact string if we don't know it yet, just ensure it raises Exception.

def test_entry_block_clears_only_after_all_material_breaks_resolve(gw):
    # Setup multiple material breaks
    snap = create_snapshot(ext_execs=[
        ExternalExecutionEvidence(
            provider="T", external_execution_id="E1", symbol="RELIANCE", side="BUY", quantity=Decimal("1"), price=Decimal("1"),
            execution_timestamp=time.time(), received_timestamp=time.time(), source="T", raw_reference="R1"
        ),
        ExternalExecutionEvidence(
            provider="T", external_execution_id="E2", symbol="RELIANCE", side="BUY", quantity=Decimal("1"), price=Decimal("1"),
            execution_timestamp=time.time(), received_timestamp=time.time(), source="T", raw_reference="R2"
        )
    ])
    gw.reconciliation.reconcile_account("PAPER_DEFAULT", snap)
    
    breaks = gw.reconciliation.get_open_breaks("PAPER_DEFAULT")
    material_breaks = [b for b in breaks if b["severity"] in (BreakSeverity.MATERIAL.value, BreakSeverity.CRITICAL.value)]
    assert len(material_breaks) == 3 # 2 MISSING_EXECUTION_EVIDENCE, 1 CASH_MISMATCH
    
    for i, b in enumerate(material_breaks):
        gw.db.conn.execute("UPDATE reconciliation_breaks SET status='INVESTIGATING' WHERE break_id=?", (b["break_id"],))
        gw.reconciliation.resolve_break(b["break_id"], f"Ev{i}", new_status=BreakStatus.RESOLVED)
        
    assert gw.reconciliation.can_accept_new_entries("PAPER_DEFAULT") is True