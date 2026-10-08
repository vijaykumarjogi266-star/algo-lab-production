import sqlite3
import time
from decimal import Decimal
from typing import Optional, Dict, Any, Tuple, Callable
from enum import Enum

class ReservationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    CONSUMED = "CONSUMED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"
    RECONCILIATION_HOLD = "RECONCILIATION_HOLD"

class ReservationOutcome(str, Enum):
    RESERVED = "RESERVED"
    IDEMPOTENT_REPLAY = "IDEMPOTENT_REPLAY"
    REJECTED = "REJECTED"
    CONFLICT = "CONFLICT"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"


class CapitalReservationService:
    def __init__(self, db_conn: sqlite3.Connection, accounts_initial_capital: Dict[str, float] = None):
        """
        Initializes the reservation service with an SQLite connection.
        If using SQLite in WAL mode, we could rely on optimistic concurrency.
        But SQLite supports BEGIN EXCLUSIVE for serializable isolation, which guarantees
        atomic reservations preventing race conditions.
        """
        self.conn = db_conn
        self.accounts_initial_capital = accounts_initial_capital or {
            "STRAT_001": 100000.0,
            "STRAT_002": 50000.0,
            "STRAT_MEAN_REV_001": 100000.0,
            "BOT_A": 100000.0,
            "BOT_B": 100000.0
        }

    def _get_available_capital_locked(self, account_id: str, cursor: sqlite3.Cursor) -> Decimal:
        """
        Computes the available capital for an account by subtracting active and consumed reservations
        from the initial capital.
        """
        initial_cap = Decimal(str(self.accounts_initial_capital.get(account_id, 100000.0)))
        
        # Calculate sum of active + consumed reservations
        cursor.execute(
            "SELECT COALESCE(SUM(reserved_cash), 0.0) FROM capital_reservations WHERE account_id = ? AND status IN (?, ?)",
            (account_id, ReservationStatus.ACTIVE.value, ReservationStatus.CONSUMED.value)
        )
        row = cursor.fetchone()
        used_cap = Decimal(str(row[0])) if row and row[0] else Decimal("0.0")
        
        return initial_cap - used_cap

    def reserve_for_order(
        self,
        account_id: str,
        idempotency_key: str,
        qty: float,
        price: float,
        strategy_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        get_available_capital: Optional[Callable[[str], float]] = None
    ) -> Dict[str, Any]:
        """
        Reserves capital atomically using SQLite BEGIN EXCLUSIVE transaction.
        """
        # 1. Calculate worst-case reservation amount
        # For simplicity, assuming requested_notional = qty * price
        requested_notional = Decimal(str(qty)) * Decimal(str(price))
        reserved_cash = requested_notional # Assuming 100% margin/cash requirement for now
        reserved_margin = Decimal("0.0")
        
        max_retries = 5
        for attempt in range(max_retries):
            try:
                # Use a dedicated cursor and explicit EXCLUSIVE transaction
                cursor = self.conn.cursor()
                cursor.execute("BEGIN EXCLUSIVE")
                
                # Check for idempotency
                cursor.execute(
                    "SELECT reservation_id, requested_notional, reserved_cash, status FROM capital_reservations WHERE account_id = ? AND idempotency_key = ?",
                    (account_id, idempotency_key)
                )
                existing = cursor.fetchone()
                
                if existing:
                    cursor.execute("ROLLBACK")
                    # Check for material conflict
                    old_notional = Decimal(str(existing[1]))
                    if abs(old_notional - requested_notional) > Decimal("0.001"):
                        return {
                            "outcome": ReservationOutcome.CONFLICT,
                            "reason_code": "IDEMPOTENCY_CONFLICT",
                            "correlation_id": correlation_id
                        }
                    return {
                        "outcome": ReservationOutcome.IDEMPOTENT_REPLAY,
                        "reservation_id": existing[0],
                        "reserved_cash": Decimal(str(existing[2])),
                        "reserved_margin": Decimal("0.0"),
                        "available_capital_before": Decimal("0.0"), # We don't recalculate for replay
                        "available_capital_after": Decimal("0.0"),
                        "reason_code": "REPLAY",
                        "correlation_id": correlation_id
                    }
                
                # Read available capital
                if get_available_capital is not None:
                    base_capital = Decimal(str(get_available_capital(account_id)))
                    cursor.execute(
                        "SELECT COALESCE(SUM(reserved_cash), 0.0) FROM capital_reservations WHERE account_id = ? AND status = ?",
                        (account_id, ReservationStatus.ACTIVE.value)
                    )
                    active_row = cursor.fetchone()
                    active_res = Decimal(str(active_row[0])) if active_row and active_row[0] else Decimal("0.0")
                    available_capital = base_capital - active_res
                    print(f"base_capital={base_capital}, active_res={active_res}, available_capital={available_capital}")
                else:
                    available_capital = self._get_available_capital_locked(account_id, cursor)
                
                if available_capital < reserved_cash:
                    cursor.execute("ROLLBACK")
                    return {
                        "outcome": ReservationOutcome.REJECTED,
                        "reason_code": "INSUFFICIENT_CAPITAL",
                        "available_capital_before": available_capital,
                        "correlation_id": correlation_id
                    }
                
                # Create reservation
                reservation_id = f"RES_{idempotency_key}"
                now = time.time()
                
                cursor.execute(
                    """
                    INSERT INTO capital_reservations 
                    (reservation_id, account_id, strategy_id, idempotency_key, requested_notional, reserved_cash, reserved_margin, currency, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        reservation_id, account_id, strategy_id, idempotency_key,
                        float(requested_notional), float(reserved_cash), float(reserved_margin),
                        "USD", ReservationStatus.ACTIVE.value, now, now
                    )
                )
                
                cursor.execute("COMMIT")
                
                return {
                    "outcome": ReservationOutcome.RESERVED,
                    "reservation_id": reservation_id,
                    "reserved_cash": reserved_cash,
                    "reserved_margin": reserved_margin,
                    "available_capital_before": available_capital,
                    "available_capital_after": available_capital - reserved_cash,
                    "reason_code": "SUCCESS",
                    "correlation_id": correlation_id
                }
                
            except sqlite3.OperationalError as e:
                # database is locked
                self.conn.rollback()
                if "locked" in str(e).lower():
                    time.sleep(0.01 * (attempt + 1))
                    continue
                else:
                    return {
                        "outcome": ReservationOutcome.RETRYABLE_FAILURE,
                        "reason_code": f"DB_ERROR: {str(e)}",
                        "correlation_id": correlation_id
                    }
            except Exception as e:
                self.conn.rollback()
                return {
                    "outcome": ReservationOutcome.RETRYABLE_FAILURE,
                    "reason_code": f"UNKNOWN_ERROR: {str(e)}",
                    "correlation_id": correlation_id
                }
                
        return {
            "outcome": ReservationOutcome.RETRYABLE_FAILURE,
            "reason_code": "LOCK_TIMEOUT",
            "correlation_id": correlation_id
        }

    def consume_reservation(self, reservation_id: str, filled_qty: float, price: float, is_final: bool = False):
        """
        Consumes a portion of the reservation based on filled quantity.
        If is_final is True, any remaining unconsumed reservation is released.
        """
        # For simplicity, if we consume part of it, we could reduce reserved_cash and add to a filled amount.
        # But our available capital check sums both ACTIVE and CONSUMED reservations.
        # When an order executes, the broker deducts cash directly from account balance or we consider CONSUMED as permanently reducing available cash.
        # Let's just mark it CONSUMED if final.
        with self.conn:
            if is_final:
                self.conn.execute(
                    "UPDATE capital_reservations SET status = ?, updated_at = ? WHERE reservation_id = ?",
                    (ReservationStatus.CONSUMED.value, time.time(), reservation_id)
                )
            else:
                # partial fill, keep it ACTIVE but maybe reduce requested_notional?
                # Actually, if we just keep it ACTIVE, it still blocks the cash, which is correct until the order is closed.
                pass

    def release_reservation(self, reservation_id: str):
        """
        Releases a reservation, freeing up the capital.
        """
        with self.conn:
            self.conn.execute(
                "UPDATE capital_reservations SET status = ?, released_at = ?, updated_at = ? WHERE reservation_id = ?",
                (ReservationStatus.RELEASED.value, time.time(), time.time(), reservation_id)
            )

    def attach_order_id(self, reservation_id: str, order_id: str):
        with self.conn:
            self.conn.execute(
                "UPDATE capital_reservations SET order_id = ?, updated_at = ? WHERE reservation_id = ?",
                (order_id, time.time(), reservation_id)
            )
