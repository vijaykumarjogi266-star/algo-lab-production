import re

with open('oms_project/gateway.py', 'r') as f:
    content = f.read()

# Replace `simulate_network_failure` handling in process_order_intent
old_network_failure = """        if simulate_network_failure:
            self.db.transition_state(order_id, OrderState.SUBMISSION_UNKNOWN, "Network Timeout During Order Submission")
            res = OrderResult(
                request_id=intent.request_id,
                order_id=order_id,
                strategy_id=intent.strategy_id,
                symbol=intent.symbol,
                side=intent.side.value,
                qty=intent.qty,
                price=exec_price,
                status=OrderState.SUBMISSION_UNKNOWN,
                message="Order submission status unknown due to network timeout. Mandatory reconciliation required.",
                reserved_value=reserved_val,
                execution_tx=signing_token,
            )
            self.idempotency_cache[intent.request_id] = res.model_dump()
            return res"""

new_network_failure = """        if simulate_network_failure:
            self.db.transition_state(order_id, OrderState.SUBMISSION_UNKNOWN, "Network Timeout During Order Submission", reserved_value=reserved_val)
            import uuid
            resolution_id = str(uuid.uuid4())
            self.db.record_uncertainty(resolution_id, order_id, intent.strategy_id, "SUBMISSION_TIMEOUT", OrderState.SUBMISSION_UNKNOWN.value, intent.request_id)
            res = OrderResult(
                request_id=intent.request_id,
                order_id=order_id,
                strategy_id=intent.strategy_id,
                symbol=intent.symbol,
                side=intent.side.value,
                qty=intent.qty,
                price=exec_price,
                status=OrderState.SUBMISSION_UNKNOWN,
                message="SUBMISSION_UNCERTAIN: Order submission status unknown due to network timeout. Mandatory reconciliation required.",
                reserved_value=reserved_val,
                execution_tx=signing_token,
            )
            self.idempotency_cache[intent.request_id] = res.model_dump()
            return res"""

content = content.replace(old_network_failure, new_network_failure)

# Add a mock cancel_order method
cancel_method = """    def cancel_order(self, order_id: str, simulate_network_failure: bool = False) -> OrderResult:
        order = self.db.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
            
        current_state = OrderState(order["state"])
        intent = OrderIntent(
            request_id=order["request_id"],
            strategy_id=order["strategy_id"],
            symbol=order["symbol"],
            side=OrderSide(order["side"]),
            qty=order["qty"],
            price=order["price"],
            timestamp=time.time(),
            expiry=time.time() + 30.0,
            signature="CANCEL"
        )
        
        if current_state not in [OrderState.LIVE, OrderState.PARTIALLY_FILLED, OrderState.ACKNOWLEDGED]:
            raise ValueError(f"Cannot cancel order in state {current_state}")
            
        self.db.transition_state(order_id, OrderState.CANCEL_PENDING, "Cancel Pending")
        
        if simulate_network_failure:
            self.db.transition_state(order_id, OrderState.CANCEL_UNKNOWN, "Cancel network timeout")
            import uuid
            self.db.record_uncertainty(str(uuid.uuid4()), order_id, order["strategy_id"], "CANCELLATION_TIMEOUT", OrderState.CANCEL_UNKNOWN.value, order["request_id"])
            return OrderResult(
                request_id=order["request_id"],
                order_id=order_id,
                strategy_id=order["strategy_id"],
                symbol=order["symbol"],
                side=order["side"],
                qty=order["qty"],
                price=order["price"],
                status=OrderState.CANCEL_UNKNOWN,
                message="CANCELLATION_UNCERTAIN",
                reserved_value=order["reserved_value"]
            )
            
        # Simulate successful cancel
        self.db.transition_state(order_id, OrderState.CANCELLED, "Cancelled successfully", reserved_value=0.0)
        
        # Release residual reservation
        if order["side"] == OrderSide.BUY.value and order["reserved_value"] > 0:
            self.strategy_reserved[order["strategy_id"]] -= order["reserved_value"]
            self.strategy_balances[order["strategy_id"]] += order["reserved_value"]
            
        return OrderResult(
            request_id=order["request_id"],
            order_id=order_id,
            strategy_id=order["strategy_id"],
            symbol=order["symbol"],
            side=order["side"],
            qty=order["qty"],
            price=order["price"],
            status=OrderState.CANCELLED,
            message="Cancelled successfully",
            reserved_value=0.0
        )
"""

content = content.replace("    def resolve_unknown_orders(self):", cancel_method + "\n    def resolve_unknown_orders(self):")

# Add a method to resolve uncertainty externally
resolve_method = """    def resolve_uncertain_order(self, order_id: str, evidence: dict):
        order = self.db.get_order(order_id)
        if not order:
            return
            
        state = OrderState(order["state"])
        strat_id = order["strategy_id"]
        sym = order["symbol"]
        side = OrderSide(order["side"])
        reserved_val = order["reserved_value"]
        
        if evidence["status"] == "REJECTED":
            self.db.transition_state(order_id, OrderState.REJECTED, "Resolved via evidence")
            if side == OrderSide.BUY and reserved_val > 0:
                self.strategy_reserved[strat_id] -= reserved_val
                self.strategy_balances[strat_id] += reserved_val
            self.db.resolve_uncertainty(order_id, "SUBMISSION_TIMEOUT", evidence.get("ref", "manual"))
        elif evidence["status"] == "CANCELLED":
            self.db.transition_state(order_id, OrderState.CANCELLED, "Resolved via evidence", reserved_value=0.0)
            if side == OrderSide.BUY and reserved_val > 0:
                self.strategy_reserved[strat_id] -= reserved_val
                self.strategy_balances[strat_id] += reserved_val
            self.db.resolve_uncertainty(order_id, "CANCELLATION_TIMEOUT", evidence.get("ref", "manual"))
        elif evidence["status"] == "LIVE":
            self.db.transition_state(order_id, OrderState.LIVE, "Resolved as live")
            self.db.resolve_uncertainty(order_id, "CANCELLATION_TIMEOUT", evidence.get("ref", "manual"))
"""

content = content.replace("    def resolve_unknown_orders(self):", resolve_method + "\n    def resolve_unknown_orders(self):")

with open('oms_project/gateway.py', 'w') as f:
    f.write(content)
