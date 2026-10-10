import os
import re

file_path = "/home/ubuntu/algolab/live_market_daemon.py"
with open(file_path, "r") as f:
    content = f.read()

# 1. Remove missing imports
content = re.sub(r'from src.indian_equity_data import IndianMarketDataFeed\n', '', content)
content = re.sub(r'from src.indian_equity_portfolio import SECTOR_MAP\n', '', content)
content = re.sub(r'from src.indian_equity_taxation import IndianEquityTaxCalculator, TradeCharges\n', '', content)
content = re.sub(r'from src.universe_manager import Nifty50UniverseManager\n', 'from services.scanner.universe_manager import Nifty50UniverseManager\n', content)

# 2. Patch self.feed
content = re.sub(r'self\.feed = IndianMarketDataFeed\(\)', 'import yfinance as yf', content)

# 3. Patch fetch
content = re.sub(
    r'df = self\.feed\.fetch_historical\(sym, period="60d", interval="1d"\)',
    r'df = yf.download(f"{sym}.NS", period="60d", interval="1d", progress=False)',
    content
)

# 4. Patch SECTOR_MAP
content = re.sub(
    r'self\.sector_map = SECTOR_MAP',
    r'self.sector_map = {"RELIANCE": "ENERGY"} # Fallback',
    content
)

with open(file_path, "w") as f:
    f.write(content)
print("Patched live_market_daemon.py")
