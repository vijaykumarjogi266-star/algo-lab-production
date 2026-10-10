"""
Authoritative Universe Manager for Indian Equities (NSE).
Dynamically manages and ingests the NIFTY 50 constituent universe.
"""

from pathlib import Path
import sys

# Ensure disposable_sandbox/src is importable or mirror class
SANDBOX_SRC = Path("/home/ubuntu/algolab-sandbox/disposable_sandbox/src")
if str(SANDBOX_SRC) not in sys.path:
    sys.path.insert(0, str(SANDBOX_SRC))

try:
    from universe_manager import Nifty50UniverseManager, AUTHORITATIVE_NIFTY_50_CONSTITUENTS
except ImportError:
    # Direct definition fallback
    from pathlib import Path
    import io, requests, pandas as pd, yfinance as yf
    from typing import Dict, List, Optional

    AUTHORITATIVE_NIFTY_50_CONSTITUENTS = [
        {"symbol": "ADANIENT", "company": "Adani Enterprises", "sector": "METALS_MINING"},
        {"symbol": "ADANIPORTS", "company": "Adani Ports & SEZ", "sector": "SERVICES_INFRA"},
        {"symbol": "APOLLOHOSP", "company": "Apollo Hospitals", "sector": "HEALTHCARE"},
        {"symbol": "ASIANPAINT", "company": "Asian Paints", "sector": "CONSUMER_DURABLES"},
        {"symbol": "AXISBANK", "company": "Axis Bank", "sector": "BANKING_FINANCE"},
        {"symbol": "BAJAJ-AUTO", "company": "Bajaj Auto", "sector": "AUTOMOTIVE"},
        {"symbol": "BAJFINANCE", "company": "Bajaj Finance", "sector": "BANKING_FINANCE"},
        {"symbol": "BAJAJFINSV", "company": "Bajaj Finserv", "sector": "BANKING_FINANCE"},
        {"symbol": "BEL", "company": "Bharat Electronics", "sector": "CAPITAL_GOODS_DEFENSE"},
        {"symbol": "BHARTIARTL", "company": "Bharti Airtel", "sector": "TELECOMMUNICATIONS"},
        {"symbol": "CIPLA", "company": "Cipla", "sector": "HEALTHCARE"},
        {"symbol": "COALINDIA", "company": "Coal India", "sector": "ENERGY_MINING"},
        {"symbol": "DRREDDY", "company": "Dr. Reddy's Laboratories", "sector": "HEALTHCARE"},
        {"symbol": "EICHERMOT", "company": "Eicher Motors", "sector": "AUTOMOTIVE"},
        {"symbol": "ETERNAL", "company": "Eternal / Zomato", "sector": "CONSUMER_SERVICES"},
        {"symbol": "GRASIM", "company": "Grasim Industries", "sector": "CONSTRUCTION_MATERIALS"},
        {"symbol": "HCLTECH", "company": "HCL Technologies", "sector": "INFORMATION_TECHNOLOGY"},
        {"symbol": "HDFCBANK", "company": "HDFC Bank", "sector": "BANKING_FINANCE"},
        {"symbol": "HDFCLIFE", "company": "HDFC Life Insurance", "sector": "BANKING_FINANCE"},
        {"symbol": "HINDALCO", "company": "Hindalco Industries", "sector": "METALS_MINING"},
        {"symbol": "HINDUNILVR", "company": "Hindustan Unilever", "sector": "FMCG"},
        {"symbol": "ICICIBANK", "company": "ICICI Bank", "sector": "BANKING_FINANCE"},
        {"symbol": "INDIGO", "company": "InterGlobe Aviation (IndiGo)", "sector": "SERVICES_AVIATION"},
        {"symbol": "INFY", "company": "Infosys", "sector": "INFORMATION_TECHNOLOGY"},
        {"symbol": "ITC", "company": "ITC Limited", "sector": "FMCG"},
        {"symbol": "JIOFIN", "company": "Jio Financial Services", "sector": "BANKING_FINANCE"},
        {"symbol": "JSWSTEEL", "company": "JSW Steel", "sector": "METALS_MINING"},
        {"symbol": "KOTAKBANK", "company": "Kotak Mahindra Bank", "sector": "BANKING_FINANCE"},
        {"symbol": "LT", "company": "Larsen & Toubro", "sector": "CAPITAL_GOODS_INFRA"},
        {"symbol": "M&M", "company": "Mahindra & Mahindra", "sector": "AUTOMOTIVE"},
        {"symbol": "MARUTI", "company": "Maruti Suzuki", "sector": "AUTOMOTIVE"},
        {"symbol": "MAXHEALTH", "company": "Max Healthcare", "sector": "HEALTHCARE"},
        {"symbol": "NESTLEIND", "company": "Nestlé India", "sector": "FMCG"},
        {"symbol": "NTPC", "company": "NTPC Limited", "sector": "POWER_UTILITIES"},
        {"symbol": "ONGC", "company": "Oil and Natural Gas Corporation", "sector": "ENERGY_OIL_GAS"},
        {"symbol": "POWERGRID", "company": "Power Grid Corporation", "sector": "POWER_UTILITIES"},
        {"symbol": "RELIANCE", "company": "Reliance Industries", "sector": "ENERGY_CONGLOMERATE"},
        {"symbol": "SBILIFE", "company": "SBI Life Insurance", "sector": "BANKING_FINANCE"},
        {"symbol": "SHRIRAMFIN", "company": "Shriram Finance", "sector": "BANKING_FINANCE"},
        {"symbol": "SBIN", "company": "State Bank of India", "sector": "BANKING_FINANCE"},
        {"symbol": "SUNPHARMA", "company": "Sun Pharmaceutical", "sector": "HEALTHCARE"},
        {"symbol": "TCS", "company": "Tata Consultancy Services", "sector": "INFORMATION_TECHNOLOGY"},
        {"symbol": "TATACONSUM", "company": "Tata Consumer Products", "sector": "FMCG"},
        {"symbol": "TMPV", "company": "Tata Motors Passenger / CV", "sector": "AUTOMOTIVE"},
        {"symbol": "TATASTEEL", "company": "Tata Steel", "sector": "METALS_MINING"},
        {"symbol": "TECHM", "company": "Tech Mahindra", "sector": "INFORMATION_TECHNOLOGY"},
        {"symbol": "TITAN", "company": "Titan Company", "sector": "CONSUMER_DURABLES"},
        {"symbol": "TRENT", "company": "Trent Limited", "sector": "CONSUMER_SERVICES"},
        {"symbol": "ULTRACEMCO", "company": "UltraTech Cement", "sector": "CONSTRUCTION_MATERIALS"},
        {"symbol": "WIPRO", "company": "Wipro", "sector": "INFORMATION_TECHNOLOGY"},
    ]

    class Nifty50UniverseManager:
        def __init__(self, cache_dir: Optional[Path] = None):
            self.cache_dir = cache_dir or Path("/home/ubuntu/algolab-sandbox/disposable_sandbox/data/cache")
            self._constituents = AUTHORITATIVE_NIFTY_50_CONSTITUENTS.copy()
            self._sector_map = {c["symbol"]: c["sector"] for c in self._constituents}

        def get_symbols(self) -> List[str]:
            return [c["symbol"] for c in self._constituents]

        def get_tickers(self) -> List[str]:
            return [f"{c['symbol']}.NS" for c in self._constituents]

        def get_sector_map(self) -> Dict[str, str]:
            return self._sector_map.copy()
