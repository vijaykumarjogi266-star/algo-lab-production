"""
Algo Lab Real-Time Automated Tick Monitoring & Trailing Stop Engine.
Tracks active intraday paper session positions, manages dynamic ratchet trailing stops,
profit targets, hard stop losses, and enforces mandatory 15:15 IST auto square-off.
"""

from datetime import datetime, time, timezone
import json
import logging
from pathlib import Path
import sys
import threading
from typing import Any, Dict, List, Optional, Tuple
import zoneinfo

from pydantic import BaseModel, Field

from services.backtest_engine.contracts import OrderSide
from services.backtest_engine.execution_lifecycle import OrderLifecycleState
from services.paper_engine.session import PaperTradingEngine, PaperSession, SessionStatus

logger = logging.getLogger("TrailingStopEngine")

IST_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")
INTRADAY_CUTOFF_TIME = time(15, 15, 0)  # 15:15:00 IST


class ClockProtocol:
    """Interface for time queries to eliminate system clock coupling."""
    def now_ist(self) -> datetime:
        return datetime.now(IST_TZ)


class SystemClock(ClockProtocol):
    """Default system clock querying real-time IST."""
    def now_ist(self) -> datetime:
        return datetime.now(IST_TZ)


class FrozenClock(ClockProtocol):
    """Deterministic clock for testing and simulated replays."""
    def __init__(self, frozen_time: datetime):
        if frozen_time.tzinfo is None:
            self._time = frozen_time.replace(tzinfo=IST_TZ)
        else:
            self._time = frozen_time.astimezone(IST_TZ)

    def set_time(self, new_time: datetime):
        if new_time.tzinfo is None:
            self._time = new_time.replace(tzinfo=IST_TZ)
        else:
            self._time = new_time.astimezone(IST_TZ)

    def now_ist(self) -> datetime:
        return self._time


class TrailingPositionConfig(BaseModel):
    """Configuration for a position's trailing stop parameters."""
    symbol: str
    stop_loss_pct: float = 0.015  # Default 1.5% initial stop loss
    target_pct: float = 0.035     # Default 3.5% profit target
    trailing_distance_pct: float = 0.010  # 1.0% trailing distance behind watermark
    breakeven_trigger_pct: float = 0.010  # Move stop to entry once +1% profit is reached
    ratchet_step_pct: float = 0.005      # Minimum increment to ratchet stop upward
    initial_stop_loss: Optional[float] = None
    target_price: Optional[float] = None


class PositionGuardState(BaseModel):
    """Real-time monitoring and trailing stop state for an active position."""
    symbol: str
    side: OrderSide = OrderSide.BUY
    quantity: int
    entry_price: float
    current_price: float
    initial_stop_loss: float
    stop_loss: float
    target_price: Optional[float] = None
    highest_watermark: float
    lowest_watermark: float
    breakeven_locked: bool = False
    is_closed: bool = False
    is_exiting: bool = False  # Concurrency lock flag during order execution
    exit_reason: Optional[str] = None
    exit_price: Optional[float] = None
    exit_timestamp: Optional[str] = None
    config: TrailingPositionConfig

    @classmethod
    def create(
        cls,
        symbol: str,
        quantity: int,
        entry_price: float,
        side: OrderSide = OrderSide.BUY,
        initial_sl: Optional[float] = None,
        target_price: Optional[float] = None,
        config: Optional[TrailingPositionConfig] = None,
    ) -> "PositionGuardState":
        cfg = config or TrailingPositionConfig(symbol=symbol)
        
        # Priority: explicit initial_stop_loss from config > param initial_sl > percentage formula
        if cfg.initial_stop_loss is not None:
            sl = round(cfg.initial_stop_loss, 2)
        elif initial_sl is not None:
            sl = round(initial_sl, 2)
        elif side == OrderSide.BUY:
            sl = round(entry_price * (1.0 - cfg.stop_loss_pct), 2)
        else:
            sl = round(entry_price * (1.0 + cfg.stop_loss_pct), 2)

        # Priority: explicit target_price from config > param target_price > percentage formula
        if cfg.target_price is not None:
            tp = round(cfg.target_price, 2)
        elif target_price is not None:
            tp = round(target_price, 2)
        elif side == OrderSide.BUY:
            tp = round(entry_price * (1.0 + cfg.target_pct), 2)
        else:
            tp = round(entry_price * (1.0 - cfg.target_pct), 2)

        return cls(
            symbol=symbol.upper(),
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            current_price=entry_price,
            initial_stop_loss=sl,
            stop_loss=sl,
            target_price=tp,
            highest_watermark=entry_price,
            lowest_watermark=entry_price,
            breakeven_locked=False,
            is_closed=False,
            is_exiting=False,
            config=cfg,
        )

    def evaluate_tick(
        self,
        tick_price: float,
        current_time_ist: Optional[datetime] = None,
        force_square_off: bool = False,
        force_reason: Optional[str] = None,
        clock: Optional[ClockProtocol] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Evaluates incoming tick against trailing stop, hard stop, target, and 15:15 IST cutoff.
        Returns: (should_exit, exit_reason)
        """
        if self.is_closed or self.is_exiting:
            return False, None

        self.current_price = tick_price

        # 1. Mandatory Cutoff / Forced Square-off Evaluation
        if force_square_off:
            return True, force_reason or "FORCED_SQUARE_OFF"

        # Check current IST time: priority is current_time_ist > clock > default SystemClock
        if current_time_ist is not None:
            now_ist = current_time_ist
        elif clock is not None:
            now_ist = clock.now_ist()
        else:
            now_ist = datetime.now(IST_TZ)

        if now_ist.time() >= INTRADAY_CUTOFF_TIME:
            return True, "AUTO_SQUARE_OFF_1515_IST"

        # 2. Defensive Microstructure Guards
        # Guard against zero or non-positive price ticks (stale/disconnected feed)
        if tick_price <= 0.0:
            logger.warning(f"[{self.symbol}] Ignoring invalid non-positive tick price: ₹{tick_price}")
            return False, None

        # Guard against catastrophic circuit locks: if ask/bid price collapse or unrealistically distorted tick
        if self.entry_price > 0.0:
            price_deviation_pct = abs(tick_price - self.entry_price) / self.entry_price
            if price_deviation_pct > 0.35:  # Over 35% instantaneous deviation from entry implies bad tick / broken feed
                logger.error(f"[{self.symbol}] Extreme price deviation {price_deviation_pct*100:.1f}% detected (LTP: ₹{tick_price}). Rejecting tick to prevent bad fills.")
                return False, None

        # 3. Dynamic Trailing Stop Ratchet Updates
        if self.side == OrderSide.BUY:
            if tick_price > self.highest_watermark:
                self.highest_watermark = tick_price

            # Breakeven ratchet lock
            gain_pct = (self.highest_watermark - self.entry_price) / self.entry_price
            if not self.breakeven_locked and gain_pct >= self.config.breakeven_trigger_pct:
                if self.stop_loss < self.entry_price:
                    self.stop_loss = round(self.entry_price, 2)
                    self.breakeven_locked = True
                    logger.info(f"[{self.symbol}] Breakeven stop locked at entry: ₹{self.entry_price}")

            # Dynamic ratchet trail
            candidate_sl = round(self.highest_watermark * (1.0 - self.config.trailing_distance_pct), 2)
            # Ratchet rule: Stop loss ONLY moves upwards, never down
            if candidate_sl > self.stop_loss:
                # Require at least ratchet_step_pct move to avoid micro-chatter
                if (candidate_sl - self.stop_loss) >= (self.entry_price * self.config.ratchet_step_pct):
                    logger.info(f"[{self.symbol}] Ratchet Trailing SL adjusted: ₹{self.stop_loss} -> ₹{candidate_sl} (High: ₹{self.highest_watermark})")
                    self.stop_loss = candidate_sl

            # 3. Check Target & Stop triggers
            if self.target_price is not None and tick_price >= self.target_price:
                return True, "PROFIT_TARGET_HIT"

            if tick_price <= self.stop_loss:
                reason = "TRAILING_STOP_LOSS_HIT" if self.stop_loss > self.initial_stop_loss else "STOP_LOSS_HIT"
                return True, reason

        else:
            # SELL / Short position
            if tick_price < self.lowest_watermark:
                self.lowest_watermark = tick_price

            drop_pct = (self.entry_price - self.lowest_watermark) / self.entry_price
            if not self.breakeven_locked and drop_pct >= self.config.breakeven_trigger_pct:
                if self.stop_loss > self.entry_price:
                    self.stop_loss = round(self.entry_price, 2)
                    self.breakeven_locked = True
                    logger.info(f"[{self.symbol}] Breakeven short stop locked at entry: ₹{self.entry_price}")

            candidate_sl = round(self.lowest_watermark * (1.0 + self.config.trailing_distance_pct), 2)
            if candidate_sl < self.stop_loss:
                if (self.stop_loss - candidate_sl) >= (self.entry_price * self.config.ratchet_step_pct):
                    logger.info(f"[{self.symbol}] Ratchet Short Trailing SL adjusted: ₹{self.stop_loss} -> ₹{candidate_sl} (Low: ₹{self.lowest_watermark})")
                    self.stop_loss = candidate_sl

            if self.target_price is not None and tick_price <= self.target_price:
                return True, "PROFIT_TARGET_HIT"

            if tick_price >= self.stop_loss:
                reason = "TRAILING_STOP_LOSS_HIT" if self.stop_loss < self.initial_stop_loss else "STOP_LOSS_HIT"
                return True, reason

        return False, None


class TrailingStopEngine:
    """
    Real-Time Automated Tick Monitoring & Trailing Stop Engine for Algo Lab Paper Sessions.
    Thread-safe and resilient against concurrent tick races and risk order rejections.
    """

    def __init__(
        self,
        paper_engine: PaperTradingEngine,
        session_id: str,
        custom_configs: Optional[Dict[str, TrailingPositionConfig]] = None,
        clock: Optional[ClockProtocol] = None,
    ):
        self.paper_engine = paper_engine
        self.session_id = session_id
        self.configs = custom_configs or {}
        self.clock = clock or SystemClock()
        self.guards: Dict[str, PositionGuardState] = {}
        self._lock = threading.RLock()
        self.sync_from_session()

    def sync_from_session(self):
        """Initializes or synchronizes guards with active positions in the paper session."""
        with self._lock:
            session = self.paper_engine.get_session(self.session_id)
            if not session:
                raise ValueError(f"Session {self.session_id} not found in paper trading database.")

            open_positions = session.portfolio.positions

            # 1. Synchronize or create guards for currently open positions
            for sym, pos in open_positions.items():
                if sym not in self.guards or self.guards[sym].is_closed:
                    cfg = self.configs.get(sym, TrailingPositionConfig(symbol=sym))
                    self.guards[sym] = PositionGuardState.create(
                        symbol=sym,
                        quantity=pos.quantity,
                        entry_price=pos.average_entry_price,
                        side=pos.side,
                        config=cfg,
                    )
                    self.guards[sym].current_price = pos.current_price
                    self.guards[sym].highest_watermark = max(pos.average_entry_price, pos.current_price)
                    self.guards[sym].lowest_watermark = min(pos.average_entry_price, pos.current_price)
                else:
                    # Update quantity and watermarks for existing open guard
                    guard = self.guards[sym]
                    guard.quantity = pos.quantity
                    guard.current_price = pos.current_price
                    if pos.current_price > guard.highest_watermark:
                        guard.highest_watermark = pos.current_price
                    if pos.current_price < guard.lowest_watermark:
                        guard.lowest_watermark = pos.current_price

            # 2. Mark any guard whose position was closed externally as closed
            for sym, guard in self.guards.items():
                if sym not in open_positions and not guard.is_closed and not guard.is_exiting:
                    guard.is_closed = True
                    guard.exit_reason = guard.exit_reason or "CLOSED_EXTERNALLY"

    def get_guard(self, symbol: str) -> Optional[PositionGuardState]:
        with self._lock:
            return self.guards.get(symbol.upper())

    def process_tick(
        self,
        symbol: str,
        tick_price: float,
        current_time_ist: Optional[datetime] = None,
        force_square_off: bool = False,
        force_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Processes a single incoming tick for a symbol thread-safely.
        If an exit condition is met, automatically executes the closing order in PaperTradingEngine.
        Guarantees idempotency and prevents race conditions under high concurrent tick volume.
        """
        with self._lock:
            sym = symbol.upper()
            guard = self.guards.get(sym)
            if not guard or guard.is_closed or guard.is_exiting:
                return {"symbol": sym, "status": "IGNORED", "message": "Position not tracked, already closed, or exit in-flight"}

            effective_force_reason = force_reason or ("AUTO_SQUARE_OFF_1515_IST" if force_square_off else None)
            should_exit, exit_reason = guard.evaluate_tick(
                tick_price=tick_price,
                current_time_ist=current_time_ist,
                force_square_off=force_square_off,
                force_reason=effective_force_reason,
                clock=self.clock,
            )

            session = self.paper_engine.get_session(self.session_id)
            if not session:
                return {"symbol": sym, "status": "ERROR", "message": f"Session {self.session_id} not found"}
            pos = session.portfolio.positions.get(sym)

            if should_exit:
                # Concurrency lock flag: prevents any duplicate tick from entering order submission
                guard.is_exiting = True
                logger.info(f"🚨 EXIT TRIGGERED for {sym}: Reason={exit_reason} at LTP=₹{tick_price}")

                if not pos or pos.quantity <= 0:
                    guard.is_closed = True
                    guard.is_exiting = False
                    guard.exit_reason = "POSITION_ALREADY_CLOSED"
                    return {"symbol": sym, "status": "IGNORED", "message": "Position already closed in session"}

                exit_side = OrderSide.SELL if guard.side == OrderSide.BUY else OrderSide.BUY
                order_qty = pos.quantity
                exit_sl = round(tick_price * 1.05, 2) if exit_side == OrderSide.SELL else round(tick_price * 0.95, 2)

                try:
                    order, fill = self.paper_engine.submit_manual_order(
                        session_id=self.session_id,
                        symbol=sym,
                        side=exit_side,
                        quantity=order_qty,
                        price=tick_price,
                        stop_loss=exit_sl,
                    )
                except Exception as e:
                    guard.is_exiting = False
                    logger.error(f"Failed to submit manual exit order for {sym}: {e}")
                    return {
                        "symbol": sym,
                        "status": "ERROR",
                        "exit_reason": exit_reason,
                        "error_message": str(e),
                    }

                # Verify fill & order lifecycle state
                if fill is None or getattr(order, "state", None) == OrderLifecycleState.ORDER_REJECTED:
                    guard.is_exiting = False
                    rejection_reason = getattr(order, "rejection_reason", "Order rejected by risk engine")
                    logger.warning(f"❌ Exit order rejected for {sym}: {rejection_reason}")
                    return {
                        "symbol": sym,
                        "status": "EXIT_REJECTED",
                        "exit_reason": exit_reason,
                        "order_id": getattr(order, "order_id", None),
                        "rejection_reason": rejection_reason,
                    }

                guard.is_closed = True
                guard.is_exiting = False
                guard.exit_reason = exit_reason
                guard.exit_price = fill.fill_price if fill else tick_price
                guard.exit_timestamp = datetime.now(timezone.utc).isoformat()

                # Refresh session to fetch updated realized P&L and cash
                refreshed_session = self.paper_engine.get_session(self.session_id)

                return {
                    "symbol": sym,
                    "status": "EXECUTED_EXIT",
                    "exit_reason": exit_reason,
                    "exit_price": guard.exit_price,
                    "quantity": order_qty,
                    "order_id": order.order_id if order else None,
                    "fill": fill.model_dump() if fill else None,
                    "updated_cash": refreshed_session.portfolio.cash if refreshed_session else None,
                    "total_realized_pnl": refreshed_session.portfolio.total_realized_pnl if refreshed_session else None,
                }

            # Otherwise mark-to-market position in session
            if pos:
                pos.mark_to_market(tick_price)
                session.portfolio.mark_to_market({sym: tick_price})
                self.paper_engine._persist_session(session)

            unrealized_pnl = (
                round((tick_price - guard.entry_price) * guard.quantity, 2)
                if guard.side == OrderSide.BUY
                else round((guard.entry_price - tick_price) * guard.quantity, 2)
            )
            return {
                "symbol": sym,
                "status": "ACTIVE_MONITORING",
                "ltp": tick_price,
                "stop_loss": guard.stop_loss,
                "target_price": guard.target_price,
                "highest_watermark": guard.highest_watermark,
                "lowest_watermark": guard.lowest_watermark,
                "unrealized_pnl": unrealized_pnl,
                "breakeven_locked": guard.breakeven_locked,
            }

    def process_tick_batch(
        self,
        quotes: Dict[str, float],
        current_time_ist: Optional[datetime] = None,
        force_square_off: bool = False,
        force_reason: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Processes ticks for multiple symbols in a batch."""
        results = []
        for sym, price in quotes.items():
            res = self.process_tick(
                symbol=sym,
                tick_price=price,
                current_time_ist=current_time_ist,
                force_square_off=force_square_off,
                force_reason=force_reason,
            )
            results.append(res)
        return results

    def auto_square_off_all_positions(
        self,
        quotes: Optional[Dict[str, float]] = None,
        reason: str = "MANUAL_AUTO_SQUARE_OFF",
    ) -> List[Dict[str, Any]]:
        """Forces square-off for all active positions."""
        results = []
        with self._lock:
            for sym, guard in list(self.guards.items()):
                if not guard.is_closed:
                    price = (quotes.get(sym) if quotes else None) or guard.current_price
                    res = self.process_tick(
                        symbol=sym,
                        tick_price=price,
                        force_square_off=True,
                        force_reason=reason,
                    )
                    results.append(res)
        return results

    def get_status_summary(self) -> Dict[str, Any]:
        """Provides full real-time telemetry of monitored positions and portfolio."""
        session = self.paper_engine.get_session(self.session_id)
        positions_summary = []
        for sym, guard in self.guards.items():
            positions_summary.append({
                "symbol": sym,
                "side": guard.side.value,
                "quantity": guard.quantity,
                "entry_price": guard.entry_price,
                "current_price": guard.current_price,
                "stop_loss": guard.stop_loss,
                "target_price": guard.target_price,
                "highest_watermark": guard.highest_watermark,
                "breakeven_locked": guard.breakeven_locked,
                "is_closed": guard.is_closed,
                "exit_reason": guard.exit_reason,
                "exit_price": guard.exit_price,
            })

        return {
            "session_id": self.session_id,
            "session_name": session.name if session else None,
            "status": session.status.value if session else None,
            "portfolio": {
                "cash": session.portfolio.cash if session else 0.0,
                "total_equity": session.portfolio.total_equity if session else 0.0,
                "total_realized_pnl": session.portfolio.total_realized_pnl if session else 0.0,
                "total_unrealized_pnl": session.portfolio.total_unrealized_pnl if session else 0.0,
                "total_fees_paid": session.portfolio.total_fees_paid if session else 0.0,
            },
            "guards": positions_summary,
        }
