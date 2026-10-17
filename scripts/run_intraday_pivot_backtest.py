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
    cache_dir = Path("/home/ubuntu/algolab/data/cache/intraday_5m")
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    for sym in symbols:
        ticker = f"{sym}.NS"
        cache_file = cache_dir / f"{sym}.parquet"
        
        # Check cache (valid if non-empty)
        if cache_file.exists():
            try:
                df = pd.read_parquet(cache_file)
            except Exception:
                df = yf.download(ticker, period="60d", interval="5m", progress=False)
                if not df.empty:
                    df.to_parquet(cache_file)
        else:
            df = yf.download(ticker, period="60d", interval="5m", progress=False)
            if not df.empty:
                try:
                    df.to_parquet(cache_file)
                except Exception:
                    pass
                    
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
        
        df['time_obj'] = df['Datetime'].dt.time
        
        in_position = False
        entry_price = 0.0
        sl_price = 0.0
        tp_price = 0.0
        entry_qty = 0
        entry_time = None
        entry_fric_mis = None
        entry_fric_cnc = None
        
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
                    # Breakout Logic: Close > R1 and Volume > 1.5x Vol_SMA_20
                    if close > r1 and vol > 1.5 * vol_sma:
                        entry_price = close
                        sl_price = low
                        tp_price = r2
                        
                        if sl_price >= entry_price:
                            sl_price = entry_price * 0.99  # Fallback SL
                            
                        if tp_price <= entry_price:
                            tp_price = entry_price * 1.01  # Fallback TP
                            
                        # Ed Thorp Risk Sizing
                        risk_amt = initial_capital * risk_per_trade_pct
                        stop_dist = entry_price - sl_price
                        qty = int(risk_amt / stop_dist) if stop_dist > 0 else 1
                        
                        max_qty = int(45000 / entry_price)  # Max ₹45k exposure
                        entry_qty = max(1, min(qty, max_qty))
                        
                        # MIS Friction
                        entry_fric_mis = IndianStatutoryCostModel.calculate_order_friction(
                            leg=OrderLeg.BUY,
                            price=Decimal(str(round(entry_price, 2))),
                            quantity=entry_qty,
                            product=ProductType.INTRADAY
                        )
                        # Delivery CNC Friction
                        entry_fric_cnc = IndianStatutoryCostModel.calculate_order_friction(
                            leg=OrderLeg.BUY,
                            price=Decimal(str(round(entry_price, 2))),
                            quantity=entry_qty,
                            product=ProductType.DELIVERY
                        )
                        
                        entry_time = row['Datetime']
                        in_position = True
            
            else:
                exit_reason = None
                exit_price = 0.0
                
                # Check Hard Exit at 15:15 IST
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
                    # MIS Exit Friction
                    exit_fric_mis = IndianStatutoryCostModel.calculate_order_friction(
                        leg=OrderLeg.SELL,
                        price=Decimal(str(round(exit_price, 2))),
                        quantity=entry_qty,
                        product=ProductType.INTRADAY
                    )
                    # Delivery CNC Exit Friction
                    exit_fric_cnc = IndianStatutoryCostModel.calculate_order_friction(
                        leg=OrderLeg.SELL,
                        price=Decimal(str(round(exit_price, 2))),
                        quantity=entry_qty,
                        product=ProductType.DELIVERY
                    )
                    
                    friction_mis = float(entry_fric_mis.all_in_total_friction + exit_fric_mis.all_in_total_friction)
                    friction_cnc = float(entry_fric_cnc.all_in_total_friction + exit_fric_cnc.all_in_total_friction)
                    
                    gross_pnl = (exit_price - entry_price) * entry_qty
                    net_pnl_mis = gross_pnl - friction_mis
                    net_pnl_cnc = gross_pnl - friction_cnc
                    
                    trades.append({
                        "Symbol": sym,
                        "Entry Time": entry_time,
                        "Exit Time": row['Datetime'],
                        "Entry Price": entry_price,
                        "Exit Price": exit_price,
                        "Qty": entry_qty,
                        "Exit Reason": exit_reason,
                        "Gross PnL": gross_pnl,
                        "Friction MIS": friction_mis,
                        "Net PnL MIS": net_pnl_mis,
                        "Friction CNC": friction_cnc,
                        "Net PnL CNC": net_pnl_cnc,
                        # Breakdown components
                        "MIS Brokerage": float(entry_fric_mis.brokerage + exit_fric_mis.brokerage),
                        "MIS STT": float(entry_fric_mis.stt + exit_fric_mis.stt),
                        "MIS Exch Fee": float(entry_fric_mis.exchange_txn_fee + exit_fric_mis.exchange_txn_fee),
                        "MIS Stamp Duty": float(entry_fric_mis.stamp_duty + exit_fric_mis.stamp_duty),
                        "MIS GST": float(entry_fric_mis.gst + exit_fric_mis.gst),
                        "MIS DP Charge": float(entry_fric_mis.dp_charge + exit_fric_mis.dp_charge),
                        "CNC Brokerage": float(entry_fric_cnc.brokerage + exit_fric_cnc.brokerage),
                        "CNC STT": float(entry_fric_cnc.stt + exit_fric_cnc.stt),
                        "CNC Exch Fee": float(entry_fric_cnc.exchange_txn_fee + exit_fric_cnc.exchange_txn_fee),
                        "CNC Stamp Duty": float(entry_fric_cnc.stamp_duty + exit_fric_cnc.stamp_duty),
                        "CNC GST": float(entry_fric_cnc.gst + exit_fric_cnc.gst),
                        "CNC DP Charge": float(entry_fric_cnc.dp_charge + exit_fric_cnc.dp_charge),
                    })
                    
                    in_position = False

    total_trades = len(trades)
    if total_trades == 0:
        print("\nNo trades executed during the backtest period.")
        return
        
    df_trades = pd.DataFrame(trades)
    df_trades['Exit Time'] = pd.to_datetime(df_trades['Exit Time'])
    df_trades = df_trades.sort_values(by='Exit Time').reset_index(drop=True)
    
    # Save processed trades
    out_csv = Path("/home/ubuntu/algolab/data/processed/intraday_pivot_trades.csv")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df_trades.to_csv(out_csv, index=False)
    
    # Gross metrics
    gross_pnl = df_trades['Gross PnL'].sum()
    gross_wins = df_trades[df_trades['Gross PnL'] > 0]['Gross PnL']
    gross_losses = df_trades[df_trades['Gross PnL'] < 0]['Gross PnL']
    gross_pf = (gross_wins.sum() / abs(gross_losses.sum())) if abs(gross_losses.sum()) > 0 else float('inf')
    gross_win_rate = (len(gross_wins) / total_trades) * 100
    
    # MIS Net metrics
    net_pnl_mis = df_trades['Net PnL MIS'].sum()
    total_fric_mis = df_trades['Friction MIS'].sum()
    mis_wins = df_trades[df_trades['Net PnL MIS'] > 0]['Net PnL MIS']
    mis_losses = df_trades[df_trades['Net PnL MIS'] <= 0]['Net PnL MIS']
    win_rate_mis = (len(mis_wins) / total_trades) * 100
    net_pf_mis = (mis_wins.sum() / abs(mis_losses.sum())) if abs(mis_losses.sum()) > 0 else float('inf')
    
    # Drawdown calculations (MIS Net)
    df_trades['Net_Equity_MIS'] = initial_capital + df_trades['Net PnL MIS'].cumsum()
    df_trades['Peak_MIS'] = df_trades['Net_Equity_MIS'].cummax()
    df_trades['DD_MIS_INR'] = df_trades['Peak_MIS'] - df_trades['Net_Equity_MIS']
    df_trades['DD_MIS_Pct'] = (df_trades['DD_MIS_INR'] / df_trades['Peak_MIS']) * 100
    max_dd_mis_inr = df_trades['DD_MIS_INR'].max()
    max_dd_mis_pct = df_trades['DD_MIS_Pct'].max()

    # Drawdown calculations (Gross)
    df_trades['Gross_Equity'] = initial_capital + df_trades['Gross PnL'].cumsum()
    df_trades['Peak_Gross'] = df_trades['Gross_Equity'].cummax()
    df_trades['DD_Gross_INR'] = df_trades['Peak_Gross'] - df_trades['Gross_Equity']
    df_trades['DD_Gross_Pct'] = (df_trades['DD_Gross_INR'] / df_trades['Peak_Gross']) * 100
    max_dd_gross_inr = df_trades['DD_Gross_INR'].max()
    max_dd_gross_pct = df_trades['DD_Gross_Pct'].max()

    # CNC Net metrics
    net_pnl_cnc = df_trades['Net PnL CNC'].sum()
    total_fric_cnc = df_trades['Friction CNC'].sum()
    cnc_wins = df_trades[df_trades['Net PnL CNC'] > 0]['Net PnL CNC']
    cnc_losses = df_trades[df_trades['Net PnL CNC'] <= 0]['Net PnL CNC']
    win_rate_cnc = (len(cnc_wins) / total_trades) * 100
    net_pf_cnc = (cnc_wins.sum() / abs(cnc_losses.sum())) if abs(cnc_losses.sum()) > 0 else float('inf')

    df_trades['Net_Equity_CNC'] = initial_capital + df_trades['Net PnL CNC'].cumsum()
    df_trades['Peak_CNC'] = df_trades['Net_Equity_CNC'].cummax()
    df_trades['DD_CNC_INR'] = df_trades['Peak_CNC'] - df_trades['Net_Equity_CNC']
    df_trades['DD_CNC_Pct'] = (df_trades['DD_CNC_INR'] / df_trades['Peak_CNC']) * 100
    max_dd_cnc_inr = df_trades['DD_CNC_INR'].max()
    max_dd_cnc_pct = df_trades['DD_CNC_Pct'].max()

    # Exit reason stats
    exit_counts = df_trades['Exit Reason'].value_counts()
    exit_summary = df_trades.groupby('Exit Reason').agg(
        Count=('Net PnL MIS', 'count'),
        Gross_PnL=('Gross PnL', 'sum'),
        Net_PnL_MIS=('Net PnL MIS', 'sum'),
        Avg_Gross=('Gross PnL', 'mean'),
        Avg_Net_MIS=('Net PnL MIS', 'mean'),
    ).reset_index()

    print("\n" + "=" * 80)
    print("📊 INTRADAY PIVOT BREAKOUT - COMPREHENSIVE PERFORMANCE REPORT")
    print("=" * 80)
    print(f"Total Trades Executed       : {total_trades}")
    print(f"Initial Capital             : ₹{initial_capital:,.2f}")
    print("-" * 80)
    print(f"GROSS PERFORMANCE:")
    print(f"  Gross PnL                 : ₹{gross_pnl:,.2f}")
    print(f"  Gross Win Rate            : {gross_win_rate:.2f}% ({len(gross_wins)} Wins / {len(gross_losses)} Losses)")
    print(f"  Gross Profit Factor       : {gross_pf:.4f}")
    print(f"  Gross Max Drawdown        : ₹{max_dd_gross_inr:,.2f} ({max_dd_gross_pct:.2f}%)")
    print("-" * 80)
    print(f"INTRADAY (MIS) NET PERFORMANCE:")
    print(f"  Net PnL (MIS)             : ₹{net_pnl_mis:,.2f}")
    print(f"  Net Win Rate (MIS)        : {win_rate_mis:.2f}% ({len(mis_wins)} Wins / {len(mis_losses)} Losses)")
    print(f"  Net Profit Factor (MIS)   : {net_pf_mis:.4f}")
    print(f"  Total Friction (MIS)      : ₹{total_fric_mis:,.2f} (Avg ₹{total_fric_mis/total_trades:.2f}/trade)")
    print(f"  Max Drawdown (MIS)        : ₹{max_dd_mis_inr:,.2f} ({max_dd_mis_pct:.2f}%)")
    print("-" * 80)
    print(f"HYPOTHETICAL DELIVERY (CNC) NET PERFORMANCE:")
    print(f"  Net PnL (CNC)             : ₹{net_pnl_cnc:,.2f}")
    print(f"  Net Win Rate (CNC)        : {win_rate_cnc:.2f}% ({len(cnc_wins)} Wins / {len(cnc_losses)} Losses)")
    print(f"  Net Profit Factor (CNC)   : {net_pf_cnc:.4f}")
    print(f"  Total Friction (CNC)      : ₹{total_fric_cnc:,.2f} (Avg ₹{total_fric_cnc/total_trades:.2f}/trade)")
    print(f"  Max Drawdown (CNC)        : ₹{max_dd_cnc_inr:,.2f} ({max_dd_cnc_pct:.2f}%)")
    print("=" * 80)
    print("📋 EXIT REASONS BREAKDOWN:")
    for _, r in exit_summary.iterrows():
        pct = (r['Count'] / total_trades) * 100
        print(f"  {r['Exit Reason']:<18}: {r['Count']:>4} ({pct:>5.1f}%) | Gross: ₹{r['Gross_PnL']:>10.2f} | Net MIS: ₹{r['Net_PnL_MIS']:>10.2f} | Avg Net: ₹{r['Avg_Net_MIS']:>7.2f}")
    print("=" * 80)
    print("⚖️ FRICTION DYNAMICS BREAKDOWN (MIS vs CNC):")
    print(f"  {'Component':<18} | {'Intraday (MIS)':>15} | {'Delivery (CNC)':>15} | {'Difference (MIS - CNC)':>22}")
    print(f"  {'-'*18}-+-{'-'*15}-+-{'-'*15}-+-{'-'*22}")
    components = [
        ("Brokerage", df_trades['MIS Brokerage'].sum(), df_trades['CNC Brokerage'].sum()),
        ("STT", df_trades['MIS STT'].sum(), df_trades['CNC STT'].sum()),
        ("Exchange Fees", df_trades['MIS Exch Fee'].sum(), df_trades['CNC Exch Fee'].sum()),
        ("Stamp Duty", df_trades['MIS Stamp Duty'].sum(), df_trades['CNC Stamp Duty'].sum()),
        ("GST (18%)", df_trades['MIS GST'].sum(), df_trades['CNC GST'].sum()),
        ("DP Charges", df_trades['MIS DP Charge'].sum(), df_trades['CNC DP Charge'].sum()),
        ("TOTAL FRICTION", total_fric_mis, total_fric_cnc),
    ]
    for comp, mis_v, cnc_v in components:
        diff = mis_v - cnc_v
        print(f"  {comp:<18} | ₹{mis_v:>14.2f} | ₹{cnc_v:>14.2f} | ₹{diff:>21.2f}")
    print("=" * 80)


if __name__ == "__main__":
    run_intraday_backtest()

