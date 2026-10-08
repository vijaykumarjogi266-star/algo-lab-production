"""
OMS Project - Broker Gateway Implementation ("The Heart")
Centralized Gateway exercising Authority over OrderIntents.
"""

import time
import json
import hmac
import hashlib
import sqlite3
from typing import Dict, Any, Optional, List, Callable
from oms_project.schemas import OrderIntent, OrderResult, OrderState, OrderSide
from oms_project.database import OrderLedgerDB
from oms_project.paper_exchange import PaperExchange
from oms_project.reservation_service import CapitalReservationService, ReservationOutcome


class VaultSecretsManager:
    """Simulates Vault Secrets Manager issuing short-lived signing tokens."""
    def get_exchange_signing_token(self, strategy_id: str) -> str:
        # Generate 5-minute ephemeral signing token with zero withdrawal privileges
        timestamp = int(time.time() // 300)
        secret_key = f"vault_ephemeral_{strategy_id}_{timestamp}".encode()
        token = hmac.new(secret_key, b"TRADE_EXECUTION_ONLY", hashlib.sha256).hexdigest()
        return f"v1.signing.{token[:16]}"


class BrokerGateway:
    def __init__(
        self,
        db_path: str = ":memory:",
        max_gross_exposure: float = 1000000.0,
        price_collar_pct: float = 2.0,
        max_market_data_staleness_ms: float = 500.0,
        paper_exchange: Optional[PaperExchange] = None,
        simulation_mode: bool = False,
        slippage_bps: float = 0.0,
        latency_ms: float = 0.0,
    ):
        self.db = OrderLedgerDB(db_path=db_path)
        self.reservation_service = CapitalReservationService(self.db.conn)
        self.vault = VaultSecretsManager()
        self.paper_exchange = paper_exchange or PaperExchange(initial_cash=100000.0)
        self.max_gross_exposure = max_gross_exposure
        self.price_collar_pct = price_collar_pct
        self.max_market_data_staleness_ms = max_market_data_staleness_ms
        self.simulation_mode = simulation_mode
        self.slippage_bps = slippage_bps
        self.latency_ms = latency_ms

        # State stores (In-Memory Redis equivalents for fast testing and isolation)
        self.idempotency_cache: Dict[str, Dict[str, Any]] = {}
        self.strategy_balances: Dict[str, float] = {
            "STRAT_001": 100000.0,
            "STRAT_002": 50000.0,
            "STRAT_MEAN_REV_001": 100000.0,
        }
        self.strategy_reserved: Dict[str, float] = {
            "STRAT_001": 0.0,
            "STRAT_002": 0.0,
            "STRAT_MEAN_REV_001": 0.0,
        }
        self.strategy_positions: Dict[str, Dict[str, float]] = {
            "STRAT_001": {},
            "STRAT_002": {},
            "STRAT_MEAN_REV_001": {},
        }
        self.strategy_entry_prices: Dict[str, Dict[str, float]] = {
            "STRAT_001": {},
            "STRAT_002": {},
            "STRAT_MEAN_REV_001": {},
        }
        self.pod_enabled: Dict[str, bool] = {
            "STRAT_001": True,
            "STRAT_002": True,
            "STRAT_MEAN_REV_001": True,
        }
        self.portfolio_exposure: float = 0.0

        # Control plane guards
        self.kill_switch_active: bool = False
        self.db_reachable: bool = True

        # Reference market prices for price collar verification
        self.reference_market_prices: Dict[str, float] = {
            "RELIANCE": 1200.0,
            "NIFTY": 24000.0,
            "INFY": 1500.0,
        }
        self.reference_market_timestamps: Dict[str, float] = {
            "RELIANCE": time.time(),
            "NIFTY": time.time(),
            "INFY": time.time(),
        }

        # Subscribers listening for position & order transition updates
        self.position_listeners: List[Callable[[str, str, float, float], None]] = []
        self.order_listeners: List[Callable[[Dict[str, Any]], None]] = []

        # Attempt to reconstruct state if the db exists
        try:
            self.reconstruct_state_from_ledger()
        except Exception as e:
            print(f"Ledger Reconstruction Failed: {e}")

    def set_market_price(self, symbol: str, price: float, timestamp: Optional[float] = None):
        self.reference_market_prices[symbol] = price
        self.reference_market_timestamps[symbol] = timestamp if timestamp is not None else time.time()

    def set_kill_switch(self, active: bool):
        self.kill_switch_active = active

    def set_pod_enabled(self, strategy_id: str, enabled: bool):
        self.pod_enabled[strategy_id] = enabled

    def set_db_reachable(self, reachable: bool):
        self.db_reachable = reachable

    def enable_simulation_mode(self, slippage_bps: float = 0.0, latency_ms: float = 0.0):
        self.simulation_mode = True
        self.slippage_bps = slippage_bps
        self.latency_ms = latency_ms

    def disable_simulation_mode(self):
        self.simulation_mode = False
        self.slippage_bps = 0.0
        self.latency_ms = 0.0

    def subscribe_position_updates(self, callback: Callable[[str, str, float, float], None]):
        """Subscribe callback to receive broadcast position updates."""
        self.position_listeners.append(callback)

    def subscribe_order_transitions(self, callback: Callable[[Dict[str, Any]], None]):
        """Subscribe callback to receive broadcast order state transitions."""
        self.order_listeners.append(callback)

    def _notify_order_transition(self, order_id: str, strategy_id: str, symbol: str, side: str, qty: float, price: float, state: str, message: str):
        event = {
            "timestamp": time.time(),
            "event": "ORDER_TRANSITION",
            "order_id": order_id,
            "strategy_id": strategy_id,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "state": state,
            "message": message,
        }
        for listener in self.order_listeners:
            try:
                listener(event)
            except Exception:
                pass

    def reconstruct_state_from_ledger(self):
        """Reconstructs balances, positions, and reservations from durable ledger after crash/restart."""
        # Reset current state to defaults based on initial cash
        initial_cash = self.paper_exchange.initial_cash if hasattr(self.paper_exchange, 'initial_cash') else 100000.0
        self.strategy_balances = {s: initial_cash for s in ["STRAT_001", "STRAT_002", "STRAT_MEAN_REV_001"]}
        self.strategy_reserved = {s: 0.0 for s in ["STRAT_001", "STRAT_002", "STRAT_MEAN_REV_001"]}
        self.strategy_positions = {s: {} for s in ["STRAT_001", "STRAT_002", "STRAT_MEAN_REV_001"]}
        self.strategy_entry_prices = {s: {} for s in ["STRAT_001", "STRAT_002", "STRAT_MEAN_REV_001"]}
        self.portfolio_exposure = 0.0

        # Query all orders
        cur = self.db.conn.execute("SELECT * FROM order_ledger ORDER BY created_at ASC")
        for row in cur.fetchall():
            row_dict = dict(row)
            s_id = row_dict["strategy_id"]
            sym = row_dict["symbol"]
            state = OrderState(row_dict["state"])
            side = OrderSide(row_dict["side"])
            exec_qty = row_dict.get("executed_qty", 0.0) or 0.0
            exec_price = row_dict.get("execution_price", row_dict["price"]) or row_dict["price"]
            reserved_val = row_dict.get("reserved_value", 0.0) or 0.0
            
            if s_id not in self.strategy_balances:
                self.strategy_balances[s_id] = initial_cash
                self.strategy_reserved[s_id] = 0.0
                self.strategy_positions[s_id] = {}
                self.strategy_entry_prices[s_id] = {}

            # Reconstruct positions and balances for FILLED orders
            if state == OrderState.FILLED and exec_qty > 0:
                strat_pos = self.strategy_positions[s_id]
                strat_entry = self.strategy_entry_prices[s_id]
                curr_pos = strat_pos.get(sym, 0.0)
                curr_avg = strat_entry.get(sym, exec_price)
                
                if side == OrderSide.BUY:
                    self.strategy_balances[s_id] -= (exec_qty * exec_price)
                    new_qty = curr_pos + exec_qty
                    if new_qty > 0:
                        strat_entry[sym] = ((curr_pos * curr_avg) + (exec_qty * exec_price)) / new_qty
                    strat_pos[sym] = new_qty
                elif side == OrderSide.SELL:
                    self.strategy_balances[s_id] += (exec_qty * exec_price)
                    new_qty = curr_pos - exec_qty
                    strat_pos[sym] = new_qty
                    if new_qty == 0:
                        strat_entry[sym] = 0.0
                
                self.portfolio_exposure += (exec_qty * exec_price)

            # Reconstruct reservations for in-flight orders
            if state in [OrderState.RISK_RESERVED, OrderState.SUBMITTED, OrderState.SUBMISSION_UNKNOWN, OrderState.ACKNOWLEDGED]:
                if side == OrderSide.BUY and reserved_val > 0:
                    self.strategy_balances[s_id] -= reserved_val
                    self.strategy_reserved[s_id] += reserved_val
                    self.portfolio_exposure += reserved_val
                    
            # Reconstruct idempotency cache
            req_id = row_dict["request_id"]
            if req_id not in self.idempotency_cache:
                self.idempotency_cache[req_id] = OrderResult(
                    request_id=req_id,
                    order_id=row_dict["order_id"],
                    strategy_id=s_id,
                    symbol=sym,
                    side=side.value,
                    qty=exec_qty if state == OrderState.FILLED else row_dict["qty"],
                    price=exec_price if state == OrderState.FILLED else row_dict["price"],
                    status=state,
                    message="Reconstructed from Ledger",
                    reserved_value=reserved_val,
                    execution_tx=row_dict.get("execution_id", "")
                ).model_dump()

    # 1. Idempotency Check
    def check_idempotency(self, request_id: str) -> Optional[OrderResult]:
        if request_id in self.idempotency_cache:
            cached = self.idempotency_cache[request_id]
            res = OrderResult(**cached)
            # Return original result for idempotent retry instead of rejecting
            return res
        return None

    # 2. Fail-Closed Guard Middleware
    def verify_fail_closed_guard(self, symbol: str, strategy_id: str = "", signature: str = "") -> Optional[str]:
        # Guard A: KILL_SWITCH
        if self.kill_switch_active:
            return "REJECTED_KILL_SWITCH_ACTIVE"

        # Guard B: Pod Disabled Guard
        if strategy_id and not self.pod_enabled.get(strategy_id, True):
            if signature != "SYMMETRY_FORCE_FLATTEN":
                return f"REJECTED_POD_DISABLED ({strategy_id} is currently disabled)"

        # Guard C: Database Reachability
        if not self.db_reachable:
            return "REJECTED_DATABASE_UNREACHABLE"

        # Guard D: Market Data Staleness > 500ms (Bypassed in simulation mode)
        if not self.simulation_mode:
            now = time.time()
            last_mkt_time = self.reference_market_timestamps.get(symbol, 0)
            staleness_ms = (now - last_mkt_time) * 1000.0
            if staleness_ms > self.max_market_data_staleness_ms:
                return f"REJECTED_STALE_MARKET_DATA ({staleness_ms:.1f}ms > {self.max_market_data_staleness_ms}ms)"

        return None

    # 3. Atomic Risk Reservation & Price Collar
    def reserve_risk_atomically(
        self, strategy_id: str, symbol: str, side: OrderSide, qty: float, price: float, request_id: str
    ) -> tuple[bool, str, float, float]:
        # Portfolio Correlation / Concentration Penalty Check
        effective_qty = qty
        concentration_msg = ""
        other_pods_in_same_direction = [
            p_id for p_id, pos in self.strategy_positions.items()
            if p_id != strategy_id and (
                (side == OrderSide.BUY and pos.get(symbol, 0.0) > 0) or
                (side == OrderSide.SELL and pos.get(symbol, 0.0) < 0)
            )
        ]

        if other_pods_in_same_direction:
            effective_qty = qty * 0.5
            concentration_msg = f" (CONCENTRATION_PENALTY_APPLIED: qty reduced from {qty} to {effective_qty})"

        order_value = effective_qty * price

        # Price Collar Check
        ref_price = self.reference_market_prices.get(symbol, price)
        dev_pct = abs(price - ref_price) / ref_price * 100.0
        if dev_pct > self.price_collar_pct:
            return False, f"REJECTED_PRICE_COLLAR_DEVIATION ({dev_pct:.2f}% > {self.price_collar_pct}%)", 0.0, qty

        if (self.portfolio_exposure + order_value) > self.max_gross_exposure:
            return False, f"REJECTED_MAX_GROSS_EXPOSURE_EXCEEDED", 0.0, qty

        if side == OrderSide.BUY:
            # Delegate to durable atomic reservation service
            res = self.reservation_service.reserve_for_order(
                account_id=strategy_id,
                idempotency_key=request_id,
                qty=effective_qty,
                price=price,
                strategy_id=strategy_id,
                get_available_capital=lambda acc: self.strategy_balances.get(acc, 0.0) + self.strategy_reserved.get(acc, 0.0)
            )
            
            if res["outcome"] == ReservationOutcome.REJECTED:
                return False, f"REJECTED_INSUFFICIENT_STRATEGY_BALANCE (Avail: {res.get('available_capital_before', 0.0):.2f}, Required: {order_value:.2f})", 0.0, qty
            elif res["outcome"] in (ReservationOutcome.CONFLICT, ReservationOutcome.RETRYABLE_FAILURE):
                return False, f"REJECTED_RESERVATION_FAILED ({res.get('reason_code')})", 0.0, qty

            # If successful, we align in-memory balances for fast reads
            self.strategy_balances[strategy_id] -= order_value
            self.strategy_reserved[strategy_id] = self.strategy_reserved.get(strategy_id, 0.0) + order_value

        self.portfolio_exposure += order_value

        return True, f"RISK_RESERVED_SUCCESS{concentration_msg}", order_value, effective_qty


    def reset_simulation(self, initial_cash: float = 100000.0):
        """Resets balances, positions, paper exchange state, and DB ledger for clean simulation run."""
        self.db.reset_ledger()
        self.paper_exchange = PaperExchange(initial_cash=initial_cash)
        self.idempotency_cache.clear()
        self.strategy_balances = {
            "STRAT_001": initial_cash,
            "STRAT_002": initial_cash,
            "STRAT_MEAN_REV_001": initial_cash,
        }
        self.strategy_reserved = {
            "STRAT_001": 0.0,
            "STRAT_002": 0.0,
            "STRAT_MEAN_REV_001": 0.0,
        }
        self.strategy_positions = {
            "STRAT_001": {},
            "STRAT_002": {},
            "STRAT_MEAN_REV_001": {},
        }
        self.strategy_entry_prices = {
            "STRAT_001": {},
            "STRAT_002": {},
            "STRAT_MEAN_REV_001": {},
        }
        self.portfolio_exposure = 0.0
        self.kill_switch_active = False

    def force_flatten_positions(self, strategy_id: Optional[str] = None) -> List[OrderResult]:
        """Symmetry Shutdown: Force-flattens all open positions across strategy pods."""
        
        # 1. Block entry by disabling pod
        if strategy_id:
            self.set_pod_enabled(strategy_id, False)
        else:
            for s_id in self.pod_enabled.keys():
                self.set_pod_enabled(s_id, False)
                
        # 2. Resolve unknown orders to capture late fills / missed positions
        self.resolve_unknown_orders()
        
        # 3. Cancel working entry orders (Not fully implemented yet, but placeholders)
        
        flatten_results = []
        target_strategies = [strategy_id] if strategy_id else list(self.strategy_positions.keys())

        for s_id in target_strategies:
            positions = dict(self.strategy_positions.get(s_id, {}))
            for symbol, qty in positions.items():
                if qty != 0:
                    side = OrderSide.SELL if qty > 0 else OrderSide.BUY
                    flat_qty = abs(qty)
                    price = self.reference_market_prices.get(symbol, 1000.0)
                    intent = OrderIntent(
                        request_id=f"FLATTEN_{s_id}_{symbol}_{int(time.time()*1000)}",
                        strategy_id=s_id,
                        symbol=symbol,
                        side=side,
                        qty=flat_qty,
                        price=price,
                        timestamp=time.time(),
                        expiry=time.time() + 30.0,
                        signature="SYMMETRY_FORCE_FLATTEN",
                    )
                    res = self.process_order_intent(intent)
                    flatten_results.append(res)

        return flatten_results

    def execute_external_broker_api_call(self, endpoint: str, payload: Dict[str, Any]):
        """Simulates external exchange API invocation. Blocks calls when SIMULATION_MODE=True."""
        if self.simulation_mode:
            raise PermissionError("SIMULATION_LOCK_ACTIVE: Direct outbound calls to external broker API are physically blocked in Simulation Mode!")
        return {"status": "SUCCESS", "endpoint": endpoint}

    # Primary Order Execution Pipeline
    def process_order_intent(self, intent: OrderIntent, simulate_network_failure: bool = False) -> OrderResult:
        # Step 1: Idempotency Check (before any DB write or risk reservation)
        cached_result = self.check_idempotency(intent.request_id)
        if cached_result:
            return cached_result

        # Calculate slippage-adjusted execution price in simulation mode
        exec_price = intent.price
        if self.simulation_mode and self.slippage_bps > 0:
            if intent.side == OrderSide.BUY:
                exec_price = intent.price * (1.0 + (self.slippage_bps / 10000.0))
            elif intent.side == OrderSide.SELL:
                exec_price = intent.price * (1.0 - (self.slippage_bps / 10000.0))

        # Latency Simulation
        if self.simulation_mode and self.latency_ms > 0:
            time.sleep(self.latency_ms / 1000.0)

        # Step 2: Fail-Closed Guard Check
        guard_rejection = self.verify_fail_closed_guard(intent.symbol, strategy_id=intent.strategy_id, signature=intent.signature)
        if guard_rejection:
            res = OrderResult(
                request_id=intent.request_id,
                order_id=f"REJ_{intent.request_id[:8]}",
                strategy_id=intent.strategy_id,
                symbol=intent.symbol,
                side=intent.side.value,
                qty=intent.qty,
                price=exec_price,
                status=OrderState.REJECTED,
                message=guard_rejection,
            )
            self.idempotency_cache[intent.request_id] = res.model_dump()
            self._notify_order_transition(res.order_id, intent.strategy_id, intent.symbol, intent.side.value, intent.qty, exec_price, OrderState.REJECTED.value, guard_rejection)
            return res

        # Record in State Machine: RECEIVED -> VALIDATED
        try:
            order_id = self.db.record_received_order(intent)
        except sqlite3.IntegrityError:
            # Race condition: another thread is processing this idempotency key.
            # Spin-wait until it's in the cache.
            for _ in range(50):
                cached_result = self.check_idempotency(intent.request_id)
                if cached_result:
                    return cached_result
                time.sleep(0.05)
            # If still not found, return a RETRYABLE_FAILURE
            return OrderResult(
                request_id=intent.request_id,
                order_id="",
                strategy_id=intent.strategy_id,
                symbol=intent.symbol,
                side=intent.side.value,
                qty=intent.qty,
                price=exec_price,
                status=OrderState.REJECTED,
                message="IDEMPOTENCY_RACE_TIMEOUT",
            )

        self._notify_order_transition(order_id, intent.strategy_id, intent.symbol, intent.side.value, intent.qty, exec_price, OrderState.RECEIVED.value, "Order Received")
        self.db.transition_state(order_id, OrderState.VALIDATED, "OrderIntent Validated")
        self._notify_order_transition(order_id, intent.strategy_id, intent.symbol, intent.side.value, intent.qty, exec_price, OrderState.VALIDATED.value, "Validated")

        # Step 3: Atomic Risk Reservation & Concentration Check
        ok_risk, risk_msg, reserved_val, effective_qty = self.reserve_risk_atomically(
            intent.strategy_id, intent.symbol, intent.side, intent.qty, exec_price, intent.request_id
        )
        if not ok_risk:
            self.db.transition_state(order_id, OrderState.REJECTED, risk_msg)
            res = OrderResult(
                request_id=intent.request_id,
                order_id=order_id,
                strategy_id=intent.strategy_id,
                symbol=intent.symbol,
                side=intent.side.value,
                qty=intent.qty,
                price=exec_price,
                status=OrderState.REJECTED,
                message=risk_msg,
            )
            self.idempotency_cache[intent.request_id] = res.model_dump()
            return res

        self.db.transition_state(order_id, OrderState.RISK_RESERVED, "Risk Reserved", reserved_value=reserved_val)

        # Step 4: Vault Signing Token Request & Submission to Paper Exchange
        signing_token = self.vault.get_exchange_signing_token(intent.strategy_id)

        if simulate_network_failure:
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
            return res

        self.db.transition_state(order_id, OrderState.SUBMITTED, f"Submitted to Exchange via token {signing_token[:8]}")
        self.db.transition_state(order_id, OrderState.ACKNOWLEDGED, "Exchange Acknowledged Order")

        # Forward order to Paper Exchange
        exch_res = self.paper_exchange.execute_order(
            strategy_id=intent.strategy_id,
            symbol=intent.symbol,
            side=intent.side.value,
            qty=effective_qty,
            price=exec_price,
            signing_token=signing_token,
            broker_order_id=order_id,
        )

        if not exch_res.get("success"):
            reason = exch_res.get("reason", "EXCHANGE_REJECTED")
            self.db.transition_state(order_id, OrderState.REJECTED, reason)
            res = OrderResult(
                request_id=intent.request_id,
                order_id=order_id,
                strategy_id=intent.strategy_id,
                symbol=intent.symbol,
                side=intent.side.value,
                qty=effective_qty,
                price=exec_price,
                status=OrderState.REJECTED,
                message=reason,
                reserved_value=reserved_val,
            )
            self.idempotency_cache[intent.request_id] = res.model_dump()
            return res
            
        filled_qty = exch_res["fill"]["qty"]
        filled_price = exch_res["fill"]["price"]

        # Clear reserved risk and finalize position in Broker Ledger
        strat_pos = self.strategy_positions.setdefault(intent.strategy_id, {})
        strat_entry = self.strategy_entry_prices.setdefault(intent.strategy_id, {})

        curr_pos = strat_pos.get(intent.symbol, 0.0)
        curr_avg = strat_entry.get(intent.symbol, exec_price)

        if intent.side == OrderSide.BUY:
            self.strategy_reserved[intent.strategy_id] -= reserved_val
            self.strategy_balances[intent.strategy_id] += (reserved_val - (filled_qty * filled_price))
            new_qty = curr_pos + filled_qty
            if new_qty > 0:
                strat_entry[intent.symbol] = ((curr_pos * curr_avg) + (filled_qty * filled_price)) / new_qty
            else:
                strat_entry[intent.symbol] = filled_price
            strat_pos[intent.symbol] = new_qty
        elif intent.side == OrderSide.SELL:
            self.strategy_balances[intent.strategy_id] += (filled_qty * filled_price)
            new_qty = curr_pos - filled_qty
            strat_pos[intent.symbol] = new_qty
            if new_qty == 0:
                strat_entry[intent.symbol] = 0.0

        self._notify_order_transition(order_id, intent.strategy_id, intent.symbol, intent.side.value, filled_qty, filled_price, OrderState.SUBMITTED.value, "Submitted to Exchange")
        self._notify_order_transition(order_id, intent.strategy_id, intent.symbol, intent.side.value, filled_qty, filled_price, OrderState.ACKNOWLEDGED.value, "Exchange Acknowledged")

        final_state = OrderState.FILLED if filled_qty == effective_qty else OrderState.CANCELLED
        base_msg = f"Order Executed & Filled (Qty: {filled_qty})" if final_state == OrderState.FILLED else f"Order Partially Filled & Cancelled (Qty: {filled_qty} / {effective_qty})"
        msg = base_msg + (f" - {risk_msg}" if "CONCENTRATION_PENALTY" in risk_msg else "")
        
        self.db.transition_state(
            order_id, 
            final_state, 
            msg,
            executed_qty=filled_qty,
            execution_price=filled_price
        )
        self._notify_order_transition(order_id, intent.strategy_id, intent.symbol, intent.side.value, filled_qty, filled_price, final_state.value, msg)

        new_pos = strat_pos.get(intent.symbol, 0.0)
        curr_bal = self.strategy_balances.get(intent.strategy_id, 0.0)

        # Broadcast updated position back to Algo Pod / Listeners
        for listener in self.position_listeners:
            listener(intent.strategy_id, intent.symbol, new_pos, curr_bal)

        res = OrderResult(
            request_id=intent.request_id,
            order_id=order_id,
            strategy_id=intent.strategy_id,
            symbol=intent.symbol,
            side=intent.side.value,
            qty=filled_qty,
            price=filled_price,
            status=final_state,
            message=msg,
            reserved_value=reserved_val,
            execution_tx=signing_token,
        )
        self.idempotency_cache[intent.request_id] = res.model_dump()
        return res

    def cancel_order(self, order_id: str, simulate_network_failure: bool = False) -> OrderResult:
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

    def resolve_uncertain_order(self, order_id: str, evidence: dict):
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

    def resolve_unknown_orders(self):
        """Resolves orders in SUBMISSION_UNKNOWN state by querying the broker/exchange."""
        unknown_orders = [o for o in self.db.get_reconciliation_orders() if OrderState(o["state"]) == OrderState.SUBMISSION_UNKNOWN]
        
        for row in unknown_orders:
            order_id = row["order_id"]
            strat_id = row["strategy_id"]
            sym = row["symbol"]
            side = OrderSide(row["side"])
            exec_qty = row["qty"]
            exec_price = row["price"]
            reserved_val = row["reserved_value"]
            
            # Query the exchange
            fill_record = self.paper_exchange.query_order(order_id)
            
            if fill_record:
                # Found it! It was filled.
                actual_qty = fill_record["qty"]
                actual_price = fill_record["price"]
                fill_id = fill_record["fill_id"]
                
                # Apply it to positions and balances
                strat_pos = self.strategy_positions.setdefault(strat_id, {})
                strat_entry = self.strategy_entry_prices.setdefault(strat_id, {})
                curr_pos = strat_pos.get(sym, 0.0)
                curr_avg = strat_entry.get(sym, actual_price)

                if side == OrderSide.BUY:
                    self.strategy_reserved[strat_id] -= reserved_val
                    self.strategy_balances[strat_id] += (reserved_val - (actual_qty * actual_price))
                    new_qty = curr_pos + actual_qty
                    if new_qty > 0:
                        strat_entry[sym] = ((curr_pos * curr_avg) + (actual_qty * actual_price)) / new_qty
                    strat_pos[sym] = new_qty
                elif side == OrderSide.SELL:
                    self.strategy_balances[strat_id] += (actual_qty * actual_price)
                    new_qty = curr_pos - actual_qty
                    strat_pos[sym] = new_qty
                    if new_qty == 0:
                        strat_entry[sym] = 0.0

                self.db.transition_state(
                    order_id, 
                    OrderState.FILLED, 
                    f"Resolved as Executed (Qty: {actual_qty})",
                    executed_qty=actual_qty,
                    execution_price=actual_price,
                    execution_id=fill_id
                )
                self._notify_order_transition(order_id, strat_id, sym, side.value, actual_qty, actual_price, OrderState.FILLED.value, "Resolved as Executed")
            else:
                # If not found, and some timeout passed, we can assume it failed or we manually intervene.
                # For now, transition to REJECTED and release reservation.
                self.db.transition_state(order_id, OrderState.REJECTED, "Resolved as Not Found on Exchange")
                if side == OrderSide.BUY:
                    self.strategy_balances[strat_id] += reserved_val
                    self.strategy_reserved[strat_id] -= reserved_val
                self._notify_order_transition(order_id, strat_id, sym, side.value, exec_qty, exec_price, OrderState.REJECTED.value, "Resolved as Not Found")

    def get_broker_ledger_total_assets(self, strategy_id: str = "STRAT_MEAN_REV_001") -> float:
        """Calculates total assets tracked in Broker Ledger for strategy."""
        cash = self.strategy_balances.get(strategy_id, 0.0)
        reserved = self.strategy_reserved.get(strategy_id, 0.0)
        positions_val = 0.0
        pos_dict = self.strategy_positions.get(strategy_id, {})
        for sym, pos in pos_dict.items():
            price = self.reference_market_prices.get(sym, 0.0)
            positions_val += pos * price
        return cash + reserved + positions_val

    def process_execution_report(self, order_id: str, execution_id: str, qty: float, price: float) -> bool:
        """Processes an async/webhook execution report. Handles deduplication and out-of-order events."""
        if not self.db.record_execution(execution_id, order_id, qty, price):
            return False  # Duplicate

        order = self.db.get_order(order_id)
        if not order:
            return False
            
        strat_id = order["strategy_id"]
        sym = order["symbol"]
        side = OrderSide(order["side"])
        reserved_val = order["reserved_value"]
        current_state = OrderState(order["state"])
        
        # If it's a new fill, we apply to balances and positions
        strat_pos = self.strategy_positions.setdefault(strat_id, {})
        strat_entry = self.strategy_entry_prices.setdefault(strat_id, {})
        curr_pos = strat_pos.get(sym, 0.0)
        curr_avg = strat_entry.get(sym, price)
        
        if side == OrderSide.BUY:
            # Release proportional reserved risk
            # In a real system we'd calculate exactly how much was reserved for THIS qty, but for now we release all if it's the first fill or proportional
            if current_state in [OrderState.RISK_RESERVED, OrderState.SUBMITTED, OrderState.SUBMISSION_UNKNOWN, OrderState.ACKNOWLEDGED]:
                # If first fill, we might release the entire reservation and rely on cash balance, or keep it.
                # Actually, our simplified model deducts from reserved and applies to positions.
                # Let's just deduct cost from reserved if we have any reserved, else from cash.
                cost = qty * price
                if self.strategy_reserved.get(strat_id, 0.0) >= cost:
                    self.strategy_reserved[strat_id] -= cost
                else:
                    self.strategy_balances[strat_id] -= cost # fallback
            
            new_qty = curr_pos + qty
            if new_qty > 0:
                strat_entry[sym] = ((curr_pos * curr_avg) + (qty * price)) / new_qty
            strat_pos[sym] = new_qty
        elif side == OrderSide.SELL:
            self.strategy_balances[strat_id] += (qty * price)
            new_qty = curr_pos - qty
            strat_pos[sym] = new_qty
            if new_qty == 0:
                strat_entry[sym] = 0.0

        # Update state machine. If out-of-order, transition to FILLED directly.
        new_state = OrderState.FILLED
        if current_state != OrderState.FILLED:
            self.db.transition_state(
                order_id, 
                new_state, 
                f"Async Execution {execution_id} (Qty: {qty})",
                executed_qty=qty,
                execution_price=price,
                execution_id=execution_id,
                reserved_value=0.0 # Clear remaining reservation
            )
            self._notify_order_transition(order_id, strat_id, sym, side.value, qty, price, new_state.value, "Async Execution Applied")
        else:
            # Already filled, just update the cumulative qty in ledger (bypassing transition_state strict checks if we don't have PARTIAL_FILL)
            # Actually, `transition_state` allows transitioning from FILLED to FILLED? No, ALLOWED_TRANSITIONS for FILLED is set().
            # So if it's already FILLED, we must use a direct DB update or we add FILLED -> FILLED to ALLOWED_TRANSITIONS.
            pass
            
            # Let's just do a direct DB update for the extra execution since state is already FILLED
            with self.db.conn:
                self.db.conn.execute(
                    "UPDATE order_ledger SET executed_qty = executed_qty + ?, execution_price = ? WHERE order_id = ?",
                    (qty, price, order_id)
                )

        # Notify position listeners
        curr_bal = self.strategy_balances.get(strat_id, 0.0)
        for listener in self.position_listeners:
            listener(strat_id, sym, strat_pos[sym], curr_bal)
            
        return True
