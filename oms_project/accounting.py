import sqlite3
import uuid
import time
import json
from decimal import Decimal
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from oms_project.schemas import OrderSide

class CashEntryType:
    OPENING_BALANCE = "OPENING_BALANCE"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    EXECUTION_BUY = "EXECUTION_BUY"
    EXECUTION_SELL = "EXECUTION_SELL"
    FEE = "FEE"
    FUNDING = "FUNDING"
    BORROW_COST = "BORROW_COST"
    ADJUSTMENT = "ADJUSTMENT"

class AccountingService:
    def __init__(self, db_conn: sqlite3.Connection):
        self.db = db_conn

    def initialize_account(self, account_id: str, account_reference: str = "PAPER_DEFAULT") -> Decimal:
        """Initialize paper account with 100,000 INR exactly once."""
        with self.db:
            cur = self.db.execute("SELECT initial_capital FROM paper_accounts WHERE account_id = ?", (account_id,))
            row = cur.fetchone()
            if row:
                return Decimal(row["initial_capital"])
            
            now = time.time()
            initial_cap = Decimal("100000.00")
            
            self.db.execute(
                "INSERT INTO paper_accounts (account_id, account_reference, account_type, base_currency, initial_capital, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (account_id, account_reference, "PAPER", "INR", str(initial_cap), "ACTIVE", now, now)
            )
            
            self.db.execute(
                "INSERT INTO cash_ledger (cash_entry_id, account_id, currency, entry_type, amount, idempotency_key, occurred_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), account_id, "INR", CashEntryType.OPENING_BALANCE, str(initial_cap), f"INIT_{account_id}", now, now)
            )
            
            return initial_cap

    def get_cash_balance(self, account_id: str) -> Decimal:
        cur = self.db.execute("SELECT amount FROM cash_ledger WHERE account_id = ?", (account_id,))
        total = Decimal("0.0")
        for row in cur:
            total += Decimal(row["amount"])
        return total

    def apply_execution(self, account_id: str, strategy_id: str, symbol: str, side: OrderSide, qty: Decimal, price: Decimal, execution_id: str, order_id: str, fee: Decimal = Decimal("0.0")):
        """Applies execution to cash ledger and lots."""
        now = time.time()
        
        try:
            with self.db:
                # 1. Cash Impact
                notional = qty * price
                if side == OrderSide.BUY:
                    cash_amount = -notional
                    entry_type = CashEntryType.EXECUTION_BUY
                else:
                    cash_amount = notional
                    entry_type = CashEntryType.EXECUTION_SELL
                
                # We enforce idempotency on related_execution_id and entry_type
                self.db.execute(
                    "INSERT INTO cash_ledger (cash_entry_id, account_id, currency, entry_type, amount, related_execution_id, related_order_id, occurred_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), account_id, "INR", entry_type, str(cash_amount), execution_id, order_id, now, now)
                )
                
                if fee > Decimal("0.0"):
                    self.db.execute(
                        "INSERT INTO cash_ledger (cash_entry_id, account_id, currency, entry_type, amount, related_execution_id, related_order_id, occurred_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (str(uuid.uuid4()), account_id, "INR", CashEntryType.FEE, str(-fee), f"fee_{execution_id}", order_id, now, now)
                    )
                
                # 2. Position Lots & P&L
                self._apply_lots_and_positions(account_id, strategy_id, symbol, side, qty, price, execution_id, fee, now)
        except sqlite3.IntegrityError:
            # Duplicate execution, ignore
            pass

    def _apply_lots_and_positions(self, account_id: str, strategy_id: str, symbol: str, side: OrderSide, executed_qty: Decimal, execution_price: Decimal, execution_id: str, fee: Decimal, now: float):
        # Determine current net quantity
        cur = self.db.execute("SELECT position_id, net_quantity, average_entry_price, realized_pnl, cumulative_fees FROM positions WHERE account_id=? AND strategy_id=? AND symbol=?", (account_id, strategy_id, symbol))
        pos_row = cur.fetchone()
        
        if pos_row:
            pos_id = pos_row["position_id"]
            net_qty = Decimal(pos_row["net_quantity"])
            realized_pnl = Decimal(pos_row["realized_pnl"])
            cum_fees = Decimal(pos_row["cumulative_fees"])
        else:
            pos_id = str(uuid.uuid4())
            net_qty = Decimal("0.0")
            realized_pnl = Decimal("0.0")
            cum_fees = Decimal("0.0")
            self.db.execute(
                "INSERT INTO positions (position_id, account_id, strategy_id, symbol, asset_class, currency, net_quantity, average_entry_price, realized_pnl, cumulative_fees, market_value, unrealized_pnl, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (pos_id, account_id, strategy_id, symbol, "EQUITY", "INR", "0.0", "0.0", "0.0", "0.0", "0.0", "0.0", now)
            )

        cum_fees += fee
        
        remaining_qty = executed_qty
        trade_pnl = Decimal("0.0")
        
        # Are we closing?
        is_closing = (net_qty > 0 and side == OrderSide.SELL) or (net_qty < 0 and side == OrderSide.BUY)
        
        if is_closing:
            # Fetch open lots opposite to our side
            opp_side = "BUY" if side == OrderSide.SELL else "SELL"
            lots_cur = self.db.execute("SELECT lot_id, open_quantity, entry_price FROM position_lots WHERE account_id=? AND strategy_id=? AND symbol=? AND side=? AND CAST(open_quantity AS REAL) > 0 ORDER BY opened_at ASC", (account_id, strategy_id, symbol, opp_side))
            
            for lot in lots_cur.fetchall():
                if remaining_qty <= Decimal("0.0"):
                    break
                    
                lot_id = lot["lot_id"]
                lot_open_qty = Decimal(lot["open_quantity"])
                lot_entry = Decimal(lot["entry_price"])
                
                close_qty = min(lot_open_qty, remaining_qty)
                
                # Calculate PnL
                if side == OrderSide.SELL: # Closing a long
                    trade_pnl += close_qty * (execution_price - lot_entry)
                else: # Closing a short
                    trade_pnl += close_qty * (lot_entry - execution_price)
                    
                new_lot_open = lot_open_qty - close_qty
                closed_at = now if new_lot_open == Decimal("0.0") else None
                
                self.db.execute("UPDATE position_lots SET open_quantity=?, closed_at=? WHERE lot_id=?", (str(new_lot_open), closed_at, lot_id))
                
                remaining_qty -= close_qty

        realized_pnl += trade_pnl
        
        # If there's remaining qty, it opens new lots
        if remaining_qty > Decimal("0.0"):
            self.db.execute(
                "INSERT INTO position_lots (lot_id, account_id, strategy_id, symbol, side, original_quantity, open_quantity, entry_price, opening_execution_id, opened_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), account_id, strategy_id, symbol, side.value, str(remaining_qty), str(remaining_qty), str(execution_price), execution_id, now)
            )

        # Recalculate position
        lots_cur = self.db.execute("SELECT open_quantity, entry_price, side FROM position_lots WHERE account_id=? AND strategy_id=? AND symbol=? AND CAST(open_quantity AS REAL) > 0", (account_id, strategy_id, symbol))
        
        total_open = Decimal("0.0")
        total_cost = Decimal("0.0")
        new_side = None
        for lot in lots_cur.fetchall():
            l_qty = Decimal(lot["open_quantity"])
            total_open += l_qty
            total_cost += l_qty * Decimal(lot["entry_price"])
            new_side = lot["side"]
            
        avg_entry = total_cost / total_open if total_open > 0 else Decimal("0.0")
        final_net = total_open if new_side == "BUY" else -total_open
        if total_open == Decimal("0.0"):
            final_net = Decimal("0.0")
            
        self.db.execute(
            "UPDATE positions SET net_quantity=?, average_entry_price=?, realized_pnl=?, cumulative_fees=?, updated_at=? WHERE position_id=?",
            (str(final_net), str(avg_entry), str(realized_pnl), str(cum_fees), now, pos_id)
        )

    def mark_to_market(self, account_id: str, symbol: str, mark_price: Decimal, timestamp: float):
        with self.db:
            cur = self.db.execute("SELECT position_id, net_quantity, average_entry_price FROM positions WHERE account_id=? AND symbol=?", (account_id, symbol))
            for row in cur.fetchall():
                pos_id = row["position_id"]
                net_qty = Decimal(row["net_quantity"])
                avg_entry = Decimal(row["average_entry_price"])
                
                market_val = net_qty * mark_price
                if net_qty > 0:
                    unrealized_pnl = net_qty * (mark_price - avg_entry)
                elif net_qty < 0:
                    unrealized_pnl = abs(net_qty) * (avg_entry - mark_price)
                else:
                    unrealized_pnl = Decimal("0.0")
                    
                self.db.execute(
                    "UPDATE positions SET last_mark_price=?, mark_timestamp=?, market_value=?, unrealized_pnl=?, updated_at=? WHERE position_id=?",
                    (str(mark_price), timestamp, str(market_val), str(unrealized_pnl), time.time(), pos_id)
                )

    def get_account_summary(self, account_id: str) -> Dict[str, Any]:
        cash = self.get_cash_balance(account_id)
        
        cur = self.db.execute("SELECT initial_capital FROM paper_accounts WHERE account_id=?", (account_id,))
        row = cur.fetchone()
        initial = Decimal(row["initial_capital"]) if row else Decimal("0.0")
        
        cur = self.db.execute("SELECT SUM(CAST(market_value AS REAL)) as total_mv, SUM(CAST(unrealized_pnl AS REAL)) as total_upl, SUM(CAST(realized_pnl AS REAL)) as total_rpl, SUM(CAST(cumulative_fees AS REAL)) as total_fees FROM positions WHERE account_id=?", (account_id,))
        pos_aggs = cur.fetchone()
        
        total_mv = Decimal(str(pos_aggs["total_mv"] or "0.0"))
        total_upl = Decimal(str(pos_aggs["total_upl"] or "0.0"))
        total_rpl = Decimal(str(pos_aggs["total_rpl"] or "0.0"))
        total_fees = Decimal(str(pos_aggs["total_fees"] or "0.0"))
        
        equity = cash + total_mv
        
        # calculate active reservations for this account
        cur = self.db.execute("SELECT SUM(reserved_cash) as res_cash FROM capital_reservations WHERE account_id=? AND status='ACTIVE'", (account_id,))
        res_row = cur.fetchone()
        active_res = Decimal(str(res_row["res_cash"] or "0.0"))
        
        available = equity - active_res
        
        return {
            "account_id": account_id,
            "initial_capital": initial,
            "cash": cash,
            "equity": equity,
            "active_reserved_capital": active_res,
            "available_capital": available,
            "realized_pnl": total_rpl,
            "unrealized_pnl": total_upl,
            "fees": total_fees
        }
