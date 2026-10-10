from datetime import datetime, timezone
from decimal import Decimal
from .models import MarketSnapshot, TechnicalSignalSet, PriceActionSignalSet, MarketRegimeAssessment, MarketMode

class MarketRegimeClassifier:
    def __init__(self, volatility_threshold: Decimal = Decimal('0.05'), min_volume: Decimal = Decimal('1000')):
        self.vol_threshold = volatility_threshold
        self.min_volume = min_volume
        
    def classify(self, snapshot: MarketSnapshot, tech: TechnicalSignalSet, pa: PriceActionSignalSet) -> MarketRegimeAssessment:
        evidence = []
        warnings = []
        
        if snapshot.quality_status != "OK" or snapshot.data_freshness_seconds > 60:
            return MarketRegimeAssessment(
                market_mode=MarketMode.DATA_UNAVAILABLE,
                confidence=1.0,
                evidence=["STALE_OR_INVALID_DATA"],
                warnings=["DATA_QUALITY_POOR"],
                assessment_timestamp=datetime.now(timezone.utc),
                freshness_status="STALE"
            )
            
        if tech.data_completeness < 0.5:
            return MarketRegimeAssessment(
                market_mode=MarketMode.UNCERTAIN,
                confidence=0.1,
                evidence=["INSUFFICIENT_HISTORY"],
                warnings=["TECH_DATA_INCOMPLETE"],
                assessment_timestamp=datetime.now(timezone.utc),
                freshness_status="OK"
            )
            
        price = snapshot.last_price
        
        # Volatility & Liquidity Checks
        if tech.atr and (tech.atr / price) > self.vol_threshold:
            return MarketRegimeAssessment(
                market_mode=MarketMode.HIGH_VOLATILITY,
                confidence=0.9,
                evidence=["ATR_EXCEEDS_THRESHOLD"],
                warnings=[],
                assessment_timestamp=datetime.now(timezone.utc),
                freshness_status="OK"
            )
            
        # Basic volume proxy
        last_vol = list(snapshot.volume_metrics.values())[0] if snapshot.volume_metrics else Decimal(0)
        if last_vol < self.min_volume:
            return MarketRegimeAssessment(
                market_mode=MarketMode.LOW_LIQUIDITY,
                confidence=0.9,
                evidence=["VOLUME_BELOW_MINIMUM"],
                warnings=[],
                assessment_timestamp=datetime.now(timezone.utc),
                freshness_status="OK"
            )
            
        is_bull = False
        is_bear = False
        
        if tech.trend_direction == 1 and pa.higher_highs and pa.higher_lows:
            if tech.vwap and price > tech.vwap:
                is_bull = True
                evidence.append("MA_TREND_UP_AND_PRICE_ABOVE_VWAP")
                
        if tech.trend_direction == -1 and pa.lower_highs and pa.lower_lows:
            if tech.vwap and price < tech.vwap:
                is_bear = True
                evidence.append("MA_TREND_DOWN_AND_PRICE_BELOW_VWAP")
                
        if is_bull and not is_bear:
            return MarketRegimeAssessment(MarketMode.BULLISH_TREND, 0.8, evidence, [], datetime.now(timezone.utc), "OK")
            
        if is_bear and not is_bull:
            return MarketRegimeAssessment(MarketMode.BEARISH_TREND, 0.8, evidence, [], datetime.now(timezone.utc), "OK")
            
        if tech.trend_direction == 0 and not pa.higher_highs and not pa.lower_lows:
            evidence.append("NO_CLEAR_TREND_STRUCTURE")
            return MarketRegimeAssessment(MarketMode.RANGE_BOUND, 0.7, evidence, [], datetime.now(timezone.utc), "OK")
            
        return MarketRegimeAssessment(MarketMode.UNCERTAIN, 0.5, ["MIXED_SIGNALS"], [], datetime.now(timezone.utc), "OK")
