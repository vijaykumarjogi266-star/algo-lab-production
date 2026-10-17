"""
Algo Lab — Zerodha Kite Daily Instrument Token Resolver & Cache.

Fetches daily NSE/NFO/MCX master instruments from Zerodha Kite Connect,
persists columnar Parquet cache, and provides fast symbol -> instrument_token mapping.
"""

from pathlib import Path
from typing import Dict, Optional
import polars as pl
from kiteconnect import KiteConnect


def sync_daily_instruments(kite: KiteConnect, exchange: str = "NSE") -> pl.DataFrame:
    """Synchronizes daily exchange instrument master list to Parquet storage."""
    raw_instruments = kite.instruments(exchange)
    df = pl.DataFrame(raw_instruments)

    output_path = Path(f"data/raw/instruments/{exchange}_instruments.parquet")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(output_path)
    return df


def get_token_map(exchange: str = "NSE") -> Dict[str, int]:
    """Retrieves cached tradingsymbol -> instrument_token mapping."""
    cache_path = Path(f"data/raw/instruments/{exchange}_instruments.parquet")
    if not cache_path.exists():
        raise FileNotFoundError(
            f"Instrument cache not found at {cache_path}. Run sync_daily_instruments() at 08:30 IST first."
        )
    df = pl.read_parquet(cache_path)
    return dict(zip(df["tradingsymbol"], df["instrument_token"]))


def resolve_instrument_token(symbol: str, exchange: str = "NSE") -> Optional[int]:
    """Resolves an individual symbol to its Kite integer instrument_token."""
    cleaned = symbol.replace(f"{exchange}:", "").replace(".NS", "").replace(".BO", "").strip().upper()
    token_map = get_token_map(exchange)
    return token_map.get(cleaned)
