"""
Algo Lab — TTM Volatility Squeeze Breakout Strategy.

Identifies volatility compression when Bollinger Bands (20, 2.0σ) contract inside
Keltner Channels (20, 1.5 ATR). When the squeeze fires (bands expand outside channels)
with relative volume surge (>= 1.15x), triggers directional trade in the momentum direction.
Adheres to Principle 1 (Never force a trade) and Principle 2 (WAIT is a valid decision).
"""

from typing import Any, Dict, List, Optional
import numpy as np
from datetime import datetime, timezone

from data.schemas.contracts import OHLCVBar
from quant.strategies.base import BaseStrategy, SignalType, StrategyDecision
from services.backtest_engine.trade_candidate import CandidateAction, TradeCandidate


class TTMSqueezeBreakout(BaseStrategy):
    """TTM Volatility Squeeze Breakout Strategy."""

    def __init__(
        self,
        strategy_id: str = "STRAT_TTM_SQUEEZE",
        version: str = "1.0.0",
        bb_period: int = 20,
        bb_std: float = 2.0,
        kc_atr_mult: float = 1.5,
        volume_multiplier: float = 1.15,
        stop_loss_atr: float = 1.5,
        target_atr: float = 3.0,
        parameters: Optional[Dict[str, Any]] = None,
    ):
        params = parameters or {}
        p = int(params.get("bb_period", bb_period))
        std = float(params.get("bb_std", bb_std))
        kc_mult = float(params.get("kc_atr_mult", kc_atr_mult))
        vol_mult = float(params.get("volume_multiplier", volume_multiplier))
        sl_atr = float(params.get("stop_loss_atr", stop_loss_atr))
        tp_atr = float(params.get("target_atr", target_atr))

        super().__init__(
            strategy_id=strategy_id,
            name="TTM Volatility Squeeze",
            version=version,
            parameters={
                "bb_period": p,
                "bb_std": std,
                "kc_atr_mult": kc_mult,
                "volume_multiplier": vol_mult,
                "stop_loss_atr": sl_atr,
                "target_atr": tp_atr,
            },
        )
        self.bb_period = p
        self.bb_std = std
        self.kc_atr_mult = kc_mult
        self.volume_multiplier = vol_mult
        self.stop_loss_atr = sl_atr
        self.target_atr = tp_atr

    def evaluate_data(
        self,
        symbol: str,
        data: Dict[str, Any],
        parameters: Optional[Dict[str, Any]] = None,
    ) -> StrategyDecision:
        """Evaluate point-in-time market data dictionary."""
        params = parameters or self.parameters
        sl_atr = float(params.get("stop_loss_atr", self.stop_loss_atr))
        tp_atr = float(params.get("target_atr", self.target_atr))
        period = int(params.get("bb_period", self.bb_period))

        price = float(data.get("price", 0.0))
        atr = float(data.get("atr", price * 0.015))
        ts = data.get("bar_timestamp") or datetime.now(timezone.utc)
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                ts = datetime.now(timezone.utc)

        closes = data.get("closes", [])
        highs = data.get("highs", [])
        lows = data.get("lows", [])
        volumes = data.get("volumes", [])

        if len(closes) < period + 5:
            return self.default_wait(symbol, ts, "Insufficient history for TTM Squeeze")

        c_arr = np.array(closes, dtype=float)
        v_arr = np.array(volumes, dtype=float) if volumes else np.ones(len(closes))

        # Bollinger Bands
        sma20 = float(np.mean(c_arr[-period:]))
        std20 = float(np.std(c_arr[-period:]))
        bb_upper = sma20 + (self.bb_std * std20)
        bb_lower = sma20 - (self.bb_std * std20)

        # Keltner Channels
        kc_upper = sma20 + (self.kc_atr_mult * atr)
        kc_lower = sma20 - (self.kc_atr_mult * atr)

        # Previous bar squeeze state
        prev_sma20 = float(np.mean(c_arr[-period-1:-1]))
        prev_std20 = float(np.std(c_arr[-period-1:-1]))
        prev_bb_upper = prev_sma20 + (self.bb_std * prev_std20)
        prev_bb_lower = prev_sma20 - (self.bb_std * prev_std20)
        prev_kc_upper = prev_sma20 + (self.kc_atr_mult * atr)
        prev_kc_lower = prev_sma20 - (self.kc_atr_mult * atr)

        was_in_squeeze = (prev_bb_lower > prev_kc_lower) and (prev_bb_upper < prev_kc_upper)
        fired_breakout = (bb_lower <= kc_lower) or (bb_upper >= kc_upper)

        # Volume surge
        vol_ma = float(np.mean(v_arr[-period:])) if len(v_arr) >= period else 1.0
        curr_vol = float(v_arr[-1]) if len(v_arr) > 0 else 1.0
        vol_surge = curr_vol >= (vol_ma * self.volume_multiplier) if vol_ma > 0 else True

        # Directional Momentum
        mom = price - sma20

        if was_in_squeeze and fired_breakout and vol_surge:
            if mom > 0 and price > sma20:
                stop_loss = round(price - (sl_atr * atr), 2)
                target = round(price + (tp_atr * atr), 2)
                return StrategyDecision(
                    symbol=symbol,
                    decision_timestamp=ts,
                    signal=SignalType.BUY,
                    confidence=0.80,
                    reason=f"TTM Volatility Squeeze Breakout: BB expanded outside KC with volume surge ({curr_vol:.0f} >= {vol_ma*self.volume_multiplier:.0f})",
                    evidence={"sma20": sma20, "bb_upper": bb_upper, "kc_upper": kc_upper, "atr": atr, "momentum": mom},
                    stop_loss=stop_loss,
                    target_price=target,
                )
            elif mom < 0 and price < sma20:
                stop_loss = round(price + (sl_atr * atr), 2)
                target = round(price - (tp_atr * atr), 2)
                return StrategyDecision(
                    symbol=symbol,
                    decision_timestamp=ts,
                    signal=SignalType.SELL,
                    confidence=0.80,
                    reason=f"TTM Volatility Squeeze Breakdown: BB expanded below KC with volume surge",
                    evidence={"sma20": sma20, "bb_lower": bb_lower, "kc_lower": kc_lower, "atr": atr, "momentum": mom},
                    stop_loss=stop_loss,
                    target_price=target,
                )

        return self.default_wait(
            symbol=symbol,
            timestamp=ts,
            reason=f"No TTM Squeeze breakout (In Squeeze: {was_in_squeeze}, Fired: {fired_breakout})",
        )

    def evaluate(self, current_bar: OHLCVBar, history: List[OHLCVBar], data_quality=None) -> StrategyDecision:
        bars = (history or []) + [current_bar]
        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        volumes = [b.volume for b in bars]
        data = {
            "price": current_bar.close,
            "closes": closes,
            "highs": highs,
            "lows": lows,
            "volumes": volumes,
            "bar_timestamp": current_bar.market_timestamp,
            "atr": float(getattr(current_bar, "atr", current_bar.close * 0.015)),
        }
        return self.evaluate_data(current_bar.symbol, data)
