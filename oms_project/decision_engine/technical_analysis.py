from typing import List, Optional
from decimal import Decimal
from .models import MarketBar, TechnicalSignalSet

def compute_sma(prices: List[Decimal], period: int) -> Optional[Decimal]:
    if len(prices) < period or period <= 0:
        return None
    return sum(prices[-period:]) / Decimal(period)

def compute_ema(prices: List[Decimal], period: int) -> Optional[Decimal]:
    if len(prices) < period or period <= 0:
        return None
    multiplier = Decimal(2) / Decimal(period + 1)
    ema = sum(prices[:period]) / Decimal(period)
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    return ema

def compute_rsi(prices: List[Decimal], period: int = 14) -> Optional[Decimal]:
    if len(prices) <= period:
        return None
    gains = []
    losses = []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change)
            losses.append(Decimal(0))
        else:
            gains.append(Decimal(0))
            losses.append(abs(change))
    
    avg_gain = sum(gains[:period]) / Decimal(period)
    avg_loss = sum(losses[:period]) / Decimal(period)
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * Decimal(period - 1) + gains[i]) / Decimal(period)
        avg_loss = (avg_loss * Decimal(period - 1) + losses[i]) / Decimal(period)
        
    if avg_loss == Decimal(0):
        return Decimal(100)
        
    rs = avg_gain / avg_loss
    return Decimal(100) - (Decimal(100) / (Decimal(1) + rs))

def compute_atr(bars: List[MarketBar], period: int = 14) -> Optional[Decimal]:
    if len(bars) <= period:
        return None
    
    true_ranges = []
    for i in range(1, len(bars)):
        high = bars[i].high
        low = bars[i].low
        prev_close = bars[i-1].close
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)
        
    atr = sum(true_ranges[:period]) / Decimal(period)
    for i in range(period, len(true_ranges)):
        atr = (atr * Decimal(period - 1) + true_ranges[i]) / Decimal(period)
    return atr

def compute_vwap(bars: List[MarketBar]) -> Optional[Decimal]:
    if not bars:
        return None
    cum_pv = Decimal(0)
    cum_vol = Decimal(0)
    for bar in bars:
        typical_price = (bar.high + bar.low + bar.close) / Decimal(3)
        cum_pv += typical_price * bar.volume
        cum_vol += bar.volume
    if cum_vol == Decimal(0):
        return None
    return cum_pv / cum_vol

def compute_technical_signals(bars: List[MarketBar]) -> TechnicalSignalSet:
    if not bars:
        return TechnicalSignalSet(
            trend_direction=0, fast_ma=None, slow_ma=None, vwap=None, rsi=None,
            macd_line=None, macd_signal=None, macd_histogram=None, atr=None,
            bollinger_upper=None, bollinger_lower=None, relative_volume=None,
            indicator_warnings=["NO_DATA"], data_completeness=0.0
        )
        
    closes = [b.close for b in bars]
    fast_ma = compute_sma(closes, 9)
    slow_ma = compute_sma(closes, 21)
    
    trend = 0
    if fast_ma and slow_ma:
        if fast_ma > slow_ma:
            trend = 1
        elif fast_ma < slow_ma:
            trend = -1
            
    vwap = compute_vwap(bars[-390:]) if len(bars) > 0 else None # intraday approximation
    rsi = compute_rsi(closes)
    atr = compute_atr(bars)
    
    warnings = []
    if len(bars) < 21:
        warnings.append("INSUFFICIENT_BARS_FOR_MA21")
        
    return TechnicalSignalSet(
        trend_direction=trend,
        fast_ma=fast_ma,
        slow_ma=slow_ma,
        vwap=vwap,
        rsi=rsi,
        macd_line=None,
        macd_signal=None,
        macd_histogram=None,
        atr=atr,
        bollinger_upper=None,
        bollinger_lower=None,
        relative_volume=None, # To implement
        indicator_warnings=warnings,
        data_completeness=min(1.0, len(bars) / 50.0)
    )
