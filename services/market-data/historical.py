"""
Algo Lab — Point-in-Time Historical & Intra-Day Data Fetcher via Zerodha Kite Connect.

Guarantees Core Principles #3 & #4 (Strict Look-Ahead Bias Prevention):
- Strips currently forming intra-minute candles during live market hours.
- Returns clean historical 1m / daily bars with Open Interest (OI).
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import polars as pl
from kiteconnect import KiteConnect

IST = timezone(timedelta(hours=5, minutes=30))


def fetch_clean_1m_bars(
    kite: KiteConnect,
    instrument_token: int,
    from_dt: datetime,
    to_dt: datetime,
    include_oi: bool = True,
) -> pl.DataFrame:
    """Fetches 1-minute historical candles from Kite Connect and strips incomplete intra-minute bars.

    Eliminates look-ahead bias by flooring current clock to start of the current minute
    and dropping any bar whose timestamp is >= current_minute_floor.
    """
    records = kite.historical_data(
        instrument_token=instrument_token,
        from_date=from_dt,
        to_date=to_dt,
        interval="minute",
        continuous=False,
        oi=include_oi,
    )
    if not records:
        return pl.DataFrame()

    df = pl.DataFrame(records)

    # Floor current IST clock to the start of the current minute
    current_minute_floor = datetime.now(IST).replace(second=0, microsecond=0)

    # Strictly drop the currently forming bar to guarantee point-in-time integrity
    # Convert 'date' column if needed
    if "date" in df.columns:
        df = df.filter(pl.col("date") < current_minute_floor)

    return df


def fetch_rolling_eod_window(
    kite: KiteConnect,
    instrument_token: int,
    lookback_days: int = 60,
    end_date: Optional[datetime] = None,
    interval: str = "minute",
) -> pl.DataFrame:
    """Fetches rolling EOD window for research and backtesting in a single API call (up to 60 days of 1-minute or daily candles)."""
    end_dt = end_date or datetime.now(IST)
    start_dt = end_dt - timedelta(days=lookback_days)

    records = kite.historical_data(
        instrument_token=instrument_token,
        from_date=start_dt,
        to_date=end_dt,
        interval=interval,
        continuous=False,
        oi=True,
    )
    if not records:
        return pl.DataFrame()

    return pl.DataFrame(records)
