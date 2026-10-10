"""Multi-Symbol Real-Time Equity Scanner & Strategy Execution Engine (Work Package B).

Pipeline:
MARKET EVENT → SYMBOL STATE → BAR/TICK AGGREGATION → INDICATORS → SCANNERS → STRATEGY CONDITIONS → SETUP CANDIDATE → RISK

Adheres to Requirements:
- Multi-symbol universe state tracking
- Deterministic point-in-time calculation (no lookahead)
- Integration with existing repository strategies (VWAPReversion, ORB, BaseStrategy)
- Symbol state isolation & session reset
- Structured setup candidate output (TradeCandidate)
- Complete audit trail of evaluated setups and decisions
- Subsystem health telemetry for SCANNER and STRATEGY
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

import numpy as np

from data.schemas.canonical_market_data import CanonicalMarketDataBar
from data.schemas.contracts import OHLCVBar, Exchange, TimeFrame
from quant.indicators.atr import ATR
from quant.indicators.rsi import RSI
from quant.indicators.relative_volume import RelativeVolume
from quant.indicators.vwap import VWAP
from quant.strategies.base import BaseStrategy, StrategyDecision
from quant.strategies.orb import OpeningRangeBreakout
from quant.strategies.vwap_reversion import VWAPReversion
from services.backtest_engine.trade_candidate import CandidateAction, TradeCandidate
from services.common.health import ComponentName, ComponentOperationalState, SubsystemHealth
from services.data_quality.validator import DataQualityReport, DataQualityValidator

logger = logging.getLogger(__name__)


class SymbolScannerState:
    """Isolated per-symbol state container for bar history and indicator calculation."""

    def __init__(self, symbol: str, max_history_bars: int = 200):
        self.symbol = symbol.upper()
        self.max_history_bars = max_history_bars
        self.history: List[CanonicalMarketDataBar] = []
        
        # Indicator engines
        self.vwap_engine = VWAP(num_std=2.0)
        self.atr_engine = ATR(period=14)
        self.rsi_engine = RSI(period=14)
        self.rvol_engine = RelativeVolume(period=20)

    def append_bar(self, bar: CanonicalMarketDataBar):
        """Appends a new bar, maintaining point-in-time ordering and max history limit."""
        if self.history and bar.timestamp <= self.history[-1].timestamp:
            # Drop duplicate or out-of-order bar
            return
        
        self.history.append(bar)
        if len(self.history) > self.max_history_bars:
            self.history = self.history[-self.max_history_bars:]

    def compute_indicators(self) -> Dict[str, Optional[float]]:
        """Computes current indicator values deterministically from historical close/high/low/volume arrays."""
        if not self.history:
            return {}

        closes = np.array([b.close for b in self.history], dtype=float)
        highs = np.array([b.high for b in self.history], dtype=float)
        lows = np.array([b.low for b in self.history], dtype=float)
        volumes = np.array([b.volume for b in self.history], dtype=float)

        indicators: Dict[str, Optional[float]] = {}

        try:
            # 1. VWAP
            vwap_res = self.vwap_engine.calculate(closes, highs=highs, lows=lows, volumes=volumes)
            indicators["vwap"] = float(vwap_res["vwap"][-1]) if not np.isnan(vwap_res["vwap"][-1]) else None
            indicators["vwap_upper"] = float(vwap_res["vwap_upper"][-1]) if not np.isnan(vwap_res["vwap_upper"][-1]) else None
            indicators["vwap_lower"] = float(vwap_res["vwap_lower"][-1]) if not np.isnan(vwap_res["vwap_lower"][-1]) else None
        except Exception:
            pass

        try:
            # 2. ATR(14)
            atr_arr = self.atr_engine.calculate(closes, highs=highs, lows=lows)
            indicators["atr_14"] = float(atr_arr[-1]) if not np.isnan(atr_arr[-1]) else None
        except Exception:
            pass

        try:
            # 3. RSI(14)
            rsi_arr = self.rsi_engine.calculate(closes)
            indicators["rsi_14"] = float(rsi_arr[-1]) if not np.isnan(rsi_arr[-1]) else None
        except Exception:
            pass

        try:
            # 4. RVOL(20)
            rvol_arr = self.rvol_engine.calculate(closes, volumes=volumes)
            indicators["rvol_20"] = float(rvol_arr[-1]) if not np.isnan(rvol_arr[-1]) else None
        except Exception:
            pass

        return indicators


class MultiSymbolScannerEngine:
    """Multi-symbol scanning engine orchestrating quantitative strategies across live bar streams."""

    def __init__(
        self,
        universe: Optional[List[str]] = None,
        strategies: Optional[List[BaseStrategy]] = None,
    ):
        self._lock = threading.RLock()
        self.universe = [s.upper().strip() for s in (universe or ["SBIN", "RELIANCE", "TCS"])]
        
        # Symbol state isolation
        self.symbol_states: Dict[str, SymbolScannerState] = {
            sym: SymbolScannerState(sym) for sym in self.universe
        }

        # Registered deterministic strategies
        self.strategies: List[BaseStrategy] = strategies or [
            VWAPReversion(std_dev_threshold=2.0, stop_loss_atr_mult=1.5),
            OpeningRangeBreakout(range_bars=3, volume_multiplier=1.2, risk_reward_ratio=2.0),
        ]

        # Audit trail of evaluated setup candidates
        self.candidate_journal: List[TradeCandidate] = []
        self.decisions_journal: List[StrategyDecision] = []

        # Candidate subscribers
        self._candidate_subscribers: List[Callable[[TradeCandidate], None]] = []

        # Subsystem health
        self.scanner_health = SubsystemHealth(
            component_name=ComponentName.SCANNER,
            state=ComponentOperationalState.STOPPED,
            message="Scanner engine initialized",
        )
        self.strategy_health = SubsystemHealth(
            component_name=ComponentName.STRATEGY,
            state=ComponentOperationalState.STOPPED,
            message="Strategy engine initialized",
        )

        # Statistics
        self.bars_scanned: int = 0
        self.candidates_generated: int = 0
        self.open_position_symbols: Set[str] = set()

    def subscribe_candidates(self, callback: Callable[[TradeCandidate], None]):
        """Registers a callback for generated trade candidates."""
        with self._lock:
            if callback not in self._candidate_subscribers:
                self._candidate_subscribers.append(callback)

    def set_open_positions(self, open_symbols: List[str]):
        """Updates list of symbols with active positions to prevent double entries."""
        with self._lock:
            self.open_position_symbols = set(s.upper() for s in open_symbols)

    def reset_session(self):
        """Resets per-session internal state across all symbols and strategies."""
        with self._lock:
            for sym in self.universe:
                self.symbol_states[sym] = SymbolScannerState(sym)
            self.candidate_journal.clear()
            self.decisions_journal.clear()
            self.bars_scanned = 0
            self.candidates_generated = 0
            self.open_position_symbols.clear()
            
            # Re-initialize strategy session state if present
            for strat in self.strategies:
                if isinstance(strat, OpeningRangeBreakout):
                    strat.opening_high = None
                    strat.opening_low = None
                    strat.session_bar_count = 0
                    strat.current_session_date = None
                    strat.trade_taken_today = False

            self.scanner_health.update_state(ComponentOperationalState.STOPPED, "Session state reset complete")
            self.strategy_health.update_state(ComponentOperationalState.STOPPED, "Strategy session state reset")

    def process_bar(self, bar: CanonicalMarketDataBar) -> List[TradeCandidate]:
        """
        Executes scanner pipeline for an incoming canonical bar:
        MARKET EVENT → SYMBOL STATE → BAR AGGREGATION → INDICATORS → SCANNERS → STRATEGY → CANDIDATE
        """
        sym = bar.symbol.upper()
        if sym not in self.symbol_states:
            return []

        generated_candidates: List[TradeCandidate] = []

        with self._lock:
            self.bars_scanned += 1
            state = self.symbol_states[sym]
            state.append_bar(bar)

            # Convert canonical bar to contract bar for strategy compatibility
            turnover_val = bar.turnover if bar.turnover is not None else (bar.close * bar.volume)
            contract_bar = OHLCVBar(
                symbol=bar.symbol,
                exchange=Exchange.NSE,
                timeframe=TimeFrame.M1 if "60" in bar.timeframe or "1m" in bar.timeframe else TimeFrame.M5,
                market_timestamp=bar.timestamp,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                vwap=turnover_val / max(1.0, bar.volume) if bar.volume > 0 else bar.close,
            )

            # Compute indicator snapshot
            indicators = state.compute_indicators()
            has_pos = sym in self.open_position_symbols

            # Evaluate registered strategies
            for strategy in self.strategies:
                candidate = None
                
                # Check if strategy implements on_bar (TradeCandidate model)
                if hasattr(strategy, "on_bar"):
                    candidate = strategy.on_bar(
                        current_bar=contract_bar,
                        history=[
                            OHLCVBar(
                                symbol=hb.symbol,
                                exchange=Exchange.NSE,
                                timeframe=TimeFrame.M1,
                                market_timestamp=hb.timestamp,
                                open=hb.open,
                                high=hb.high,
                                low=hb.low,
                                close=hb.close,
                                volume=hb.volume,
                            )
                            for hb in state.history[:-1]
                        ],
                        indicators=indicators,
                        has_open_position=has_pos,
                    )

                # Evaluate base contract interface
                dq_report = DataQualityValidator().validate_series([contract_bar])
                decision = strategy.evaluate(
                    current_bar=contract_bar,
                    history=[],
                    data_quality=dq_report,
                )
                self.decisions_journal.append(decision)

                if candidate:
                    self.candidates_generated += 1
                    self.candidate_journal.append(candidate)
                    generated_candidates.append(candidate)
                    self._notify_candidate_subscribers(candidate)

            # Update telemetry
            self.scanner_health.update_state(
                ComponentOperationalState.RUNNING,
                f"Scanning active across {len(self.universe)} symbols",
                metrics={
                    "bars_scanned": self.bars_scanned,
                    "candidates_generated": self.candidates_generated,
                    "active_symbols": len(self.universe),
                },
            )
            self.strategy_health.update_state(
                ComponentOperationalState.RUNNING,
                f"{len(self.strategies)} deterministic strategies active",
                metrics={
                    "active_strategies": [s.name for s in self.strategies],
                    "decisions_evaluated": len(self.decisions_journal),
                },
            )

        return generated_candidates

    def _notify_candidate_subscribers(self, candidate: TradeCandidate):
        subscribers = list(self._candidate_subscribers)
        for sub in subscribers:
            try:
                sub(candidate)
            except Exception as e:
                logger.error(f"Candidate subscriber error: {e}")
