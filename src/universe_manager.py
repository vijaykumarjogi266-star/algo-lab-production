"""
Authoritative Universe Manager for Indian Equities (NSE).
Dynamically manages and ingests the NIFTY 50 constituent universe.

Key Responsibilities:
1. Dynamic Constituent Fetching:
   - Fetches live NIFTY 50 constituents from official/verified sources with authoritative fallback.
2. Macro Sector Classification:
   - Maps each constituent to standardized institutional sector for concentration guardrails.
3. 1d Daily Candle Ingestion & Local Parquet Caching:
   - Synchronously or batch-downloads 1d daily candles for all 50 constituents.
   - Standardizes schema ('date', 'open', 'high', 'low', 'close', 'volume') for Polars/Pandas.
"""

import sys
import io
from pathlib import Path
from typing import Dict, List, Any, Optional
import requests
import pandas as pd
import yfinance as yf

# Fallback Authoritative 50 Constituents and Standardized Macro Sectors
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
    """
    Manages Nifty 50 constituents, sector classifications, and daily candle ingestion.
    """
    WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/NIFTY_50"

    def __init__(self, cache_dir: Optional[Path] = None):
        if cache_dir is None:
            cache_dir = Path(__file__).resolve().parent.parent / "data" / "cache"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._constituents: List[Dict[str, str]] = []
        self._sector_map: Dict[str, str] = {}
        self.load_universe()

    def load_universe(self, dynamic: bool = True) -> List[Dict[str, str]]:
        """Loads Nifty 50 constituents dynamically with verified fallback."""
        if dynamic:
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                resp = requests.get(self.WIKIPEDIA_URL, headers=headers, timeout=8)
                if resp.status_code == 200:
                    tables = pd.read_html(io.StringIO(resp.text))
                    for t in tables:
                        if "Symbol" in t.columns:
                            valid_rows = t.dropna(subset=["Symbol"]).copy()
                            if len(valid_rows) >= 50:
                                parsed = []
                                for _, row in valid_rows.head(50).iterrows():
                                    sym = str(row["Symbol"]).strip()
                                    sec = str(row.get("Sector[15]", row.get("Sector", "GENERAL"))).strip()
                                    parsed.append({
                                        "symbol": sym,
                                        "company": str(row.get("Company name", sym)).strip(),
                                        "sector": self._standardize_sector(sec),
                                    })
                                self._constituents = parsed
                                self._rebuild_sector_map()
                                return self._constituents
            except Exception as e:
                pass

        # Authoritative fallback
        self._constituents = AUTHORITATIVE_NIFTY_50_CONSTITUENTS.copy()
        self._rebuild_sector_map()
        return self._constituents

    def _standardize_sector(self, raw_sector: str) -> str:
        s = raw_sector.upper()
        if "FINANCIAL" in s or "BANK" in s:
            return "BANKING_FINANCE"
        if "TECH" in s:
            return "INFORMATION_TECHNOLOGY"
        if "AUTO" in s:
            return "AUTOMOTIVE"
        if "HEALTH" in s or "PHARM" in s:
            return "HEALTHCARE"
        if "METAL" in s or "STEEL" in s or "MINING" in s:
            return "METALS_MINING"
        if "CONSUMER" in s or "FMCG" in s:
            return "FMCG"
        if "ENERGY" in s or "OIL" in s or "GAS" in s or "POWER" in s:
            return "ENERGY_POWER"
        if "CONSTRUCT" in s or "CEMENT" in s:
            return "CONSTRUCTION_INFRA"
        if "TELECOM" in s:
            return "TELECOMMUNICATIONS"
        return "GENERAL"

    def _rebuild_sector_map(self):
        self._sector_map = {}
        for c in self._constituents:
            sym = c["symbol"]
            sec = c["sector"]
            self._sector_map[sym] = sec
            self._sector_map[f"{sym}.NS"] = sec
            self._sector_map[f"{sym}_NS"] = sec

    def get_symbols(self) -> List[str]:
        """Returns clean symbols without exchange suffix."""
        return [c["symbol"] for c in self._constituents]

    def get_tickers(self) -> List[str]:
        """Returns symbols with .NS suffix for Yahoo Finance / Broker endpoints."""
        return [f"{c['symbol']}.NS" for c in self._constituents]

    def get_sector_map(self) -> Dict[str, str]:
        """Returns mapping from symbol to macro sector string."""
        return self._sector_map.copy()

    def download_daily_candles(
        self,
        period: str = "5y",
        interval: str = "1d",
        force_refresh: bool = False,
    ) -> Dict[str, Path]:
        """
        Downloads 1d daily candles for all 50 constituents and saves to parquet cache.
        Returns dict mapping symbol -> Path.
        """
        results = {}
        total = len(self._constituents)
        print(f"[UNIVERSE MANAGER] Ingesting {period} {interval} candles for {total} Nifty 50 constituents...")

        for idx, item in enumerate(self._constituents, 1):
            sym = item["symbol"]
            ticker = f"{sym}.NS"
            cache_file = self.cache_dir / f"{sym}_NS_{period}_{interval}.parquet"

            if not force_refresh and cache_file.exists():
                results[sym] = cache_file
                continue

            try:
                df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True)
                if not df.empty and len(df) >= 20:
                    df = df.reset_index()
                    cols_needed = ["Date", "Open", "High", "Low", "Close", "Volume"]
                    existing_cols = [c for c in cols_needed if c in df.columns]
                    df = df[existing_cols].copy()
                    if "Date" in df.columns and hasattr(df["Date"], "dt"):
                        df["Date"] = df["Date"].dt.tz_localize(None)
                    df.columns = [c.lower() for c in df.columns]
                    df.to_parquet(cache_file)
                    results[sym] = cache_file
                    print(f"  [{idx:02d}/{total:02d}] ✅ Cached {sym} ({len(df)} daily bars)")
                else:
                    print(f"  [{idx:02d}/{total:02d}] ⚠️ Incomplete data for {sym}")
            except Exception as e:
                print(f"  [{idx:02d}/{total:02d}] ❌ Error downloading {sym}: {e}")

        print(f"[UNIVERSE MANAGER] Successfully ingested {len(results)}/{total} constituent datasets into {self.cache_dir}")
        return results
