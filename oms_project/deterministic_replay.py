"""
OMS Project - Stage 2: Deterministic Historical Replay and Market-Regime Evaluation
(deterministic_replay.py)

Implements:
1. ReplayClock: Deterministic virtual clock with session and timezone awareness (Asia/Kolkata).
2. LookAheadBiasError: Fail-closed exception preventing any future-data leakage.
3. BoundedEventStream: Synchronized multi-symbol event queue enforcing strict visible historical bounds.
4. MarketRegime & RegimeEvaluator: Dynamic classification of market regimes (trend, range, volatility, etc.).
5. ReplayExecutionEngine: Full closed-loop deterministic simulation from verified datasets to durable reports.
"""

from __future__ import annotations
import math
import time
import uuid
import json
import sqlite3
from enum import Enum
from decimal import Decimal
from datetime import datetime, timezone, time as dt_time
from typing import List, Dict, Any, Optional, Tuple, Callable
from zoneinfo import ZoneInfo

from oms_project.calendar_service import NSECalendarService, IST_TZ
from oms_project.data_registry import HistoricalDataRegistry
from oms_project.schemas import OrderIntent, OrderResult, OrderSide, OrderState, NormalizedTick
from oms_project.gateway import BrokerGateway
from oms_project.paper_exchange import PaperExchange
from oms_project.central_data_feed import MarketDataService
from oms_project.scripts.reconciliation import AssetReconciler


class LookAheadBiasError(Exception):
    """Raised when an indicator, strategy, or query attempts to access future data beyond current replay time."""
    pass


class ReplayClockMonotonicityError(Exception):
    """Raised when replay time is moved backwards."""
    pass


class ReplayClockStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"


class MarketRegime(str, Enum):
    BULLISH_TREND = "BULLISH_TREND"
    BEARISH_TREND = "BEARISH_TREND"
    RANGE_BOUND = "RANGE_BOUND"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    LOW_LIQUIDITY = "LOW_LIQUIDITY"
    EVENT_DRIVEN = "EVENT_DRIVEN"
    OPENING_CLOSING_VOLATILITY = "OPENING_CLOSING_VOLATILITY"
    DEGRADED_DATA = "DEGRADED_DATA"
    UNCERTAIN = "UNCERTAIN"


class ReplayClock:
    """
    Deterministic Replay Clock.
    Provides authoritative simulation time, session awareness, and monotonic advancement.
    """

    def __init__(
        self,
        initial_time: Optional[float] = None,
        tz_name: str = "Asia/Kolkata",
        calendar_service: Optional[NSECalendarService] = None,
        enforce_session_hours: bool = False,
        filter_holidays: bool = False,
    ):
        self.tz = ZoneInfo(tz_name)
        self.calendar = calendar_service or NSECalendarService()
        self.enforce_session_hours = enforce_session_hours
        self.filter_holidays = filter_holidays
        self._current_time: float = initial_time if initial_time is not None else 0.0
        self._status: ReplayClockStatus = ReplayClockStatus.IDLE

    @property
    def current_time(self) -> float:
        return self._current_time

    @property
    def current_datetime(self) -> datetime:
        return datetime.fromtimestamp(self._current_time, tz=timezone.utc).astimezone(self.tz)

    @property
    def status(self) -> ReplayClockStatus:
        return self._status

    def start(self):
        self._status = ReplayClockStatus.RUNNING

    def pause(self):
        self._status = ReplayClockStatus.PAUSED

    def resume(self):
        self._status = ReplayClockStatus.RUNNING

    def stop(self):
        self._status = ReplayClockStatus.STOPPED

    def reset(self, initial_time: float = 0.0):
        self._current_time = initial_time
        self._status = ReplayClockStatus.IDLE

    def advance_to(self, new_timestamp: float):
        """Advances replay clock to new_timestamp. Enforces strict monotonicity."""
        if new_timestamp < self._current_time:
            raise ReplayClockMonotonicityError(
                f"Clock cannot move backwards from {self._current_time} to {new_timestamp}"
            )
        self._current_time = new_timestamp

    def is_regular_session(self) -> bool:
        """Determines if current simulation time is within regular NSE trading hours (09:15 - 15:30 IST)."""
        dt = self.current_datetime
        if not self.calendar.is_trading_day(dt):
            return False
        ist_time = dt.time()
        return dt_time(9, 15) <= ist_time <= dt_time(15, 30)

    def is_opening_or_closing_window(self) -> bool:
        """Opening 15 mins (09:15 - 09:30) or closing 15 mins (15:15 - 15:30)."""
        if not self.is_regular_session():
            return False
        ist_time = self.current_datetime.time()
        return (dt_time(9, 15) <= ist_time < dt_time(9, 30)) or (dt_time(15, 15) <= ist_time <= dt_time(15, 30))


class BoundedEventStream:
    """
    Look-ahead protected event stream.
    Synchronizes multi-symbol tick events and guards history access.
    """

    def __init__(self, clock: ReplayClock):
        self.clock = clock
        self._all_events: List[Dict[str, Any]] = []
        self._symbol_history: Dict[str, List[Dict[str, Any]]] = {}
        self._cursor: int = 0

    def load_events(self, events: List[Dict[str, Any]]):
        """
        Loads and deterministically sorts events by (timestamp, symbol).
        """
        # Ensure deterministic ordering: timestamp first, then symbol
        sorted_events = sorted(events, key=lambda x: (float(x["timestamp"]), str(x.get("symbol", ""))))
        self._all_events = sorted_events
        self._symbol_history = {}
        self._cursor = 0

    @property
    def total_events(self) -> int:
        return len(self._all_events)

    @property
    def remaining_events(self) -> int:
        return max(0, len(self._all_events) - self._cursor)

    def has_next(self) -> bool:
        return self._cursor < len(self._all_events)

    def next_event(self) -> Optional[Dict[str, Any]]:
        """Advances cursor, updates replay clock, and stores visible event into history."""
        if not self.has_next():
            return None
        event = self._all_events[self._cursor]
        ts = float(event["timestamp"])
        self.clock.advance_to(ts)

        symbol = str(event.get("symbol", "")).upper()
        if symbol not in self._symbol_history:
            self._symbol_history[symbol] = []
        self._symbol_history[symbol].append(event)

        self._cursor += 1
        return event

    def get_history(
        self,
        symbol: Optional[str] = None,
        start: Optional[float] = None,
        end: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Returns history strictly at or before current replay clock.
        Raises LookAheadBiasError if end > clock.current_time.
        """
        curr = self.clock.current_time
        if end is not None and end > curr:
            raise LookAheadBiasError(
                f"Look-ahead violation: requested history until {end}, but replay clock is at {curr}"
            )

        effective_end = end if end is not None else curr
        source = (
            self._symbol_history.get(symbol.upper(), [])
            if symbol
            else [e for e in self._all_events[: self._cursor]]
        )

        filtered = [
            e for e in source
            if float(e["timestamp"]) <= effective_end and (start is None or float(e["timestamp"]) >= start)
        ]
        return filtered

    def peek_future(self, delta_seconds: float = 1.0):
        """Strictly prohibited: peeking into future data raises LookAheadBiasError."""
        raise LookAheadBiasError(
            f"Future peeking is prohibited! Attempted to peek +{delta_seconds}s beyond {self.clock.current_time}"
        )


class RegimeEvaluator:
    """
    Evaluates market regime based on visible price action, rolling volatility,
    volume liquidity, and time-of-day dynamics.
    """

    def __init__(
        self,
        volatility_threshold: float = 0.008,
        min_volume_threshold: float = 20.0,
        trend_threshold_pct: float = 0.002,
        window_size: int = 20,
    ):
        self.volatility_threshold = volatility_threshold
        self.min_volume_threshold = min_volume_threshold
        self.trend_threshold_pct = trend_threshold_pct
        self.window_size = window_size

    def evaluate(
        self,
        clock: ReplayClock,
        history: List[Dict[str, Any]],
        current_tick: Dict[str, Any],
    ) -> Tuple[MarketRegime, float]:
        """
        Evaluates current market regime and returns (MarketRegime, confidence).
        """
        # 1. Opening / Closing session volatility
        if clock.is_opening_or_closing_window():
            return MarketRegime.OPENING_CLOSING_VOLATILITY, 0.95

        # 2. Check for degraded data (timestamp gaps > 300s during regular trading)
        if len(history) >= 2:
            timestamps = [float(t["timestamp"]) for t in history]
            max_gap = max(timestamps[i] - timestamps[i - 1] for i in range(1, len(timestamps)))
            if max_gap > 300.0 and clock.is_regular_session():
                return MarketRegime.DEGRADED_DATA, 0.9

        # 3. Insufficient data
        if len(history) < max(5, self.window_size // 4):
            return MarketRegime.UNCERTAIN, 0.2

        recent = history[-self.window_size:] if len(history) >= self.window_size else history
        prices = [float(t["price"]) for t in recent]
        volumes = [float(t.get("volume", 1.0)) for t in recent]

        # 4. Liquidity check
        avg_volume = sum(volumes) / len(volumes)
        if avg_volume < self.min_volume_threshold:
            return MarketRegime.LOW_LIQUIDITY, 0.85

        curr_price = float(current_tick["price"])
        mean_price = sum(prices) / len(prices)
        variance = sum((p - mean_price) ** 2 for p in prices) / len(prices)
        std_dev = math.sqrt(variance)
        normalized_vol = std_dev / mean_price if mean_price > 0 else 0.0

        # 5. Volatility check
        if normalized_vol > self.volatility_threshold:
            return MarketRegime.HIGH_VOLATILITY, 0.90

        # 6. Trend check
        first_p = prices[0]
        last_p = prices[-1]
        pct_change = (last_p - first_p) / first_p if first_p > 0 else 0.0

        if pct_change >= self.trend_threshold_pct:
            return MarketRegime.BULLISH_TREND, 0.80
        elif pct_change <= -self.trend_threshold_pct:
            return MarketRegime.BEARISH_TREND, 0.80

        # 7. Low Volatility vs Range Bound
        if normalized_vol < (self.volatility_threshold * 0.3):
            return MarketRegime.LOW_VOLATILITY, 0.75

        return MarketRegime.RANGE_BOUND, 0.85


class ReplayExecutionEngine:
    """
    Deterministic Historical Replay Execution Engine.
    Executes an end-to-end replay workflow:
    Immutable dataset -> Replay clock -> Bounded event stream -> Regime evaluation -> Strategy decision -> OMS/Gateway -> Accounting & Durable Replay Report.
    """

    def __init__(
        self,
        db_path: str = ":memory:",
        initial_cash: float = 100000.0,
        slippage_bps: float = 0.0,
        fee_rate_bps: float = 5.0,  # 0.05%
        calendar_service: Optional[NSECalendarService] = None,
        enforce_session_hours: bool = False,
    ):
        self.db_path = db_path
        self.initial_cash = initial_cash
        self.slippage_bps = slippage_bps
        self.fee_rate_bps = fee_rate_bps
        self.calendar_service = calendar_service or NSECalendarService()
        self.enforce_session_hours = enforce_session_hours

    def run_replay(
        self,
        dataset_id: str,
        registry: HistoricalDataRegistry,
        strategy_class: Any,
        strategy_params: Dict[str, Any],
        strategy_id: str = "STRAT_REPLAY_001",
        symbol: str = "RELIANCE",
        allowed_regimes: Optional[List[MarketRegime]] = None,
    ) -> Dict[str, Any]:
        """
        Executes a deterministic replay simulation against a verified dataset.
        """
        # 1. Verify dataset integrity against registry
        meta = registry.verify_integrity(dataset_id)
        config = {
            "strategy_id": strategy_id,
            "strategy_params": strategy_params,
            "slippage_bps": self.slippage_bps,
            "fee_rate_bps": self.fee_rate_bps,
            "initial_cash": self.initial_cash,
            "allowed_regimes": [r.value for r in allowed_regimes] if allowed_regimes else None,
        }
        replay_run_id = registry.create_replay_run(dataset_id=dataset_id, configuration=config)

        # 2. Read events from verified dataset file
        events = []
        import csv
        with open(meta.file_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                events.append({
                    "symbol": str(row["symbol"]).upper(),
                    "price": float(row["price"]),
                    "volume": float(row.get("volume", 1.0)),
                    "timestamp": float(row["timestamp"]),
                })

        # 3. Setup Replay Clock and Bounded Event Stream
        initial_ts = float(events[0]["timestamp"]) if events else 0.0
        clock = ReplayClock(
            initial_time=initial_ts,
            calendar_service=self.calendar_service,
            enforce_session_hours=self.enforce_session_hours,
        )
        stream = BoundedEventStream(clock=clock)
        stream.load_events(events)

        # 4. Setup Simulation Gateway and Broker
        paper_ex = PaperExchange(initial_cash=self.initial_cash)
        gateway = BrokerGateway(
            paper_exchange=paper_ex,
            simulation_mode=True,
            slippage_bps=self.slippage_bps,
        )
        gateway.reset_simulation(initial_cash=self.initial_cash)
        gateway.strategy_balances[strategy_id] = self.initial_cash
        gateway.strategy_reserved[strategy_id] = 0.0
        gateway.strategy_positions[strategy_id] = {}
        gateway.strategy_entry_prices[strategy_id] = {}
        gateway.simulation_mode = True
        gateway.slippage_bps = self.slippage_bps

        # 5. Initialize Strategy and Regime Evaluator
        evaluator = RegimeEvaluator()
        bot = strategy_class(
            strategy_id=strategy_id,
            symbol=symbol,
            **strategy_params,
        )

        clock.start()

        # Replay Metrics Tracking
        total_ticks = 0
        total_decisions = 0
        total_orders = 0
        total_fills = 0
        total_rejections = 0
        total_slippage = Decimal("0.00")
        total_fees = Decimal("0.00")

        regime_counts: Dict[str, int] = {r.value: 0 for r in MarketRegime}
        regime_trades: Dict[str, int] = {r.value: 0 for r in MarketRegime}
        regime_pnl: Dict[str, float] = {r.value: 0.0 for r in MarketRegime}

        peak_equity = self.initial_cash
        max_drawdown_pct = 0.0
        turnover = Decimal("0.00")
        trade_entry_prices: Dict[str, float] = {}
        last_regime = MarketRegime.UNCERTAIN

        # 6. Step through events
        while stream.has_next():
            raw_event = stream.next_event()
            if not raw_event:
                break

            total_ticks += 1
            tick_symbol = raw_event["symbol"]
            tick_price = float(raw_event["price"])
            tick_ts = float(raw_event["timestamp"])

            # Session Filtering if enabled
            if self.enforce_session_hours and not clock.is_regular_session():
                continue

            gateway.set_market_price(tick_symbol, tick_price, tick_ts)

            # Evaluate market regime strictly on visible history
            history = stream.get_history(symbol=tick_symbol)
            current_regime, confidence = evaluator.evaluate(clock, history, raw_event)
            last_regime = current_regime
            regime_counts[current_regime.value] += 1

            # Check if strategy is permitted to act in this regime
            regime_allowed = True
            if allowed_regimes and current_regime not in allowed_regimes:
                regime_allowed = False

            # Let strategy inspect tick
            intent: Optional[OrderIntent] = None
            if regime_allowed and hasattr(bot, "on_tick"):
                intent = bot.on_tick(tick_price, timestamp=tick_ts)

            total_decisions += 1

            if intent:
                total_orders += 1
                res = gateway.process_order_intent(intent)
                if res.status == OrderState.FILLED:
                    total_fills += 1
                    regime_trades[current_regime.value] += 1
                    fill_val = Decimal(str(res.price)) * Decimal(str(res.qty))
                    turnover += fill_val

                    # Calculate slippage
                    expected_price = Decimal(str(intent.price))
                    actual_price = Decimal(str(res.price))
                    slip = abs(actual_price - expected_price) * Decimal(str(res.qty))
                    total_slippage += slip

                    # Simulate fee
                    fee = fill_val * (Decimal(str(self.fee_rate_bps)) / Decimal("10000.0"))
                    total_fees += fee
                elif res.status == OrderState.REJECTED:
                    total_rejections += 1

            # Track peak equity and drawdown
            curr_assets = gateway.get_broker_ledger_total_assets(strategy_id)
            if curr_assets > peak_equity:
                peak_equity = curr_assets
            dd = (peak_equity - curr_assets) / peak_equity * 100.0 if peak_equity > 0 else 0.0
            if dd > max_drawdown_pct:
                max_drawdown_pct = dd

        clock.stop()

        # 7. Final Accounting and Reconciliation
        reconciler = AssetReconciler(gateway, gateway.paper_exchange)
        recon_report = reconciler.run_reconciliation(strategy_id)

        final_equity = gateway.get_broker_ledger_total_assets(strategy_id)
        # Deduct simulated fees from final equity
        final_equity_after_fees = float(Decimal(str(final_equity)) - total_fees)
        net_pnl = final_equity_after_fees - self.initial_cash

        # 8. Persist Replay Execution Report
        report_id = f"RPT_{uuid.uuid4().hex[:12].upper()}"
        report_payload = {
            "report_id": report_id,
            "replay_run_id": replay_run_id,
            "strategy_id": strategy_id,
            "strategy_version": getattr(bot, "version", "1.0.0"),
            "dataset_id": dataset_id,
            "dataset_checksum": meta.sha256_checksum,
            "total_ticks": total_ticks,
            "total_decisions": total_decisions,
            "total_orders": total_orders,
            "total_fills": total_fills,
            "total_rejections": total_rejections,
            "initial_cash": f"{Decimal(str(self.initial_cash)):.8f}",
            "final_equity": f"{Decimal(str(final_equity_after_fees)):.8f}",
            "net_pnl": f"{Decimal(str(net_pnl)):.8f}",
            "max_drawdown_pct": f"{Decimal(str(max_drawdown_pct)):.4f}",
            "turnover": f"{turnover:.4f}",
            "total_fees": f"{total_fees:.4f}",
            "total_slippage": f"{total_slippage:.4f}",
            "reconciliation_status": recon_report["status"],
            "regimes_summary": {k: v for k, v in regime_counts.items() if v > 0},
            "regimes_trades": {k: v for k, v in regime_trades.items() if v > 0},
            "metrics": {
                "order_to_fill_ratio": (total_fills / total_orders) if total_orders > 0 else 1.0,
                "rejection_rate": (total_rejections / total_orders) if total_orders > 0 else 0.0,
                "reconciliation_variance": recon_report["variance"],
            },
            "created_at": time.time(),
        }

        conn = getattr(registry, "conn", None)
        if conn is None and hasattr(registry, "db"):
            conn = getattr(registry.db, "conn", None)
        if conn:
            self._persist_report(conn, report_payload)

        return report_payload

    def _persist_report(self, conn: sqlite3.Connection, report: Dict[str, Any]):
        """Persists the replay execution report into SQLite."""
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO replay_execution_reports (
                report_id, replay_run_id, strategy_id, strategy_version,
                dataset_id, dataset_checksum, total_ticks, total_decisions,
                total_orders, total_fills, total_rejections, initial_cash,
                final_equity, net_pnl, max_drawdown_pct, turnover,
                total_fees, total_slippage, reconciliation_status,
                regimes_summary_json, metrics_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report["report_id"],
                report["replay_run_id"],
                report["strategy_id"],
                report["strategy_version"],
                report["dataset_id"],
                report["dataset_checksum"],
                report["total_ticks"],
                report["total_decisions"],
                report["total_orders"],
                report["total_fills"],
                report["total_rejections"],
                report["initial_cash"],
                report["final_equity"],
                report["net_pnl"],
                report["max_drawdown_pct"],
                report["turnover"],
                report["total_fees"],
                report["total_slippage"],
                report["reconciliation_status"],
                json.dumps({
                    "counts": report["regimes_summary"],
                    "trades": report["regimes_trades"],
                }),
                json.dumps(report["metrics"]),
                report["created_at"],
            ),
        )
        conn.commit()
