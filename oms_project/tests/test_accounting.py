import pytest
from decimal import Decimal
import time
from oms_project.gateway import BrokerGateway
from oms_project.schemas import OrderIntent, OrderSide, OrderState
from oms_project.accounting import CashEntryType

def test_account_initialization():
    gw = BrokerGateway()
    # 1. New account creates exactly one 100000 opening-balance entry
    cur = gw.db.conn.execute("SELECT amount FROM cash_ledger WHERE entry_type=?", (CashEntryType.OPENING_BALANCE,))
    rows = cur.fetchall()
    assert len(rows) == 1
    assert Decimal(rows[0]["amount"]) == Decimal("100000.00")
    
    # 3. Concurrent initialization creates one account only (idempotent)
    gw.accounting.initialize_account("PAPER_DEFAULT")
    cur = gw.db.conn.execute("SELECT amount FROM cash_ledger WHERE entry_type=?", (CashEntryType.OPENING_BALANCE,))
    rows = cur.fetchall()
    assert len(rows) == 1

def test_restart_preserves_account(tmp_path):
    db_file = str(tmp_path / "acc.db")
    gw = BrokerGateway(db_path=db_file)
    
    cur = gw.db.conn.execute("SELECT amount FROM cash_ledger")
    assert len(cur.fetchall()) == 1
    
    gw.db.conn.close()
    
    # 2. Restart does not create another opening balance
    gw2 = BrokerGateway(db_path=db_file)
    cur = gw2.db.conn.execute("SELECT amount FROM cash_ledger")
    assert len(cur.fetchall()) == 1

def test_buy_execution_accounting():
    gw = BrokerGateway()
    gw.reset_simulation()
    
    # 4. Buy execution updates cash, position, lot, reservation
    intent = OrderIntent(
        request_id="req_buy",
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=10.0,
        price=1200.0,
        signature="TEST"
    )
    res = gw.process_order_intent(intent)
    
    # Check cash ledger
    cur = gw.db.conn.execute("SELECT amount FROM cash_ledger WHERE entry_type=?", (CashEntryType.EXECUTION_BUY,))
    rows = cur.fetchall()
    assert len(rows) == 1
    assert Decimal(rows[0]["amount"]) == Decimal("-12000.0")
    
    # Check positions
    cur = gw.db.conn.execute("SELECT net_quantity FROM positions WHERE symbol='RELIANCE'")
    assert Decimal(cur.fetchone()["net_quantity"]) == Decimal("10.0")
    
    # Check lots
    cur = gw.db.conn.execute("SELECT open_quantity, entry_price FROM position_lots")
    lot = cur.fetchone()
    assert Decimal(lot["open_quantity"]) == Decimal("10.0")
    assert Decimal(lot["entry_price"]) == Decimal("1200.0")

def test_sell_execution_accounting():
    gw = BrokerGateway()
    gw.reset_simulation()
    
    intent = OrderIntent(
        request_id="req_buy",
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=10.0,
        price=1200.0,
        signature="TEST"
    )
    gw.process_order_intent(intent)
    
    gw.set_market_price("RELIANCE", 1220.0)
    # 5. Sell/close execution updates cash, realized P&L, lot
    intent_sell = OrderIntent(
        request_id="req_sell",
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side=OrderSide.SELL,
        qty=10.0,
        price=1220.0,
        signature="TEST"
    )
    gw.process_order_intent(intent_sell)
    
    cur = gw.db.conn.execute("SELECT amount FROM cash_ledger WHERE entry_type=?", (CashEntryType.EXECUTION_SELL,))
    rows = cur.fetchall()
    assert len(rows) == 1
    assert Decimal(rows[0]["amount"]) == Decimal("12200.0")
    
    cur = gw.db.conn.execute("SELECT realized_pnl, net_quantity FROM positions WHERE symbol='RELIANCE'")
    pos = cur.fetchone()
    assert Decimal(pos["realized_pnl"]) == Decimal("200.0")
    assert Decimal(pos["net_quantity"]) == Decimal("0.0")
    
    # Lot closed
    cur = gw.db.conn.execute("SELECT open_quantity, closed_at FROM position_lots")
    lot = cur.fetchone()
    assert Decimal(lot["open_quantity"]) == Decimal("0.0")
    assert lot["closed_at"] is not None

def test_partial_fill_accounting():
    gw = BrokerGateway()
    gw.reset_simulation()
    
    intent = OrderIntent(
        request_id="req_pf",
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=10.0,
        price=1200.0,
        signature="TEST"
    )
    res = gw.process_order_intent(intent, simulate_network_failure=True)
    
    # 6. Partial fill
    gw.process_execution_report(res.order_id, "exec1", 4.0, 1200.0)
    
    cur = gw.db.conn.execute("SELECT amount FROM cash_ledger WHERE entry_type=?", (CashEntryType.EXECUTION_BUY,))
    rows = cur.fetchall()
    assert len(rows) == 1
    assert Decimal(rows[0]["amount"]) == Decimal("-4800.0")
    
    cur = gw.db.conn.execute("SELECT net_quantity FROM positions")
    assert Decimal(cur.fetchone()["net_quantity"]) == Decimal("4.0")

def test_duplicate_execution():
    gw = BrokerGateway()
    gw.reset_simulation()
    
    intent = OrderIntent(
        request_id="req_pf",
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=10.0,
        price=1200.0,
        signature="TEST"
    )
    res = gw.process_order_intent(intent, simulate_network_failure=True)
    
    gw.process_execution_report(res.order_id, "exec_dup", 4.0, 1200.0)
    gw.process_execution_report(res.order_id, "exec_dup", 4.0, 1200.0)
    
    # 8. Duplicate leaves accounting unchanged
    cur = gw.db.conn.execute("SELECT amount FROM cash_ledger WHERE entry_type=?", (CashEntryType.EXECUTION_BUY,))
    assert len(cur.fetchall()) == 1
    
def test_long_mark_to_market():
    gw = BrokerGateway()
    gw.reset_simulation()
    
    intent = OrderIntent(
        request_id="req_buy",
        strategy_id="STRAT_001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        qty=10.0,
        price=1200.0,
        signature="TEST"
    )
    gw.process_order_intent(intent)
    
    # 9. Mark to market updates unrealized P&L
    gw.set_market_price("RELIANCE", 1250.0)
    
    cur = gw.db.conn.execute("SELECT unrealized_pnl, realized_pnl, market_value FROM positions WHERE symbol='RELIANCE'")
    pos = cur.fetchone()
    assert pos is not None
    assert Decimal(pos["unrealized_pnl"]) == Decimal("500.0")
    assert Decimal(pos["realized_pnl"]) == Decimal("0.0") # untouched
    assert Decimal(pos["market_value"]) == Decimal("12500.0")

def test_fifo_lots():
    gw = BrokerGateway()
    gw.reset_simulation()
    
    # Buy 10 at 1200
    intent1 = OrderIntent(request_id="r1", strategy_id="STRAT_001", symbol="RELIANCE", side=OrderSide.BUY, qty=10.0, price=1200.0, signature="T")
    gw.process_order_intent(intent1)
    
    gw.set_market_price("RELIANCE", 1220.0)
    
    # Buy 10 at 1220
    intent2 = OrderIntent(request_id="r2", strategy_id="STRAT_001", symbol="RELIANCE", side=OrderSide.BUY, qty=10.0, price=1220.0, signature="T")
    gw.process_order_intent(intent2)
    
    # Sell 15 at 1210
    # FIFO: closes 10 at 1200 (pnl = 10 * 10 = 100)
    # closes 5 at 1220 (pnl = -10 * 5 = -50)
    # Total RPL = 50
    gw.set_market_price("RELIANCE", 1210.0)
    intent3 = OrderIntent(request_id="r3", strategy_id="STRAT_001", symbol="RELIANCE", side=OrderSide.SELL, qty=15.0, price=1210.0, signature="T")
    gw.process_order_intent(intent3)
    
    cur = gw.db.conn.execute("SELECT realized_pnl, net_quantity FROM positions")
    pos = cur.fetchone()
    assert Decimal(pos["realized_pnl"]) == Decimal("50.0")
    assert Decimal(pos["net_quantity"]) == Decimal("5.0")
    
def test_position_reversal():
    gw = BrokerGateway()
    gw.reset_simulation()
    
    # Buy 10 at 1200
    intent1 = OrderIntent(request_id="r1", strategy_id="STRAT_001", symbol="RELIANCE", side=OrderSide.BUY, qty=10.0, price=1200.0, signature="T")
    gw.process_order_intent(intent1)
    
    gw.set_market_price("RELIANCE", 1220.0)
    
    # Sell 15 at 1220
    # Closes 10 at 1200 (pnl = 200), opens short 5 at 1220
    intent2 = OrderIntent(request_id="r2", strategy_id="STRAT_001", symbol="RELIANCE", side=OrderSide.SELL, qty=15.0, price=1220.0, signature="T")
    gw.process_order_intent(intent2)
    
    cur = gw.db.conn.execute("SELECT realized_pnl, net_quantity FROM positions")
    pos = cur.fetchone()
    assert Decimal(pos["realized_pnl"]) == Decimal("200.0")
    assert Decimal(pos["net_quantity"]) == Decimal("-5.0")
    
    cur = gw.db.conn.execute("SELECT open_quantity, side, entry_price FROM position_lots WHERE CAST(open_quantity AS REAL) > 0")
    lot = cur.fetchone()
    assert lot["side"] == "SELL"
    assert Decimal(lot["open_quantity"]) == Decimal("5.0")
    assert Decimal(lot["entry_price"]) == Decimal("1220.0")

def test_account_summary_report():
    gw = BrokerGateway()
    gw.reset_simulation()
    
    intent1 = OrderIntent(request_id="r1", strategy_id="STRAT_001", symbol="RELIANCE", side=OrderSide.BUY, qty=10.0, price=1200.0, signature="T")
    gw.process_order_intent(intent1)
    
    gw.set_market_price("RELIANCE", 1250.0)
    
    report = gw.accounting.get_account_summary("PAPER_DEFAULT")
    assert report["initial_capital"] == Decimal("100000.0")
    assert report["cash"] == Decimal("88000.0") # 100,000 - 12000
    assert report["unrealized_pnl"] == Decimal("500.0")
    assert report["equity"] == Decimal("100500.0") # cash + mv(12500)
