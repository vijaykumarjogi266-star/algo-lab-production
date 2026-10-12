"""
Algo Lab Deep Multi-Interval Scanner & Market Regime Evaluation Engine.
Evaluates trend, volatility, and breakout setups across the NIFTY 100 / F&O universe
for 5m, 15m, 1h, and daily (1d) intervals.
"""

from datetime import datetime, timezone
from enum import Enum
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
import yfinance as yf

from services.scanner.nifty100_universe import (
    Nifty100UniverseManager,
    AUTHORITATIVE_NIFTY_100_CONSTITUENTS,
)

logger = logging.getLogger("DeepMultiIntervalScanner")


class MarketRegimeType(str, Enum):
    BULL_TREND_STRONG = "BULL_TREND_STRONG"
    BEAR_TREND_STRONG = "BEAR_TREND_STRONG"
    HIGH_VOLATILITY_EXPANSION = "HIGH_VOLATILITY_EXPANSION"
    LOW_VOLATILITY_SQUEEZE = "LOW_VOLATILITY_SQUEEZE"
    RANGE_BOUND_CHOP = "RANGE_BOUND_CHOP"


class SetupType(str, Enum):
    DONCHIAN_BREAKOUT = "DONCHIAN_BREAKOUT"
    ORB_BREAKOUT = "ORB_BREAKOUT"
    VOLATILITY_EXPANSION = "VOLATILITY_EXPANSION"
    TREND_PULLBACK = "TREND_PULLBACK"
    OVERSOLD_REVERSION = "OVERSOLD_REVERSION"
    BULLISH_MOMENTUM = "BULLISH_MOMENTUM"


def compute_interval_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Computes technical trend, volatility, and breakout indicators on OHLCV dataframe."""
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"] if "Volume" in df.columns else pd.Series(100000, index=df.index)

    # 1. Moving Averages & Trend
    df["EMA_20"] = close.ewm(span=20, adjust=False).mean()
    df["SMA_50"] = close.rolling(window=min(len(close), 50)).mean()
    df["SMA_200"] = close.rolling(window=min(len(close), 200)).mean()

    # 2. RSI 14
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-9)
    df["RSI_14"] = 100 - (100 / (1 + rs))

    # 3. ATR 14
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["TR"] = tr
    df["ATR_14"] = tr.rolling(window=14).mean().fillna(close * 0.015)
    df["ATR_PCT"] = (df["ATR_14"] / close) * 100.0

    # 4. Bollinger Bands (20, 2) & Bandwidth
    rolling_20_mean = close.rolling(window=20).mean()
    rolling_20_std = close.rolling(window=20).std()
    df["BB_UPPER"] = rolling_20_mean + (2 * rolling_20_std)
    df["BB_LOWER"] = rolling_20_mean - (2 * rolling_20_std)
    df["BB_MIDDLE"] = rolling_20_mean
    df["BB_WIDTH"] = ((df["BB_UPPER"] - df["BB_LOWER"]) / (rolling_20_mean + 1e-9)) * 100.0
    df["BB_PERCENT"] = (close - df["BB_LOWER"]) / ((df["BB_UPPER"] - df["BB_LOWER"]) + 1e-9)

    # 5. Volume & Relative Volume
    df["VOL_SMA_20"] = volume.rolling(window=20).mean().fillna(volume)
    df["RVOL"] = volume / (df["VOL_SMA_20"] + 1e-9)

    # 6. Donchian 20-Period High & Low
    df["DONCHIAN_HIGH_20"] = high.shift(1).rolling(window=20).max()
    df["DONCHIAN_LOW_20"] = low.shift(1).rolling(window=20).min()

    # 7. ADX 14 (Trend Strength)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_di = 100 * (pd.Series(plus_dm, index=df.index).rolling(14).mean() / (df["ATR_14"] + 1e-9))
    minus_di = 100 * (pd.Series(minus_dm, index=df.index).rolling(14).mean() / (df["ATR_14"] + 1e-9))
    dx = 100 * (plus_di - minus_di).abs() / ((plus_di + minus_di) + 1e-9)
    df["ADX_14"] = dx.rolling(14).mean().fillna(20.0)

    return df


class DeepMultiIntervalScanner:
    """
    Executes multi-interval technical scanning and market regime evaluation
    across the NIFTY 100 / F&O universe.
    """

    def __init__(
        self,
        universe_symbols: Optional[List[str]] = None,
        sector_map: Optional[Dict[str, str]] = None,
    ):
        mgr = Nifty100UniverseManager()
        self.universe_symbols = universe_symbols or mgr.get_symbols()
        self.sector_map = sector_map or mgr.get_sector_map()

        self.interval_history_map = {
            "5m": ("5d", "5m"),
            "15m": ("5d", "15m"),
            "1h": ("30d", "1h"),
            "1d": ("90d", "1d"),
        }

    def evaluate_symbol_interval(
        self,
        symbol: str,
        df: pd.DataFrame,
        interval: str,
    ) -> Optional[Dict[str, Any]]:
        """Evaluates setups and regime metrics for a single symbol at a given interval."""
        if df.empty or len(df) < 20:
            return None

        df_calc = compute_interval_indicators(df)
        last_row = df_calc.iloc[-1]
        prev_row = df_calc.iloc[-2] if len(df_calc) >= 2 else last_row

        close = float(last_row["Close"])
        high = float(last_row["High"])
        low = float(last_row["Low"])
        ema20 = float(last_row["EMA_20"])
        sma50 = float(last_row["SMA_50"])
        sma200 = float(last_row["SMA_200"])
        rsi = float(last_row["RSI_14"])
        atr = float(last_row["ATR_14"])
        atr_pct = float(last_row["ATR_PCT"])
        bb_width = float(last_row["BB_WIDTH"])
        bb_upper = float(last_row["BB_UPPER"])
        bb_lower = float(last_row["BB_LOWER"])
        rvol = float(last_row["RVOL"])
        adx = float(last_row["ADX_14"])
        dh20 = float(last_row["DONCHIAN_HIGH_20"])
        dl20 = float(last_row["DONCHIAN_LOW_20"])

        # Trend Evaluation
        is_strong_uptrend = close > ema20 and ema20 > sma50 and adx > 25.0
        is_bullish = close > ema20 and ema20 > sma50
        is_bearish = close < ema20 and ema20 < sma50

        # Volatility Squeeze Evaluation
        # BB Width in lowest quartile of last 20 periods
        recent_bb_widths = df_calc["BB_WIDTH"].tail(20)
        is_in_squeeze = bb_width <= recent_bb_widths.quantile(0.25)
        is_vol_expanding = bb_width > float(prev_row["BB_WIDTH"]) * 1.15

        # Breakout Setup Classification
        setup = None
        score = 0.0

        if close >= dh20 and rvol >= 1.20:
            setup = SetupType.DONCHIAN_BREAKOUT.value
            score = 9.2 + (0.5 if rvol >= 1.5 else 0.0)
        elif is_vol_expanding and close >= bb_upper and rvol >= 1.15:
            setup = SetupType.VOLATILITY_EXPANSION.value
            score = 8.8 + (0.4 if is_strong_uptrend else 0.0)
        elif interval in ["5m", "15m"] and high >= float(df_calc["High"].tail(10).max()) and rvol >= 1.30:
            setup = SetupType.ORB_BREAKOUT.value
            score = 8.5
        elif is_bullish and 42.0 <= rsi <= 60.0 and (low <= ema20 * 1.005 and close >= ema20):
            setup = SetupType.TREND_PULLBACK.value
            score = 8.0 + (0.5 if rvol >= 1.1 else 0.0)
        elif rsi < 32.0 and close > low * 1.002:
            setup = SetupType.OVERSOLD_REVERSION.value
            score = 7.5 + (0.5 if rvol >= 1.2 else 0.0)
        elif is_strong_uptrend:
            setup = SetupType.BULLISH_MOMENTUM.value
            score = 7.2

        if not setup:
            return None

        # Risk parameters
        sl_dist = max(2.0 * atr, close * 0.012)
        stop_loss = round(close - sl_dist, 2)
        take_profit = round(close + (3.0 * sl_dist), 2)
        allocated_capital = 30000.0 if interval == "1d" else 25000.0
        suggested_qty = max(1, int(allocated_capital / close))

        return {
            "symbol": symbol,
            "sector": self.sector_map.get(symbol, "GENERAL"),
            "interval": interval,
            "setup": setup,
            "score": round(score, 1),
            "close": round(close, 2),
            "trend": "STRONG_BULLISH" if is_strong_uptrend else ("BULLISH" if is_bullish else ("BEARISH" if is_bearish else "NEUTRAL")),
            "rsi_14": round(rsi, 1),
            "atr_14": round(atr, 2),
            "atr_pct": round(atr_pct, 2),
            "adx_14": round(adx, 1),
            "rel_volume": round(rvol, 2),
            "bollinger_bandwidth": round(bb_width, 2),
            "in_squeeze": bool(is_in_squeeze),
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "suggested_qty": suggested_qty,
            "allocated_capital": round(suggested_qty * close, 2),
        }

    def evaluate_market_regime(
        self,
        interval_data: Dict[str, pd.DataFrame],
        interval: str,
    ) -> Dict[str, Any]:
        """Evaluates aggregate market regime across all symbols for the specified interval."""
        total_symbols = len(interval_data)
        if total_symbols == 0:
            return {
                "regime": MarketRegimeType.RANGE_BOUND_CHOP.value,
                "breadth_pct_above_ema20": 50.0,
                "breadth_pct_above_sma50": 50.0,
                "advance_decline_ratio": 1.0,
                "avg_adx": 20.0,
                "avg_atr_pct": 1.5,
                "pct_in_squeeze": 15.0,
            }

        above_ema20 = 0
        above_sma50 = 0
        advances = 0
        declines = 0
        adx_list = []
        atr_pct_list = []
        squeeze_count = 0

        for sym, df in interval_data.items():
            if df.empty or len(df) < 20:
                continue
            df_calc = compute_interval_indicators(df)
            last_row = df_calc.iloc[-1]
            c = float(last_row["Close"])
            ema = float(last_row["EMA_20"])
            sma = float(last_row["SMA_50"])
            adx = float(last_row["ADX_14"])
            atr_pct = float(last_row["ATR_PCT"])
            bbw = float(last_row["BB_WIDTH"])

            if c > ema:
                above_ema20 += 1
            if c > sma:
                above_sma50 += 1

            prev_c = float(df_calc.iloc[-2]["Close"]) if len(df_calc) >= 2 else c
            if c > prev_c:
                advances += 1
            elif c < prev_c:
                declines += 1

            adx_list.append(adx)
            atr_pct_list.append(atr_pct)

            recent_bbw = df_calc["BB_WIDTH"].tail(20)
            if bbw <= recent_bbw.quantile(0.25):
                squeeze_count += 1

        valid_count = max(1, len(adx_list))
        pct_above_ema20 = round((above_ema20 / valid_count) * 100.0, 1)
        pct_above_sma50 = round((above_sma50 / valid_count) * 100.0, 1)
        ad_ratio = round(advances / max(1, declines), 2)
        avg_adx = round(float(np.mean(adx_list)), 1)
        avg_atr_pct = round(float(np.mean(atr_pct_list)), 2)
        pct_in_squeeze = round((squeeze_count / valid_count) * 100.0, 1)

        # Macro Classification
        if pct_above_ema20 >= 60.0 and avg_adx >= 24.0 and ad_ratio >= 1.3:
            regime = MarketRegimeType.BULL_TREND_STRONG.value
        elif pct_above_ema20 <= 40.0 and avg_adx >= 24.0 and ad_ratio <= 0.7:
            regime = MarketRegimeType.BEAR_TREND_STRONG.value
        elif avg_atr_pct >= 2.2:
            regime = MarketRegimeType.HIGH_VOLATILITY_EXPANSION.value
        elif pct_in_squeeze >= 35.0:
            regime = MarketRegimeType.LOW_VOLATILITY_SQUEEZE.value
        else:
            regime = MarketRegimeType.RANGE_BOUND_CHOP.value

        return {
            "interval": interval,
            "regime": regime,
            "valid_symbols": valid_count,
            "breadth_pct_above_ema20": pct_above_ema20,
            "breadth_pct_above_sma50": pct_above_sma50,
            "advance_decline_ratio": ad_ratio,
            "avg_adx": avg_adx,
            "avg_atr_pct": avg_atr_pct,
            "pct_in_squeeze": pct_in_squeeze,
        }

    def scan_universe(
        self,
        intervals: Optional[List[str]] = None,
        symbols_limit: Optional[int] = None,
        top_n: int = 10,
    ) -> Dict[str, Any]:
        """
        Executes end-to-end deep multi-interval scanning and regime evaluation.
        """
        intervals = intervals or ["5m", "15m", "1h", "1d"]
        symbols = self.universe_symbols[:symbols_limit] if symbols_limit else self.universe_symbols

        logger.info(f"Scanning {len(symbols)} symbols across intervals: {intervals}")

        all_interval_setups = {}
        all_interval_regimes = {}
        confluence_tracker: Dict[str, List[str]] = {}

        for interval in intervals:
            period, yf_interval = self.interval_history_map.get(interval, ("30d", interval))
            tickers_str = " ".join([f"{s}.NS" for s in symbols])
            
            try:
                data = yf.download(
                    tickers_str,
                    period=period,
                    interval=yf_interval,
                    group_by="ticker",
                    progress=False,
                )
            except Exception as e:
                logger.error(f"Error downloading data for {interval}: {e}")
                data = pd.DataFrame()

            symbol_dfs = {}
            if not data.empty:
                if len(symbols) == 1:
                    symbol_dfs[symbols[0]] = data.dropna()
                else:
                    is_multi = isinstance(data.columns, pd.MultiIndex)
                    top_levels = set(data.columns.get_level_values(0)) if is_multi else set(data.columns)
                    for sym in symbols:
                        ticker_key = f"{sym}.NS"
                        if ticker_key in top_levels:
                            try:
                                df_sym = data[ticker_key].dropna()
                                if len(df_sym) >= 20:
                                    symbol_dfs[sym] = df_sym
                            except Exception:
                                continue

            # Evaluate market regime for interval
            regime_report = self.evaluate_market_regime(symbol_dfs, interval)
            all_interval_regimes[interval] = regime_report

            # Evaluate setups for each symbol
            candidates = []
            for sym, df_sym in symbol_dfs.items():
                cand = self.evaluate_symbol_interval(sym, df_sym, interval)
                if cand:
                    candidates.append(cand)
                    confluence_tracker.setdefault(sym, []).append(f"{interval}:{cand['setup']}")

            candidates.sort(key=lambda x: x["score"], reverse=True)
            all_interval_setups[interval] = candidates

        # Multi-timeframe Confluence (present in >= 2 intervals)
        confluence_symbols = {
            sym: setups
            for sym, setups in confluence_tracker.items()
            if len(setups) >= 2
        }

        return {
            "scan_timestamp": datetime.now(timezone.utc).isoformat(),
            "universe_size": len(symbols),
            "intervals_scanned": intervals,
            "regimes_by_interval": all_interval_regimes,
            "confluence_symbols": confluence_symbols,
            "top_setups_by_interval": {
                k: v[:top_n] for k, v in all_interval_setups.items()
            },
        }
