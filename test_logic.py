import sys
sys.path.append("/home/ubuntu/algolab")
from live_market_daemon import LiveAlgoLabDaemon

print("Running aggressive logic test...")
daemon = LiveAlgoLabDaemon()
daemon.swing_universe = ["RELIANCE.NS"] # Test on just 1 stock
try:
    daemon.ingest_near_close_daily_candles()
    print("SUCCESS: Signal generation logic executed flawlessly.")
except Exception as e:
    print(f"FAILED: {e}")
