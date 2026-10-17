#!/usr/bin/env python3
"""
Algo Lab — TradingView Technical Indicators Fetcher & Validator
Tests and extracts 90+ real-time technical indicators directly from TradingView
for NSE/BSE symbols across multiple timeframes without requiring login.
"""

import sys
import argparse
from typing import Dict, Any

try:
    from tradingview_ta import TA_Handler, Interval, Exchange
except ImportError:
    print("Error: tradingview-ta is required. Install via: pip install tradingview-ta")
    sys.exit(1)

INTERVAL_MAP = {
    "1m": Interval.INTERVAL_1_MINUTE,
    "5m": Interval.INTERVAL_5_MINUTES,
    "15m": Interval.INTERVAL_15_MINUTES,
    "30m": Interval.INTERVAL_30_MINUTES,
    "1h": Interval.INTERVAL_1_HOUR,
    "2h": Interval.INTERVAL_2_HOURS,
    "4h": Interval.INTERVAL_4_HOURS,
    "1d": Interval.INTERVAL_1_DAY,
    "1W": Interval.INTERVAL_1_WEEK,
    "1M": Interval.INTERVAL_1_MONTH,
}


def fetch_tradingview_indicators(symbol: str, interval_str: str = "15m", exchange: str = "NSE") -> Dict[str, Any]:
    """Fetches full technical analysis indicators payload from TradingView."""
    interval = INTERVAL_MAP.get(interval_str, Interval.INTERVAL_15_MINUTES)
    
    # Strip any .NS suffix if user provided it
    clean_symbol = symbol.replace(".NS", "").replace(".BO", "").strip().upper()
    
    handler = TA_Handler(
        symbol=clean_symbol,
        screener="india",
        exchange=exchange,
        interval=interval,
    )
    
    analysis = handler.get_analysis()
    return {
        "symbol": clean_symbol,
        "exchange": exchange,
        "interval": interval_str,
        "summary": analysis.summary,
        "oscillators": analysis.oscillators,
        "moving_averages": analysis.moving_averages,
        "indicators": analysis.indicators,
    }


def display_report(data: Dict[str, Any]):
    """Renders a structured terminal report of TradingView indicators."""
    symbol = data["symbol"]
    interval = data["interval"]
    summary = data["summary"]
    ind = data["indicators"]
    
    print("\n" + "=" * 76)
    print(f"   TRADINGVIEW LIVE INDICATORS REPORT: {symbol} (NSE) [{interval}]")
    print("=" * 76)
    
    close_price = ind.get("close", 0.0)
    change = ind.get("change", 0.0)
    vol = ind.get("volume", 0)
    print(f"Price: INR {close_price:,.2f} | Change: {change:+.2f}% | Volume: {vol:,.0f}")
    print(f"Overall Rating: {summary.get('RECOMMENDATION', 'N/A')} "
          f"(Buy: {summary.get('BUY', 0)} | Sell: {summary.get('SELL', 0)} | Neutral: {summary.get('NEUTRAL', 0)})")
    print("-" * 76)

    print("\n[1] KEY MOMENTUM & TREND OSCILLATORS:")
    print(f"  • RSI (14):               {ind.get('RSI', 0.0):>8.2f}  | Action: {data['oscillators'].get('COMPUTE', {}).get('RSI', 'N/A')}")
    print(f"  • Stochastic %K / %D:     {ind.get('Stoch.K', 0.0):>8.2f} / {ind.get('Stoch.D', 0.0):<6.2f} | Action: {data['oscillators'].get('COMPUTE', {}).get('STOCH.K', 'N/A')}")
    print(f"  • MACD (Level / Signal):  {ind.get('MACD.macd', 0.0):>8.2f} / {ind.get('MACD.signal', 0.0):<6.2f} | Action: {data['oscillators'].get('COMPUTE', {}).get('MACD', 'N/A')}")
    print(f"  • ADX (Trend Strength):   {ind.get('ADX', 0.0):>8.2f}  | Action: {data['oscillators'].get('COMPUTE', {}).get('ADX', 'N/A')}")
    print(f"  • CCI (20):               {ind.get('CCI20', 0.0):>8.2f}  | Action: {data['oscillators'].get('COMPUTE', {}).get('CCI', 'N/A')}")
    print(f"  • Awesome Oscillator:     {ind.get('AO', 0.0):>8.2f}  | Action: {data['oscillators'].get('COMPUTE', {}).get('AO', 'N/A')}")

    print("\n[2] MOVING AVERAGES HIERARCHY:")
    print(f"  • EMA 20:   INR {ind.get('EMA20', 0.0):>9.2f}  | Action: {data['moving_averages'].get('COMPUTE', {}).get('EMA20', 'N/A')}")
    print(f"  • SMA 20:   INR {ind.get('SMA20', 0.0):>9.2f}  | Action: {data['moving_averages'].get('COMPUTE', {}).get('SMA20', 'N/A')}")
    print(f"  • EMA 50:   INR {ind.get('EMA50', 0.0):>9.2f}  | Action: {data['moving_averages'].get('COMPUTE', {}).get('EMA50', 'N/A')}")
    print(f"  • EMA 200:  INR {ind.get('EMA200', 0.0):>9.2f}  | Action: {data['moving_averages'].get('COMPUTE', {}).get('EMA200', 'N/A')}")
    print(f"  • VWMA:     INR {ind.get('VWMA', 0.0):>9.2f}  | Action: {data['moving_averages'].get('COMPUTE', {}).get('VWMA', 'N/A')}")
    print(f"  • Hull MA:  INR {ind.get('HullMA9', 0.0):>9.2f}  | Action: {data['moving_averages'].get('COMPUTE', {}).get('HullMA', 'N/A')}")

    print("\n[3] VOLATILITY & BANDS:")
    bb_upper = ind.get("BB.upper", 0.0)
    bb_lower = ind.get("BB.lower", 0.0)
    print(f"  • Bollinger Upper:        INR {bb_upper:,.2f}")
    print(f"  • Bollinger Lower:        INR {bb_lower:,.2f}")
    print(f"  • Parabolic SAR:          INR {ind.get('P.SAR', 0.0):,.2f}")

    print("\n[4] PIVOT LEVELS (CLASSIC & CAMARILLA):")
    print(f"  • Classic Pivot:          INR {ind.get('Pivot.M.Classic.Middle', 0.0):,.2f} (R1: {ind.get('Pivot.M.Classic.R1', 0.0):,.2f} | S1: {ind.get('Pivot.M.Classic.S1', 0.0):,.2f})")
    print(f"  • Camarilla Pivot:        INR {ind.get('Pivot.M.Camarilla.Middle', 0.0):,.2f} (R3: {ind.get('Pivot.M.Camarilla.R3', 0.0):,.2f} | S3: {ind.get('Pivot.M.Camarilla.S3', 0.0):,.2f})")
    print(f"  • Fibonacci Pivot:        INR {ind.get('Pivot.M.Fibonacci.Middle', 0.0):,.2f} (R1: {ind.get('Pivot.M.Fibonacci.R1', 0.0):,.2f} | S1: {ind.get('Pivot.M.Fibonacci.S1', 0.0):,.2f})")
    print("=" * 76 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Algo Lab TradingView Indicator Fetcher")
    parser.add_argument("--symbol", type=str, default="RELIANCE", help="Symbol (e.g. RELIANCE, TCS, INFY)")
    parser.add_argument("--interval", type=str, default="15m", choices=list(INTERVAL_MAP.keys()), help="Timeframe")
    parser.add_argument("--exchange", type=str, default="NSE", help="Exchange (default: NSE)")
    args = parser.parse_args()

    data = fetch_tradingview_indicators(args.symbol, args.interval, args.exchange)
    display_report(data)


if __name__ == "__main__":
    main()
