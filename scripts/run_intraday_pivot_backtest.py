#!/usr/bin/env python3
"""
Intraday (MIS) Pivot Point Breakout Strategy Backtest
- Timeframe: 5-minute (5m) over the max available yfinance history (~60 days)
- Universe: Nifty 50
- Entry: Close > R1 AND Volume > 1.5 * Vol_SMA_20 between 09:45 and 13:30 IST.
- Exit: Take Profit at R2, Stop Loss at breakout candle Low, Hard Square-off at 15:15 IST.
- Friction: MIS Statutory Cost Model.
"""

import sys
import os
from pathlib import Path
from decimal import Decimal
import pandas as pd
import yfinance as yf
from datetime import time, timedelta
import pytz

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from services.backtest_engine.statutory_cost_model import (
    IndianStatutoryCostModel,
    OrderLeg,
    ProductType,
)
from services.scanner.universe_manager import Nifty50UniverseManager


def calculate_daily_pivots(df: pd.DataFrame) -> pd.DataFrame:
    """Calculates Previous Day High, Low, Close, and Pivot Points."""
    # Ensure index is datetime and localized
    df['Date'] = pd.to_datetime(df['Datetime']).dt.date
    
    # Group by date to get daily HLC
    daily = df.groupby('Date').agg(
        day_high=('High', 'max'),
        day_low=('Low', 'min'),
        day_close=('Close', 'last')
    ).reset_index()
    
    daily['prev_high'] = daily['day_high'].shift(1)
    daily['prev_low'] = daily['day_low'].shift(1)
    daily['prev_close'] = daily['day_close'].shift(1)
    
    # P = (H + L + C) / 3
    daily['P'] = (daily['prev_high'] + daily['prev_low'] + daily['prev_close']) / 3
    # R1 = 2P - L
    daily['R1'] = 2 * daily['P'] - daily['prev_low']
    # R2 = P + (H - L)
    daily['R2'] = daily['P'] + (daily['prev_high'] - daily['prev_low'])
    # S1 = 2P - H
    daily['S1'] = 2 * daily['P'] - daily['prev_high']
    # S2 = P - (H - L)
    daily['S2'] = daily['P'] - (daily['prev_high'] - daily['prev_low'])
    
    return pd.merge(df, daily[['Date', 'P', 'R1', 'R2', 'S1', 'S2', 'prev_high', 'prev_low']], on='Date', how='left')


def run_intraday_backtest():
    universe_mgr = Nifty50UniverseManager()
    symbols = universe_mgr.get_symbols()
    
    print("=" * 80)
    print("🚀 RUNNING INTRADAY PIVOT POINT BREAKOUT BACKTEST (MIS)")
    print("=" * 80)
    print(f"Universe: Nifty 50 ({len(symbols)} symbols)")
    print(f"Timeframe: 5m (Last 60 Days - yfinance limit)")
    print("Fetching data...")

    initial_capital = 100000.0
    risk_per_trade_pct = 0.010
    
    trades = []
    
    for sym in symbols:
        ticker = f"{sym}.NS"
        # yfinance limits 5m data to last 60 days max. 
        df = yf.download(ticker, period="60d", interval="5m", progress=False)
        if df.empty:
            continue
            
        df = df.reset_index()
        # Flatten MultiIndex columns if yf version >= 0.2.20
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]

        # Standardize column names
        df.rename(columns={'index': 'Datetime'}, inplace=True)
        if 'Datetime' not in df.columns and 'Date' in df.columns:
            df.rename(columns={'Date': 'Datetime'}, inplace=True)
            
        if 'Datetime' not in df.columns:
            continue

        df = calculate_daily_pivots(df)
        df['Vol_SMA_20'] = df['Volume'].rolling(window=20).mean()
        
        # Convert Datetime to local IST time strings for fast filtering
        if df['Datetime'].dt.tz is None:
            # Assuming yfinance returns localized to Asia/Kolkata or UTC, we ensure it's IST
            # But yfinance 'Datetime' is usually localized. Let's just use dt.time directly
            pass

        df['time_obj'] = df['Datetime'].dt.time
        
        in_position = False
        entry_price = 0.0
        sl_price = 0.0
        tp_price = 0.0
        entry_qty = 0
        entry_time = None
        entry_friction_val = 0.0
        
        start_time = time(9, 45)
        end_time = time(13, 30)
        hard_exit_time = time(15, 15)
        
        # Iterate over bars
        for idx, row in df.iterrows():
            t = row['time_obj']
            close = row['Close']
            high = row['High']
            low = row['Low']
            vol = row['Volume']
            r1 = row['R1']
            r2 = row['R2']
            vol_sma = row['Vol_SMA_20']
            
            if pd.isna(r1) or pd.isna(vol_sma):
                continue
                
            if not in_position:
                if start_time <= t <= end_time:
                    # Breakout Logic
                    if close > r1 and vol > 1.5 * vol_sma:
                        entry_price = close
                        sl_price = low
                        tp_price = r2
                        
                        if sl_price >= entry_price:
                            sl_price = entry_price * 0.99 # Fallback SL
                            
                        if tp_price <= entry_price:
                            tp_price = entry_price * 1.01 # Fallback TP
                            
                        # Ed Thorp Risk Sizing
                        risk_amt = initial_capital * risk_per_trade_pct
                        stop_dist = entry_price - sl_price
                        qty = int(risk_amt / stop_dist) if stop_dist > 0 else 1
                        
                        max_qty = int(45000 / entry_price) # Max ₹45k exposure
                        entry_qty = max(1, min(qty, max_qty))
                        
                        entry_fric = IndianStatutoryCostModel.calculate_order_friction(
                            leg=OrderLeg.BUY,
                            price=Decimal(str(round(entry_price, 2))),
                            quantity=entry_qty,
                            product=ProductType.INTRADAY
                        )
                        
                        entry_friction_val = float(entry_fric.all_in_total_friction)
                        entry_time = row['Datetime']
                        in_position = True
            
            else:
                exit_reason = None
                exit_price = 0.0
                
                # Check Hard Exit
                if t >= hard_exit_time:
                    exit_reason = "HARD_EXIT_15_15"
                    exit_price = close
                elif high >= tp_price:
                    exit_reason = "TAKE_PROFIT"
                    exit_price = tp_price
                elif low <= sl_price:
                    exit_reason = "STOP_LOSS"
                    exit_price = sl_price
                    
                if exit_reason:
                    exit_fric = IndianStatutoryCostModel.calculate_order_friction(
                        leg=OrderLeg.SELL,
                        price=Decimal(str(round(exit_price, 2))),
                        quantity=entry_qty,
                        product=ProductType.INTRADAY
                    )
                    
                    exit_friction_val = float(exit_fric.all_in_total_friction)
                    total_friction = entry_friction_val + exit_friction_val
                    
                    gross_pnl = (exit_price - entry_price) * entry_qty
                    net_pnl = gross_pnl - total_friction
                    
                    trades.append({
                        "Symbol": sym,
                        "Entry Time": entry_time,
                        "Exit Time": row['Datetime'],
                        "Entry Price": entry_price,
                        "Exit Price": exit_price,
                        "Qty": entry_qty,
                        "Exit Reason": exit_reason,
                        "Gross PnL": gross_pnl,
                        "Friction": total_friction,
                        "Net PnL": net_pnl
                    })
                    
                    in_position = False

    # Summarize
    total_trades = len(trades)
    if total_trades == 0:
        print("\nNo trades executed during the backtest period.")
        return
        
    df_trades = pd.DataFrame(trades)
    winning_trades = df_trades[df_trades['Net PnL'] > 0]
    losing_trades = df_trades[df_trades['Net PnL'] <= 0]
    
    win_rate = (len(winning_trades) / total_trades) * 100
    gross_pnl = df_trades['Gross PnL'].sum()
    total_fric = df_trades['Friction'].sum()
    net_pnl = df_trades['Net PnL'].sum()
    
    print("\n" + "=" * 80)
    print("📊 INTRADAY PIVOT BREAKOUT - PERFORMANCE REPORT (LAST 60 DAYS)")
    print("=" * 80)
    print(f"Total Trades Executed : {total_trades}")
    print(f"Win Rate              : {win_rate:.2f}% ({len(winning_trades)} Wins / {len(losing_trades)} Losses)")
    print(f"Gross PnL             : ₹{gross_pnl:,.2f}")
    print(f"Total Friction Paid   : ₹{total_fric:,.2f}")
    print(f"Net Profit            : ₹{net_pnl:,.2f}")
    print("=" * 80)


if __name__ == "__main__":
    run_intraday_backtest()
