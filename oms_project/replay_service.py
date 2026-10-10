"""
OMS Project - Historical Replay Engine ("The Time Machine")
Feeds historical market data ticks into MarketDataService and BrokerGateway
with time compression and deterministic tick-by-tick synchronization.
"""

import time
import csv
import math
import random
from typing import List, Dict, Any, Optional, Callable
from oms_project.schemas import NormalizedTick
from oms_project.central_data_feed import MarketDataService


def generate_synthetic_ticks(
    symbol: str = "RELIANCE",
    start_price: float = 1200.0,
    count: int = 1000,
    volatility: float = 0.005,
    trend: float = 0.0001,
    seed: int = 42,
) -> List[Dict[str, Any]]:
    """Generates synthetic tick series (geometric random walk with mean-reverting waves)."""
    random.seed(seed)
    ticks = []
    curr_price = start_price
    base_time = 1750000000.0  # Synthetic epoch start

    for i in range(count):
        # Sine wave overlay to create explicit mean-reversion opportunity
        cycle = math.sin(i / 15.0) * 15.0
        noise = random.gauss(0, start_price * volatility)
        curr_price = max(10.0, start_price + cycle + noise + (i * trend))
        
        ticks.append({
            "symbol": symbol,
            "price": round(curr_price, 2),
            "volume": float(random.randint(10, 500)),
            "timestamp": base_time + (i * 0.1),
        })

    return ticks


class HistoricalReplayEngine:
    """
    Historical Replay Engine for Backtesting.
    Loads tick datasets and replays them into MarketDataService pub/sub.
    """

    def __init__(
        self,
        market_data_service: Optional[MarketDataService] = None,
        playback_speed: float = 0.0,  # 0.0 = instant / synchronous backtest mode
    ):
        self.feed = market_data_service or MarketDataService()
        self.playback_speed = playback_speed
        self.ticks: List[Dict[str, Any]] = []
        self.processed_count: int = 0
        self.start_time: float = 0.0
        self.end_time: float = 0.0

    def load_ticks(self, ticks: List[Dict[str, Any]]):
        """Load tick data list directly."""
        self.ticks = ticks
        self.processed_count = 0

    def load_csv(self, file_path: str):
        """Load historical ticks from CSV file."""
        ticks = []
        with open(file_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ticks.append({
                    "symbol": str(row["symbol"]).upper(),
                    "price": float(row["price"]),
                    "volume": float(row.get("volume", 1.0)),
                    "timestamp": float(row.get("timestamp", time.time())),
                })
        self.ticks = ticks
        self.processed_count = 0

    def replay_ticks_sync(
        self,
        on_tick_callback: Optional[Callable[[NormalizedTick], None]] = None,
    ) -> int:
        """
        Synchronously replays loaded historical ticks.
        Guarantees deterministic execution tick-by-tick.
        """
        self.start_time = time.time()
        self.processed_count = 0

        if not self.ticks:
            return 0

        prev_tick_ts: Optional[float] = None

        for raw_tick in self.ticks:
            curr_tick_ts = raw_tick.get("timestamp", time.time())
            
            # Time Compression delay if playback_speed > 0
            if self.playback_speed > 0 and prev_tick_ts is not None:
                delta = curr_tick_ts - prev_tick_ts
                if delta > 0:
                    time.sleep(delta / self.playback_speed)

            # Publish to central market data feed
            tick, _ = self.feed.publish_tick_broadcast(raw_tick)
            self.feed.emit_system_heartbeat()

            if on_tick_callback:
                on_tick_callback(tick)

            self.processed_count += 1
            prev_tick_ts = curr_tick_ts

        self.end_time = time.time()
        return self.processed_count

    def get_elapsed_time(self) -> float:
        """Returns elapsed wall clock time in seconds for the replay run."""
        return max(0.0001, self.end_time - self.start_time)
