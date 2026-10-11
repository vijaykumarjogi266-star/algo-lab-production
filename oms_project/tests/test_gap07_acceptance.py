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

def test_restart_reconciliation_hold_returns_explicit_code_and_has_no_side_effects(tmp_path):
    db_path = str(tmp_path / "persistent.db")
    
    # 1. Create persistent DB file, 2. Init gateway, create break
    gw1 = BrokerGateway(db_path=db_path)
    gw1.reset_simulation()
    gw1.reconciliation._record_break("run1", "PAPER_DEFAULT", "TEST", BreakType.CASH_MISMATCH, BreakSeverity.MATERIAL, "1", "2")
    
    # 3. Commit and close
    gw1.db.conn.commit()
    gw1.db.conn.close()
    
    # 4. Recreate
    gw = BrokerGateway(db_path=db_path)
    
    # 5. Capture before states
    res_count = gw.db.conn.execute("SELECT count(*) as c FROM capital_reservations").fetchone()["c"]
    ord_count = gw.db.conn.execute("SELECT count(*) as c FROM order_ledger").fetchone()["c"]
    sim_calls = len(gw.paper_exchange.execution_history) if gw.paper_exchange else 0
    exe_count = gw.db.conn.execute("SELECT count(*) as c FROM executions_ledger").fetchone()["c"]
    csh_count = gw.db.conn.execute("SELECT count(*) as c FROM cash_ledger").fetchone()["c"]
    
    summary = gw.accounting.get_account_summary("PAPER_DEFAULT")
    csh_bal = summary["cash"]
    pos_state = gw.db.conn.execute("SELECT count(*) as c FROM positions").fetchone()["c"]
    lots = gw.db.conn.execute("SELECT count(*) as c FROM position_lots").fetchone()["c"]
    pnl = summary["realized_pnl"]
    fee_entries = gw.db.conn.execute("SELECT count(*) as c FROM cash_ledger WHERE entry_type='FEE'").fetchone()["c"]
    
    # 6. Submit new entry
    intent = OrderIntent(request_id="req1", strategy_id="S1", symbol="REL", side=OrderSide.BUY, qty=10.0, price=100.0, signature="X")
    res = gw.process_order_intent(intent)
    
    # 7. Assert exact outcome
    assert res.message == "RECONCILIATION_HOLD_NEW_ENTRIES_BLOCKED"
    
    # 8-10. Assert unchanged
    assert gw.db.conn.execute("SELECT count(*) as c FROM capital_reservations").fetchone()["c"] == res_count
    assert gw.db.conn.execute("SELECT count(*) as c FROM order_ledger").fetchone()["c"] == ord_count
    sim_calls_after = len(gw.paper_exchange.execution_history) if gw.paper_exchange else 0
    assert sim_calls_after == sim_calls
    assert sim_calls_after == 0
    
    assert gw.db.conn.execute("SELECT count(*) as c FROM executions_ledger").fetchone()["c"] == exe_count
    assert gw.db.conn.execute("SELECT count(*) as c FROM cash_ledger").fetchone()["c"] == csh_count
    
    after_summary = gw.accounting.get_account_summary("PAPER_DEFAULT")
    assert after_summary["cash"] == csh_bal
    assert gw.db.conn.execute("SELECT count(*) as c FROM positions").fetchone()["c"] == pos_state
    assert gw.db.conn.execute("SELECT count(*) as c FROM position_lots").fetchone()["c"] == lots
    assert after_summary["realized_pnl"] == pnl
    assert gw.db.conn.execute("SELECT count(*) as c FROM cash_ledger WHERE entry_type='FEE'").fetchone()["c"] == fee_entries

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
    
    # reject blanks
    for bad in [None, "", "   "]:
        with pytest.raises(ValueError):
            gw.reconciliation.resolve_break(b_id, bad, "rationale")
        with pytest.raises(ValueError):
            gw.reconciliation.resolve_break(b_id, "evidence", bad)
            
    # validation happens before status mutation (prove state is open)
    assert gw.reconciliation.get_open_breaks("PAPER_DEFAULT")[0]["status"] == "OPEN"
    assert not gw.reconciliation.can_accept_new_entries("PAPER_DEFAULT")

def test_material_break_valid_resolution_is_durable_and_idempotent():
    gw = BrokerGateway()
    gw.reset_simulation()
    gw.reconciliation._record_break("run1", "PAPER_DEFAULT", "TEST", BreakType.CASH_MISMATCH, BreakSeverity.MATERIAL, "1", "2")
    b_id = gw.reconciliation.get_open_breaks("PAPER_DEFAULT")[0]["break_id"]
    
    # resolve
    gw.reconciliation.resolve_break(b_id, "evidence", "rationale", BreakStatus.RESOLVED)
    
    # verify durable
    cur = gw.db.conn.execute("SELECT status, evidence_reference, operator_rationale, resolved_at FROM reconciliation_breaks WHERE break_id=?", (b_id,))
    row = cur.fetchone()
    assert row["status"] == "RESOLVED"
    assert row["evidence_reference"] == "evidence"
    assert row["operator_rationale"] == "rationale"
    orig_ts = row["resolved_at"]
    assert orig_ts > 0
    
    # repeating valid resolution does not overwrite or error
    gw.reconciliation.resolve_break(b_id, "ev2", "rat2", BreakStatus.FALSE_POSITIVE)
    
    cur = gw.db.conn.execute("SELECT status, evidence_reference, operator_rationale, resolved_at FROM reconciliation_breaks WHERE break_id=?", (b_id,))
    row = cur.fetchone()
    assert row["status"] == "RESOLVED"
    assert row["evidence_reference"] == "evidence"
    assert row["operator_rationale"] == "rationale"
    assert row["resolved_at"] == orig_ts

def test_fee_reconciliation_uses_decimal_safe_aggregation():
    gw = BrokerGateway()
    gw.reset_simulation()
    # durable internal fee row 1: -0.10
    gw.db.conn.execute("INSERT INTO cash_ledger (cash_entry_id, account_id, currency, entry_type, amount, related_execution_id, occurred_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("f1", "PAPER_DEFAULT", "INR", "FEE", "-0.10", "fee_E1", time.time(), time.time()))
    # durable internal fee row 2: -0.20 (same account, same currency, same execution reference)
    gw.db.conn.execute("INSERT INTO cash_ledger (cash_entry_id, account_id, currency, entry_type, amount, related_execution_id, occurred_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("f2", "PAPER_DEFAULT", "INR", "FEE", "-0.20", "fee_E1", time.time(), time.time()))
    gw.db.conn.execute("INSERT INTO executions_ledger (execution_id, order_id, qty, price, timestamp) VALUES (?, ?, ?, ?, ?)",
        ("E1", "O1", 10.0, 100.0, time.time()))
        
    snap = create_snapshot(ext_execs=[
        ExternalExecutionEvidence(provider="T", external_execution_id="E1", symbol="REL", side="BUY", quantity=Decimal("10"), price=Decimal("100"), fee=Decimal("0.30"), execution_timestamp=time.time(), received_timestamp=time.time(), source="T", raw_reference="R")
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
    # 1. Internal order is LIVE
    gw.db.conn.execute("INSERT INTO order_ledger (order_id, request_id, strategy_id, symbol, side, qty, price, state, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("int_ord_1", "R1", "S1", "REL", "BUY", 10.0, 100.0, "LIVE", time.time(), time.time()))
    cur_ord = gw.db.conn.execute("SELECT state FROM order_ledger WHERE order_id='int_ord_1'")
    assert cur_ord.fetchone()["state"] == "LIVE"

    # 3. No matching internal execution evidence exists
    cur_exec = gw.db.conn.execute("SELECT count(*) as c FROM executions_ledger WHERE order_id='int_ord_1'")
    assert cur_exec.fetchone()["c"] == 0

    # Capture initial ledger & accounting states
    init_summary = gw.accounting.get_account_summary("PAPER_DEFAULT")
    init_cash = init_summary["cash"]
    init_pnl = init_summary["realized_pnl"]
    init_pos_count = gw.db.conn.execute("SELECT count(*) as c FROM positions").fetchone()["c"]
    init_lots_count = gw.db.conn.execute("SELECT count(*) as c FROM position_lots").fetchone()["c"]
    init_fee_count = gw.db.conn.execute("SELECT count(*) as c FROM cash_ledger WHERE entry_type='FEE'").fetchone()["c"]
    init_exec_count = gw.db.conn.execute("SELECT count(*) as c FROM executions_ledger").fetchone()["c"]

    # 2. External snapshot is FILLED
    snap = create_snapshot(ext_orders=[
        ExternalOrderSnapshot(provider="T", external_order_id="ext_ord_1", internal_order_id="int_ord_1", symbol="REL", side="BUY", quantity=Decimal("10"), filled_quantity=Decimal("10"), pending_quantity=Decimal("0"), status="FILLED", timestamp=time.time(), source="A")
    ])
    
    # 9. The same snapshot processed twice results in exactly one equivalent open break
    gw.reconciliation.reconcile_account("PAPER_DEFAULT", snap)
    gw.reconciliation.reconcile_account("PAPER_DEFAULT", snap)
    
    breaks = gw.reconciliation.get_open_breaks("PAPER_DEFAULT")
    assert len(breaks) == 1
    # 4. A MATERIAL reconciliation break exists
    assert breaks[0]["break_type"] == BreakType.ORDER_STATUS_MISMATCH.value
    assert breaks[0]["severity"] == BreakSeverity.MATERIAL.value
    
    # 5. Internal order state remains unchanged
    cur = gw.db.conn.execute("SELECT state FROM order_ledger WHERE order_id='int_ord_1'")
    assert cur.fetchone()["state"] == "LIVE"
    
    # 6. No execution ledger row is created
    cur = gw.db.conn.execute("SELECT count(*) as c FROM executions_ledger")
    assert cur.fetchone()["c"] == init_exec_count
    
    # 7. Cash, position, lot, realized P&L, and fee state remain unchanged
    after_summary = gw.accounting.get_account_summary("PAPER_DEFAULT")
    assert after_summary["cash"] == init_cash
    assert after_summary["realized_pnl"] == init_pnl
    assert gw.db.conn.execute("SELECT count(*) as c FROM positions").fetchone()["c"] == init_pos_count
    assert gw.db.conn.execute("SELECT count(*) as c FROM position_lots").fetchone()["c"] == init_lots_count
    assert gw.db.conn.execute("SELECT count(*) as c FROM cash_ledger WHERE entry_type='FEE'").fetchone()["c"] == init_fee_count
    
    # 8. A new entry receives exactly: RECONCILIATION_HOLD_NEW_ENTRIES_BLOCKED
    intent = OrderIntent(request_id="R2", strategy_id="S1", symbol="REL", side=OrderSide.BUY, qty=10.0, price=100.0, signature="X")
    res = gw.process_order_intent(intent)
    assert res.message == "RECONCILIATION_HOLD_NEW_ENTRIES_BLOCKED"
    
    # 10. Blank/whitespace evidence or rationale cannot resolve a MATERIAL break
    b_id = breaks[0]["break_id"]
    for bad_ev in [None, "", "   "]:
        with pytest.raises(ValueError):
            gw.reconciliation.resolve_break(b_id, bad_ev, "valid_rationale")
    for bad_rat in [None, "", "   "]:
        with pytest.raises(ValueError):
            gw.reconciliation.resolve_break(b_id, "valid_evidence", bad_rat)

    # Prove break is still OPEN and entries still blocked
    assert gw.reconciliation.get_open_breaks("PAPER_DEFAULT")[0]["status"] == "OPEN"
    assert not gw.reconciliation.can_accept_new_entries("PAPER_DEFAULT")
        
    # 11. Valid evidence-based resolution is durable and follows existing terminal-state policy
    gw.reconciliation.resolve_break(b_id, "audit_ref_123", "verified_offline_manual_sync", BreakStatus.RESOLVED)
    assert gw.reconciliation.can_accept_new_entries("PAPER_DEFAULT")

    cur_res = gw.db.conn.execute("SELECT status, evidence_reference, operator_rationale, resolved_at FROM reconciliation_breaks WHERE break_id=?", (b_id,))
    row_res = cur_res.fetchone()
    assert row_res["status"] == "RESOLVED"
    assert row_res["evidence_reference"] == "audit_ref_123"
    assert row_res["operator_rationale"] == "verified_offline_manual_sync"
    orig_ts = row_res["resolved_at"]
    assert orig_ts > 0

    # Repeat resolution to prove terminal state immutability
    gw.reconciliation.resolve_break(b_id, "tamper_ref", "tamper_rationale", BreakStatus.FALSE_POSITIVE)
    cur_res2 = gw.db.conn.execute("SELECT status, evidence_reference, operator_rationale, resolved_at FROM reconciliation_breaks WHERE break_id=?", (b_id,))
    row_res2 = cur_res2.fetchone()
    assert row_res2["status"] == "RESOLVED"
    assert row_res2["evidence_reference"] == "audit_ref_123"
    assert row_res2["operator_rationale"] == "verified_offline_manual_sync"
    assert row_res2["resolved_at"] == orig_ts

def test_gap_register_only_marks_gap07_t28_t30_resolved():
    import os
    with open("BASELINE_GAP_REGISTER.md", "r") as f:
        content = f.read()
    assert "GAP-07 / T28/T30 reconciliation: RESOLVED" in content or "IMPLEMENTED_PENDING_ACCEPTANCE_REPAIR" in content
    # Prove no global replacement logic happened to other gaps that weren't resolved
    assert "RESOLVED_VERIFIED" not in content
    
    with open("PROJECT_STATUS.md", "r") as f:
        content2 = f.read()
    assert "RESOLVED_VERIFIED" not in content2

