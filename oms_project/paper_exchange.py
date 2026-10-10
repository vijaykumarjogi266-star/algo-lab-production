"""
OMS Project - Paper Exchange Implementation
Simulates external exchange matching engine & account custody.
"""

import time
from typing import Dict, Any, Optional


class PaperExchange:
    """
    Paper Exchange Service.
    Holds exchange cash balances, security positions (long and short),
    and processes orders submitted with Vault ephemeral signing tokens.
    """

    def __init__(self, initial_cash: float = 100000.0):
        self.initial_cash = initial_cash
        self.cash_balance = initial_cash
        self.positions: Dict[str, float] = {}
        self.execution_history = []

    def _record_fill(self, broker_order_id, strategy_id, symbol, side, qty, price, signing_token):
        fill_id = f"FILL_{len(self.execution_history) + 1:06d}"
        exec_record = {
            "fill_id": fill_id,
            "broker_order_id": broker_order_id,
            "strategy_id": strategy_id,
            "symbol": symbol,
            "side": side.upper(),
            "qty": qty,
            "price": price,
            "timestamp": time.time(),
            "signing_token": signing_token,
            "cash_balance": self.cash_balance,
            "position": self.positions.get(symbol, 0.0),
        }
        self.execution_history.append(exec_record)
        return exec_record

    def execute_order(
        self,
        strategy_id: str,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        signing_token: str,
        broker_order_id: str = "",
        simulate_partial_qty: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Executes trade on exchange if valid short-lived signing token is supplied."""
        if not signing_token.startswith("v1.signing."):
            return {"success": False, "reason": "REJECTED_INVALID_SIGNING_TOKEN"}

        actual_qty = simulate_partial_qty if simulate_partial_qty is not None else qty
        cost = actual_qty * price
        
        if side.upper() == "BUY":
            if self.cash_balance < cost:
                return {"success": False, "reason": "REJECTED_EXCHANGE_INSUFFICIENT_FUNDS"}
            self.cash_balance -= cost
            self.positions[symbol] = self.positions.get(symbol, 0.0) + actual_qty
        elif side.upper() == "SELL":
            self.cash_balance += cost
            self.positions[symbol] = self.positions.get(symbol, 0.0) - actual_qty
        else:
            return {"success": False, "reason": "REJECTED_INVALID_SIDE"}

        exec_record = self._record_fill(broker_order_id, strategy_id, symbol, side, actual_qty, price, signing_token)
        return {"success": True, "fill": exec_record}

    def query_order(self, broker_order_id: str) -> Optional[Dict[str, Any]]:
        for record in self.execution_history:
            if record.get("broker_order_id") == broker_order_id:
                return record
        return None

    def get_total_assets(self, market_prices: Dict[str, float]) -> float:
        """Calculates total exchange equity: Cash Balance + Sum(Positions * Market Price)."""
        total = self.cash_balance
        for sym, pos in self.positions.items():
            price = market_prices.get(sym, 0.0)
            total += pos * price
        return total
