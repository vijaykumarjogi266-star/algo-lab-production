"""
Market Data Ingestion Pipeline & Bar Construction Engine.
Implements the 9-stage pipeline:
1. Angel One Feed Ingestion
2. Schema Validation
3. Timestamp Normalization (UTC)
4. Duplicate & Out-of-Order Handling
5. Append-Only Raw Event Capture
6. Deterministic Bar Construction (1m, 5m, 1h)
7. Quality Gate (Canonical Bar Validator)
8. Timestamped Signal Generation
9. Simulated Execution & Paper Ledger Reconciliation

Adheres to Non-Negotiable Principles:
- Principle 3: Bad or uncertain data must not produce a trading decision.
- Principle 4: No lookahead bias (Signal on bar close t-1 executes on t open).
- Principle 13: Data validation must fail closed.
"""

import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Callable, Tuple
from collections import defaultdict

from data.schemas.canonical_market_data import (
    CanonicalMarketDataBar,
    CanonicalMarketDataValidator,
)
from data.schemas.contracts import DataQualityStatus
from services.market_data.adapters.market_event_schemas import (
    MarketTickEvent,
    MarketDataProvenance,
    DataSource,
    CollectionMode,
    FeedHealth,
    ExecutionMode,
    AccountingValidationStatus,
)


class FoundationExecutionGate:
    """
    Enforces quality-first foundation gating (Principle 3 & Principle 13):
    Strategy execution and paper orders remain strictly BLOCKED until:
    1. Accounting validation gate passes: accounting_validation == VERIFIED
    2. Fresh data streaming gate passes: real_connection_observed == True and feed_health == HEALTHY
    """

    @classmethod
    def evaluate_execution_readiness(
        cls,
        provenance: MarketDataProvenance,
        allow_diagnostic_simulation: bool = False,
    ) -> Tuple[bool, str]:
        """
        Evaluates whether strategy execution and paper order creation are permitted.
        Returns (is_permitted: bool, reason: str).
        """
        if allow_diagnostic_simulation:
            return True, "DIAGNOSTIC_SIMULATION_OVERRIDE_ACTIVE"

        if provenance.accounting_validation != AccountingValidationStatus.VERIFIED:
            return (
                False,
                f"GATE BLOCKED: Accounting validation is '{provenance.accounting_validation.value}'. "
                "Historical records remain unvalidated; forward strategy execution is strictly disabled."
            )

        if not provenance.real_connection_observed:
            return (
                False,
                "GATE BLOCKED: Fresh streaming not yet verified. "
                "Real market connection has not been observed; strategy execution is disabled."
            )

        if provenance.feed_health != FeedHealth.HEALTHY:
            return (
                False,
                f"GATE BLOCKED: Feed health is '{provenance.feed_health.value}'. "
                "Active feed must be continuous and healthy."
            )

        return True, "ALL FOUNDATION GATES PASSED: Forward paper execution authorized."


class MarketDataPipelineEngine:
    """
    End-to-end streaming market data ingestion, bar aggregation, and simulation engine.
    """

    def __init__(
        self,
        bar_interval_seconds: int = 60,  # 1-minute default bars
        raw_log_path: Optional[Path] = None,
        signal_generator: Optional[Callable[[CanonicalMarketDataBar], Optional[int]]] = None,
        paper_executor: Optional[Callable[[int, CanonicalMarketDataBar], None]] = None,
        provenance: Optional[MarketDataProvenance] = None,
        allow_diagnostic_simulation: bool = False,
    ):
        self.bar_interval_seconds = bar_interval_seconds
        self.raw_log_path = raw_log_path
        self.signal_generator = signal_generator
        self.paper_executor = paper_executor
        self.allow_diagnostic_simulation = allow_diagnostic_simulation
        self.provenance = provenance or MarketDataProvenance(
            data_source=DataSource.MOCK,
            collection_mode=CollectionMode.FORWARD,
            feed_health=FeedHealth.UNVERIFIED,
            execution_mode=ExecutionMode.PAPER if paper_executor else ExecutionMode.NONE,
            accounting_validation=AccountingValidationStatus.UNVALIDATED,
        )

        # Pipeline state tracking
        self.last_sequence_by_symbol: Dict[str, int] = defaultdict(int)
        self.last_timestamp_by_symbol: Dict[str, datetime] = {}
        self.last_cumulative_vol_by_symbol: Dict[str, int] = {}
        
        # Raw event buffer
        self.raw_event_journal: List[Dict[str, Any]] = []

        # Current in-progress bars: symbol -> partial bar dict
        self._current_bars: Dict[str, Dict[str, Any]] = {}
        # Completed canonical bars
        self.completed_bars: List[CanonicalMarketDataBar] = []
        
        # Statistics
        self.total_ticks_received: int = 0
        self.valid_ticks_processed: int = 0
        self.duplicates_dropped: int = 0
        self.out_of_order_count: int = 0
        self.quarantined_ticks: int = 0
        self.signals_emitted: int = 0
        self.volume_resets_detected: int = 0

    def process_tick(self, tick: MarketTickEvent) -> Optional[CanonicalMarketDataBar]:
        """
        Executes pipeline stages 2 through 9 for a single incoming tick.
        Returns a completed CanonicalMarketDataBar if the tick triggered a bar closure.
        """
        self.total_ticks_received += 1

        # Stage 2: Schema & Value Sanity Validation
        if tick.last_traded_price <= 0.0 or not tick.symbol:
            self.quarantined_ticks += 1
            return None

        # Stage 3: Timestamp Normalization
        if tick.exchange_timestamp.tzinfo is None:
            tick.exchange_timestamp = tick.exchange_timestamp.replace(tzinfo=timezone.utc)
        else:
            tick.exchange_timestamp = tick.exchange_timestamp.astimezone(timezone.utc)

        # Stage 4: Duplicate & Out-of-Order Handling
        sym = tick.symbol
        last_seq = self.last_sequence_by_symbol[sym]
        last_time = self.last_timestamp_by_symbol.get(sym)

        if last_seq > 0 and tick.sequence_id <= last_seq:
            self.duplicates_dropped += 1
            return None

        if last_time and tick.exchange_timestamp < (last_time - timedelta(seconds=2)):
            self.out_of_order_count += 1
            tick.quality_status = DataQualityStatus.SUSPICIOUS

        self.last_sequence_by_symbol[sym] = tick.sequence_id
        self.last_timestamp_by_symbol[sym] = tick.exchange_timestamp
        self.valid_ticks_processed += 1

        # Provenance tracking
        self.provenance.latest_event_at = tick.exchange_timestamp
        self.provenance.feed_received_at = tick.receive_timestamp
        if sym not in self.provenance.active_subscriptions:
            self.provenance.active_subscriptions.append(sym)
        self.provenance.feed_health = FeedHealth.HEALTHY

        # Stage 5: Append-Only Raw Event Capture
        event_record = tick.model_dump(mode="json")
        self.raw_event_journal.append(event_record)
        if self.raw_log_path:
            try:
                self.raw_log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.raw_log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event_record) + "\n")
            except Exception:
                pass

        # Stage 6: Deterministic Bar Construction
        completed_bar = self._aggregate_into_bar(tick)

        if completed_bar:
            # Stage 7: Quality Gate
            bar_validation = CanonicalMarketDataValidator.validate_series([completed_bar])
            if not bar_validation.is_valid:
                completed_bar.quality_status = DataQualityStatus.QUARANTINED
                return None

            self.completed_bars.append(completed_bar)

            # Stage 8: Timestamped Signal Generation Hook with Stale Feed Gate
            # Non-negotiable safety: If feed is stale, block new simulated entries.
            stale_symbols = self.check_stale_feeds(current_time=tick.receive_timestamp, max_staleness_seconds=60)
            if sym in stale_symbols:
                self.provenance.feed_health = FeedHealth.STALE
                # Stale feed: Do NOT generate trading signal or execute order.
                return completed_bar

            # Foundation Execution Gate: Strategy execution blocked until accounting and fresh-data gates pass
            can_exec, gate_reason = FoundationExecutionGate.evaluate_execution_readiness(
                self.provenance,
                allow_diagnostic_simulation=self.allow_diagnostic_simulation,
            )
            if not can_exec:
                # Observation-only mode: Strategy execution and paper ledger updates blocked
                return completed_bar

            if self.signal_generator:
                sig = self.signal_generator(completed_bar)
                if sig is not None and sig != 0:
                    self.signals_emitted += 1
                    # Stage 9: Simulated Execution & Paper Ledger Hook
                    if self.paper_executor:
                        self.paper_executor(sig, completed_bar)

        return completed_bar

    def _aggregate_into_bar(self, tick: MarketTickEvent) -> Optional[CanonicalMarketDataBar]:
        """Aggregates tick prices and volumes into fixed time interval OHLCV bars."""
        sym = tick.symbol
        t = tick.exchange_timestamp
        
        # Floor timestamp to interval boundary
        epoch = int(t.timestamp())
        interval_start_epoch = epoch - (epoch % self.bar_interval_seconds)
        bar_start_time = datetime.fromtimestamp(interval_start_epoch, tz=timezone.utc)

        cur = self._current_bars.get(sym)
        completed_bar = None

        # Incremental volume calculation with reset protection
        if sym not in self.last_cumulative_vol_by_symbol:
            delta_vol = tick.last_traded_quantity
            self.last_cumulative_vol_by_symbol[sym] = tick.cumulative_volume
        else:
            prior_cum = self.last_cumulative_vol_by_symbol[sym]
            if tick.cumulative_volume < prior_cum:
                # Exchange / session reset detected
                delta_vol = tick.last_traded_quantity
                self.last_cumulative_vol_by_symbol[sym] = tick.cumulative_volume
                self.volume_resets_detected += 1
            else:
                delta_vol = max(0, tick.cumulative_volume - prior_cum) if tick.cumulative_volume > 0 else tick.last_traded_quantity
                self.last_cumulative_vol_by_symbol[sym] = max(prior_cum, tick.cumulative_volume)

        if cur is None:
            # Start new bar
            self._current_bars[sym] = {
                "start_time": bar_start_time,
                "open": tick.last_traded_price,
                "high": tick.last_traded_price,
                "low": tick.last_traded_price,
                "close": tick.last_traded_price,
                "volume": float(delta_vol),
                "trade_count": 1,
            }
        elif cur["start_time"] == bar_start_time:
            # Update existing bar
            cur["high"] = max(cur["high"], tick.last_traded_price)
            cur["low"] = min(cur["low"], tick.last_traded_price)
            cur["close"] = tick.last_traded_price
            cur["volume"] += float(delta_vol)
            cur["trade_count"] += 1
        else:
            # Interval elapsed: Finalize current bar and start next
            completed_bar = CanonicalMarketDataBar(
                timestamp=cur["start_time"],
                symbol=sym,
                exchange="NSE",
                timeframe=f"{self.bar_interval_seconds}s",
                open=round(cur["open"], 2),
                high=round(cur["high"], 2),
                low=round(cur["low"], 2),
                close=round(cur["close"], 2),
                volume=round(cur["volume"], 2),
                trade_count=cur["trade_count"],
                turnover=round(cur["close"] * cur["volume"], 2),
                quality_status=DataQualityStatus.VALID,
            )

            # Initialize new bar
            self._current_bars[sym] = {
                "start_time": bar_start_time,
                "open": tick.last_traded_price,
                "high": tick.last_traded_price,
                "low": tick.last_traded_price,
                "close": tick.last_traded_price,
                "volume": float(delta_vol),
                "trade_count": 1,
            }

        return completed_bar

    def flush_open_bars(self) -> List[CanonicalMarketDataBar]:
        """Flushes any open bars at session end."""
        flushed = []
        for sym, cur in list(self._current_bars.items()):
            bar = CanonicalMarketDataBar(
                timestamp=cur["start_time"],
                symbol=sym,
                exchange="NSE",
                timeframe=f"{self.bar_interval_seconds}s",
                open=round(cur["open"], 2),
                high=round(cur["high"], 2),
                low=round(cur["low"], 2),
                close=round(cur["close"], 2),
                volume=round(cur["volume"], 2),
                trade_count=cur["trade_count"],
                turnover=round(cur["close"] * cur["volume"], 2),
                quality_status=DataQualityStatus.VALID,
            )
            flushed.append(bar)
            self.completed_bars.append(bar)
        self._current_bars.clear()
        return flushed

    def check_stale_feeds(
        self,
        current_time: Optional[datetime] = None,
        max_staleness_seconds: int = 60
    ) -> List[str]:
        """
        Detects symbols whose tick feed has ceased updating for > max_staleness_seconds.
        Strict Governance Rule: Does NOT fabricate ticks or mark positions closed during an outage.
        """
        now = current_time or datetime.now(timezone.utc)
        stale_symbols = []
        for sym, last_t in self.last_timestamp_by_symbol.items():
            if (now - last_t).total_seconds() > max_staleness_seconds:
                stale_symbols.append(sym)
        return stale_symbols

    def get_pipeline_telemetry(self) -> Dict[str, Any]:
        """Returns real-time data-quality and operational monitoring statistics."""
        return {
            "total_ticks_received": self.total_ticks_received,
            "valid_ticks_processed": self.valid_ticks_processed,
            "duplicates_dropped": self.duplicates_dropped,
            "out_of_order_count": self.out_of_order_count,
            "quarantined_ticks": self.quarantined_ticks,
            "volume_resets_detected": self.volume_resets_detected,
            "completed_bars_count": len(self.completed_bars),
            "signals_emitted": self.signals_emitted,
            "active_symbol_streams": list(self._current_bars.keys()),
            "provenance": self.provenance.model_dump(mode="json"),
        }
