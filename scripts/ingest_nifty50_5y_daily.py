#!/usr/bin/env python3
"""
Batch Ingestion and Data Cleaning Engine for NIFTY 50 (5-Year Historical Daily Data).

Capabilities:
1. Dynamic Universe Resolution:
   - Fetches official/verified NIFTY 50 constituent list and industrial sectors via Nifty50UniverseManager.
2. Robust Batch Ingestion:
   - Downloads exactly 5 years of daily (1d) candles via yfinance for all 50 NSE tickers.
3. Strict Data Cleaning & Hygiene:
   - Normalizes columns to lowercase ('date', 'open', 'high', 'low', 'close', 'volume').
   - Strips timezone artifacts from timestamps.
   - Detects and cleans missing/null/NaN values:
     * Drops completely unformed bars (null close).
     * Forward fills or harmonizes partial missing values with close prices.
     * Fills null volume with 0.
     * Eliminates duplicate timestamps.
     * Sorts chronologically.
4. Parquet Persistence & Verification:
   - Saves clean, compressed .parquet files to sandbox cache directory.
   - Audits 100% of datasets for zero nulls and institutional bar count compliance.
"""

import sys
import os
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Any
import pandas as pd
import numpy as np
import polars as pl
import yfinance as yf

# Configure paths
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from services.scanner.universe_manager import Nifty50UniverseManager
except ImportError:
    from src.universe_manager import Nifty50UniverseManager


def clean_daily_dataframe(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """
    Cleans and standardizes raw OHLCV DataFrame from yfinance:
    - Removes timezone offsets
    - Renames columns to lowercase
    - Handles missing/null values
    - Removes duplicate dates and sorts chronologically
    """
    if df.empty:
        return df

    df = df.reset_index()

    # Standardize column names
    col_map = {}
    for c in df.columns:
        clow = c.lower()
        if clow in ("date", "datetime"):
            col_map[c] = "date"
        elif clow in ("open", "high", "low", "close", "volume"):
            col_map[c] = clow
    df = df.rename(columns=col_map)

    required_cols = ["date", "open", "high", "low", "close", "volume"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns for {symbol}: {missing}")

    df = df[required_cols].copy()

    # Strip timezone
    if hasattr(df["date"], "dt") and df["date"].dt.tz is not None:
        df["date"] = df["date"].dt.tz_localize(None)

    # Clean missing values:
    # 1. Drop rows where Close is NaN / Null (untraded or missing session)
    df = df.dropna(subset=["close"]).copy()

    # 2. Fill missing Open/High/Low with Close if null
    df["open"] = df["open"].fillna(df["close"])
    df["high"] = df["high"].fillna(df["close"])
    df["low"] = df["low"].fillna(df["close"])

    # High must be >= max(Open, Close) and Low <= min(Open, Close)
    df["high"] = np.maximum(df["high"], np.maximum(df["open"], df["close"]))
    df["low"] = np.minimum(df["low"], np.minimum(df["open"], df["close"]))

    # 3. Fill missing volume with 0
    df["volume"] = df["volume"].fillna(0).astype(int)

    # 4. Deduplicate and sort
    df = df.drop_duplicates(subset=["date"], keep="last")
    df = df.sort_values("date").reset_index(drop=True)

    return df


def batch_ingest_nifty50_5y(
    cache_dirs: List[Path],
    force_refresh: bool = False,
    period: str = "5y",
) -> Dict[str, Dict[str, Any]]:
    """
    Downloads, cleans, and caches 5-year daily parquets for all 50 Nifty constituents.
    """
    for cd in cache_dirs:
        cd.mkdir(parents=True, exist_ok=True)

    mgr = Nifty50UniverseManager()
    symbols = mgr.get_symbols()
    sector_map = mgr.get_sector_map()

    total = len(symbols)
    print("=" * 85)
    print(f"      🏛️  ALGO LAB NIFTY 50 BATCH DATA INGESTION ENGINE ({period.upper()} DAILY)")
    print(f"         Total Constituents: {total} | Output Directories: {[str(d) for d in cache_dirs]}")
    print("=" * 85)

    ingestion_records = {}

    for idx, sym in enumerate(symbols, 1):
        ticker = f"{sym}.NS"
        target_files = [cd / f"{sym}_NS_{period}_1d.parquet" for cd in cache_dirs]
        primary_file = target_files[0]

        sector = sector_map.get(sym, "GENERAL")

        # Check if already cached and clean
        need_download = force_refresh or not primary_file.exists()
        cleaned_pl = None

        if not need_download:
            try:
                pl_test = pl.read_parquet(primary_file)
                col_rename = {c: c.lower() for c in pl_test.columns if c != c.lower()}
                if col_rename:
                    pl_test = pl_test.rename(col_rename)
                    for tf in target_files:
                        pl_test.write_parquet(tf)
                # Check for null values
                null_cnt = sum(pl_test[c].null_count() for c in pl_test.columns)
                if null_cnt > 0 or pl_test.height < 500:
                    need_download = True
                else:
                    cleaned_pl = pl_test
            except Exception:
                need_download = True

        if need_download:
            print(f"[{idx:02d}/{total:02d}] ⬇️ Fetching {ticker:<15} ({sector:<22}) ...", end="", flush=True)
            try:
                raw_df = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=True)
                if raw_df.empty:
                    print(" ❌ EMPTY RESPONSE")
                    continue

                clean_df = clean_daily_dataframe(raw_df, sym)
                cleaned_pl = pl.from_pandas(clean_df)

                # Write to all target cache directories
                for tf in target_files:
                    cleaned_pl.write_parquet(tf)

                d_min = str(cleaned_pl["date"].min())[:10]
                d_max = str(cleaned_pl["date"].max())[:10]
                print(f" ✅ CACHED ({cleaned_pl.height:>4} bars | {d_min} to {d_max})")

            except Exception as e:
                print(f" ❌ ERROR: {e}")
                continue
        else:
            d_min = str(cleaned_pl["date"].min())[:10]
            d_max = str(cleaned_pl["date"].max())[:10]
            # Ensure mirrored across all cache dirs
            for tf in target_files[1:]:
                if not tf.exists():
                    cleaned_pl.write_parquet(tf)
            print(f"[{idx:02d}/{total:02d}] ⚡ CACHED {sym:<15} ({sector:<22}) | {cleaned_pl.height:>4} bars | {d_min} to {d_max}")

        ingestion_records[sym] = {
            "symbol": sym,
            "ticker": ticker,
            "sector": sector,
            "bars": cleaned_pl.height if cleaned_pl is not None else 0,
            "start_date": str(cleaned_pl["date"].min())[:10] if cleaned_pl is not None else None,
            "end_date": str(cleaned_pl["date"].max())[:10] if cleaned_pl is not None else None,
            "null_count": sum(cleaned_pl[c].null_count() for c in cleaned_pl.columns) if cleaned_pl is not None else -1,
        }

    # Summary Audit Table
    print("\n" + "=" * 85)
    print("  📋 NIFTY 50 INGESTION & DATA QUALITY AUDIT SUMMARY")
    print("=" * 85)
    print(f"  {'Symbol':<12} | {'Sector':<22} | {'Bars':>5} | {'Start Date':<10} | {'End Date':<10} | {'Nulls':>5}")
    print("  " + "-" * 81)
    
    total_valid = 0
    for sym, rec in sorted(ingestion_records.items()):
        null_str = "0" if rec["null_count"] == 0 else str(rec["null_count"])
        print(f"  {rec['symbol']:<12} | {rec['sector']:<22} | {rec['bars']:>5} | {rec['start_date']} | {rec['end_date']} | {null_str:>5}")
        if rec["bars"] >= 500 and rec["null_count"] == 0:
            total_valid += 1

    print("  " + "-" * 81)
    print(f"  ✅ High-Quality Clean Datasets Verified: {total_valid}/{total} ({total_valid/total*100:.1f}%)")
    print("=" * 85)

    return ingestion_records


def main():
    parser = argparse.ArgumentParser(description="NIFTY 50 5-Year Historical Daily Ingestion Engine")
    parser.add_argument("--force", action="store_true", default=False, help="Force re-download and re-cleaning of all datasets")
    parser.add_argument("--period", type=str, default="5y", help="Historical horizon (default: 5y)")
    args = parser.parse_args()

    cache_dirs = [BASE_DIR / "data" / "cache"]
    sandbox_cache = Path("/home/ubuntu/algolab-sandbox/disposable_sandbox/data/cache")
    if sandbox_cache.parent.exists():
        cache_dirs.append(sandbox_cache)

    batch_ingest_nifty50_5y(
        cache_dirs=cache_dirs,
        force_refresh=args.force,
        period=args.period,
    )


if __name__ == "__main__":
    main()
