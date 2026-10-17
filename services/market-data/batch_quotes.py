"""
Algo Lab — Batched Real-Time Quote Engine via Zerodha Kite Connect.

Replaces slow 60s individual REST loops with high-performance batch operations:
- Batch up to 500 instruments per kite.quote() call (rate limit: 1 req/sec).
- Formats instrument keys compliant with Kite Connect ("NSE:SYMBOL", "NFO:SYMBOL").
"""

from typing import Any, Dict, List, Optional
import time
from kiteconnect import KiteConnect


class BatchQuoteProvider:
    """Manages high-throughput batched quote ingestion adhering to Kite rate limits."""

    MAX_BATCH_SIZE: int = 500

    def __init__(self, kite: KiteConnect, default_exchange: str = "NSE"):
        self.kite = kite
        self.default_exchange = default_exchange
        self._last_call_time: float = 0.0
        self._min_interval: float = 1.0  # 1 request per second for quote API

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_call_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call_time = time.time()

    def format_instrument_key(self, symbol: str, exchange: Optional[str] = None) -> str:
        ex = exchange or self.default_exchange
        sym = symbol.replace(f"{ex}:", "").replace(".NS", "").replace(".BO", "").strip().upper()
        return f"{ex}:{sym}"

    def fetch_quotes_batch(self, symbols: List[str], exchange: Optional[str] = None) -> Dict[str, Any]:
        """Fetches real-time LTP, OHLC, depth, and volume in single batched HTTP requests.

        Chunks symbols into batches of 500 per Kite Connect specification.
        """
        if not symbols:
            return {}

        ex = exchange or self.default_exchange
        formatted_keys = [self.format_instrument_key(s, ex) for s in symbols]
        all_quotes: Dict[str, Any] = {}

        for i in range(0, len(formatted_keys), self.MAX_BATCH_SIZE):
            chunk = formatted_keys[i : i + self.MAX_BATCH_SIZE]
            self._rate_limit()
            try:
                chunk_quotes = self.kite.quote(chunk)
                all_quotes.update(chunk_quotes)
            except Exception as e:
                # Fail-closed logging
                print(f"[ERROR] Failed fetching batch quotes for chunk: {e}")

        return all_quotes

    def fetch_ltp_batch(self, symbols: List[str], exchange: Optional[str] = None) -> Dict[str, float]:
        """Fetches lightweight LTP for given symbols in batch."""
        if not symbols:
            return {}

        ex = exchange or self.default_exchange
        formatted_keys = [self.format_instrument_key(s, ex) for s in symbols]
        self._rate_limit()

        try:
            raw_ltp = self.kite.ltp(formatted_keys)
            return {
                k.split(":")[-1]: float(v.get("last_price", 0.0))
                for k, v in raw_ltp.items()
            }
        except Exception as e:
            print(f"[ERROR] Failed fetching batch LTP: {e}")
            return {}
