import pytest
from decimal import Decimal
import time
from oms_project.gateway import BrokerGateway
from oms_project.schemas import OrderIntent, OrderSide
from oms_project.reconciliation import (
    ReconciliationSnapshot, ExternalAccountSnapshot, ExternalPositionSnapshot, 
    ExternalOrderSnapshot, ExternalExecutionEvidence, BreakType, BreakSeverity
)

def test_position_mismatch():
    gw = BrokerGateway()
    gw.reset_simulation()
    
    # Internal state: empty
    
    snap = ReconciliationSnapshot(
        provider="TEST_BROKER",
        account_id="PAPER_DEFAULT",
        collection_timestamp=time.time(),
        account_snapshot=ExternalAccountSnapshot(
            provider="TEST_BROKER",
            external_account_id="ext_act_1",
            snapshot_reference="snap_1",
            timestamp=time.time(),
            currency="INR",
            source="API",
            quality_status="OK"
        ),
        positions=[
            ExternalPositionSnapshot(
                provider="TEST_BROKER",
                account_id="PAPER_DEFAULT",
                symbol="RELIANCE",
                asset_class="EQ",
                currency="INR",
                quantity=Decimal("10.0"),
                timestamp=time.time(),
                source="API"
            )
        ],
        orders=[],
        executions=[]
    )
    
    run_id = gw.reconciliation.reconcile_account("PAPER_DEFAULT", snap)
    breaks = gw.reconciliation.get_open_breaks("PAPER_DEFAULT")
    
    assert len(breaks) == 1
    brk = breaks[0]
    assert brk["break_type"] == BreakType.POSITION_MISMATCH.value
    assert brk["severity"] == BreakSeverity.MATERIAL.value
    assert Decimal(brk["expected_value"]) == Decimal("0.0") # Internal
    assert Decimal(brk["observed_value"]) == Decimal("10.0") # External
    
    # Entry blocked
    assert not gw.reconciliation.can_accept_new_entries("PAPER_DEFAULT")
    
    intent = OrderIntent(request_id="req1", strategy_id="STRAT", symbol="REL", side=OrderSide.BUY, qty=10.0, price=100.0, signature="X")
    res = gw.process_order_intent(intent)
    assert res.status.value == "REJECTED"
    assert "RECONCILIATION_HOLD" in res.message


def test_cash_mismatch():
    gw = BrokerGateway()
    gw.reset_simulation()
    
    # Internal state: 100000.00 cash
    
    snap = ReconciliationSnapshot(
        provider="TEST_BROKER",
        account_id="PAPER_DEFAULT",
        collection_timestamp=time.time(),
        account_snapshot=ExternalAccountSnapshot(
            provider="TEST_BROKER",
            external_account_id="ext_act_1",
            snapshot_reference="snap_2",
            timestamp=time.time(),
            currency="INR",
            cash_balance=Decimal("95000.0"),
            source="API",
            quality_status="OK"
        ),
        positions=[],
        orders=[],
        executions=[]
    )
    
    run_id = gw.reconciliation.reconcile_account("PAPER_DEFAULT", snap)
    breaks = gw.reconciliation.get_open_breaks("PAPER_DEFAULT")
    
    assert len(breaks) == 1
    assert breaks[0]["break_type"] == BreakType.CASH_MISMATCH.value
    
    # Check that cash ledger was NOT mutated
    report = gw.accounting.get_account_summary("PAPER_DEFAULT")
    assert report["cash"] == Decimal("100000.00")

def test_missing_execution_evidence():
    gw = BrokerGateway()
    gw.reset_simulation()
    
    snap = ReconciliationSnapshot(
        provider="TEST_BROKER",
        account_id="PAPER_DEFAULT",
        collection_timestamp=time.time(),
        account_snapshot=ExternalAccountSnapshot(
            provider="TEST_BROKER",
            external_account_id="ext_act_1",
            snapshot_reference="snap_3",
            timestamp=time.time(),
            currency="INR",
            source="API",
            quality_status="OK"
        ),
        positions=[],
        orders=[],
        executions=[
            ExternalExecutionEvidence(
                provider="TEST_BROKER",
                external_execution_id="ext_exec_999",
                symbol="RELIANCE",
                side="BUY",
                quantity=Decimal("10.0"),
                price=Decimal("1200.0"),
                execution_timestamp=time.time(),
                received_timestamp=time.time(),
                source="API",
                raw_reference="RAW"
            )
        ]
    )
    
    run_id = gw.reconciliation.reconcile_account("PAPER_DEFAULT", snap)
    breaks = gw.reconciliation.get_open_breaks("PAPER_DEFAULT")
    assert any(b["break_type"] == BreakType.MISSING_EXECUTION_EVIDENCE.value for b in breaks)
    
def test_missing_internal_order():
    gw = BrokerGateway()
    gw.reset_simulation()
    
    snap = ReconciliationSnapshot(
        provider="TEST_BROKER",
        account_id="PAPER_DEFAULT",
        collection_timestamp=time.time(),
        account_snapshot=ExternalAccountSnapshot(
            provider="TEST_BROKER",
            external_account_id="ext_act_1",
            snapshot_reference="snap_4",
            timestamp=time.time(),
            currency="INR",
            source="API",
            quality_status="OK"
        ),
        positions=[],
        orders=[
            ExternalOrderSnapshot(
                provider="TEST_BROKER",
                external_order_id="ext_ord_1",
                symbol="RELIANCE",
                side="BUY",
                quantity=Decimal("10.0"),
                filled_quantity=Decimal("0.0"),
                pending_quantity=Decimal("10.0"),
                status="OPEN",
                timestamp=time.time(),
                source="API"
            )
        ],
        executions=[]
    )
    
    gw.reconciliation.reconcile_account("PAPER_DEFAULT", snap)
    breaks = gw.reconciliation.get_open_breaks("PAPER_DEFAULT")
    assert any(b["break_type"] == BreakType.MISSING_INTERNAL_ORDER.value for b in breaks)

def test_idempotent_reconciliation():
    gw = BrokerGateway()
    gw.reset_simulation()
    
    snap = ReconciliationSnapshot(
        provider="TEST_BROKER",
        account_id="PAPER_DEFAULT",
        collection_timestamp=time.time(),
        account_snapshot=ExternalAccountSnapshot(
            provider="TEST_BROKER",
            external_account_id="ext_act_1",
            snapshot_reference="snap_idempotent",
            timestamp=time.time(),
            currency="INR",
            cash_balance=Decimal("95000.0"),
            source="API",
            quality_status="OK"
        ),
        positions=[],
        orders=[],
        executions=[]
    )
    
    run1 = gw.reconciliation.reconcile_account("PAPER_DEFAULT", snap)
    run2 = gw.reconciliation.reconcile_account("PAPER_DEFAULT", snap)
    
    assert run1 == run2
    
    cur = gw.db.conn.execute("SELECT count(*) as c FROM reconciliation_breaks WHERE account_id=?", ("PAPER_DEFAULT",))
    assert cur.fetchone()["c"] == 1

def test_evidence_based_resolution():
    gw = BrokerGateway()
    gw.reset_simulation()
    
    snap = ReconciliationSnapshot(
        provider="TEST_BROKER",
        account_id="PAPER_DEFAULT",
        collection_timestamp=time.time(),
        account_snapshot=ExternalAccountSnapshot(
            provider="TEST_BROKER",
            external_account_id="ext_act_1",
            snapshot_reference="snap_resolve",
            timestamp=time.time(),
            currency="INR",
            cash_balance=Decimal("95000.0"),
            source="API",
            quality_status="OK"
        ),
        positions=[],
        orders=[],
        executions=[]
    )
    
    gw.reconciliation.reconcile_account("PAPER_DEFAULT", snap)
    breaks = gw.reconciliation.get_open_breaks("PAPER_DEFAULT")
    assert len(breaks) == 1
    
    assert not gw.reconciliation.can_accept_new_entries("PAPER_DEFAULT")
    
    gw.reconciliation.resolve_break(breaks[0]["break_id"], "MANUAL_WIRE_TRANSFER", "Confirmed with broker")
    
    breaks_after = gw.reconciliation.get_open_breaks("PAPER_DEFAULT")
    assert len(breaks_after) == 0
    assert gw.reconciliation.can_accept_new_entries("PAPER_DEFAULT")
