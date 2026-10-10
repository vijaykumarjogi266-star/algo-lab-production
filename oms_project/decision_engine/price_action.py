from typing import List
from decimal import Decimal
from .models import MarketBar, PriceActionSignalSet

def evaluate_price_action(bars: List[MarketBar]) -> PriceActionSignalSet:
    if len(bars) < 5:
        return PriceActionSignalSet(
            higher_highs=False, higher_lows=False,
            lower_highs=False, lower_lows=False,
            breakout_status=False, failed_breakout_status=False,
            support_proximity=False, resistance_proximity=False,
            range_expansion=False, volume_confirmation=False,
            confidence=0.0, rationale=["INSUFFICIENT_DATA"]
        )
        
    recent_bars = bars[-5:]
    hh = all(recent_bars[i].high > recent_bars[i-1].high for i in range(1, len(recent_bars)))
    hl = all(recent_bars[i].low > recent_bars[i-1].low for i in range(1, len(recent_bars)))
    lh = all(recent_bars[i].high < recent_bars[i-1].high for i in range(1, len(recent_bars)))
    ll = all(recent_bars[i].low < recent_bars[i-1].low for i in range(1, len(recent_bars)))
    
    rationale = []
    confidence = 0.5
    
    if hh and hl:
        rationale.append("BULLISH_STRUCTURE_5_BARS")
        confidence += 0.3
    elif lh and ll:
        rationale.append("BEARISH_STRUCTURE_5_BARS")
        confidence += 0.3
    else:
        rationale.append("MIXED_STRUCTURE")
        
    avg_vol = sum(b.volume for b in bars) / Decimal(len(bars))
    last_vol = bars[-1].volume
    vol_conf = last_vol > avg_vol
    
    if vol_conf:
        rationale.append("VOLUME_CONFIRMATION")
        confidence += 0.1
        
    return PriceActionSignalSet(
        higher_highs=hh,
        higher_lows=hl,
        lower_highs=lh,
        lower_lows=ll,
        breakout_status=False,
        failed_breakout_status=False,
        support_proximity=False,
        resistance_proximity=False,
        range_expansion=False,
        volume_confirmation=vol_conf,
        confidence=min(1.0, confidence),
        rationale=rationale
    )
