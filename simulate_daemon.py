import os
import sys
from datetime import datetime, timezone, timedelta
import pytz

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from live_market_daemon import LiveAlgoLabDaemon

def test_dry_run():
    print("=" * 80)
    print("🚀 INITIATING ALGO LAB DAEMON DRY-RUN (TIME TRAVEL SIMULATION)")
    print("=" * 80)
    
    daemon = LiveAlgoLabDaemon(session_only=True)
    
    # Let's time travel to exactly 15:00 IST on a valid trading day (e.g. today if weekday, or a past weekday)
    # We will just patch `get_ist_now()`
    ist = pytz.timezone('Asia/Kolkata')
    
    # Pick the most recent weekday to ensure market was open
    target_date = datetime(2026, 10, 1).date()
    while target_date.weekday() > 4: # 5=Sat, 6=Sun
        target_date -= timedelta(days=1)
        
    fake_time_15_00 = ist.localize(datetime(target_date.year, target_date.month, target_date.day, 15, 0, 5))
    
    def fake_now_15_00():
        return fake_time_15_00
        
    daemon.get_ist_now = fake_now_15_00
    
    # 1. Step at 15:00:05 IST (Ingestion Phase)
    print(f"\n--- TIMING: {fake_time_15_00.strftime('%H:%M:%S IST')} ---")
    daemon.step()
    
    # 2. Time travel to exactly 15:15:05 IST (Execution Phase)
    fake_time_15_15 = ist.localize(datetime(target_date.year, target_date.month, target_date.day, 15, 15, 5))
    def fake_now_15_15():
        return fake_time_15_15
    daemon.get_ist_now = fake_now_15_15
    
    print(f"\n--- TIMING: {fake_time_15_15.strftime('%H:%M:%S IST')} ---")
    daemon.step()

    # 3. Time travel to exactly 15:30:05 IST (Close Phase / Summary)
    fake_time_15_30 = ist.localize(datetime(target_date.year, target_date.month, target_date.day, 15, 30, 5))
    def fake_now_15_30():
        return fake_time_15_30
    daemon.get_ist_now = fake_now_15_30
    
    print(f"\n--- TIMING: {fake_time_15_30.strftime('%H:%M:%S IST')} ---")
    daemon.step()

    print("\n" + "=" * 80)
    print("✅ DRY-RUN COMPLETE")
    print("Check standard output and Discord/Telegram for Webhook notifications!")

if __name__ == "__main__":
    test_dry_run()
