"""
Authoritative Universe Manager for NIFTY 100 & NSE F&O Universe.
Provides full constituents, company names, and standardized institutional macro sectors.
"""

from typing import Dict, List, Optional


AUTHORITATIVE_NIFTY_100_CONSTITUENTS: List[Dict[str, str]] = [
    # NIFTY 50 Core
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
    {"symbol": "INDIGO", "company": "InterGlobe Aviation", "sector": "SERVICES_AVIATION"},
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

    # NIFTY Next 50 & High-Beta F&O Giants
    {"symbol": "ABB", "company": "ABB India", "sector": "CAPITAL_GOODS_INFRA"},
    {"symbol": "ADANIENSOL", "company": "Adani Energy Solutions", "sector": "POWER_UTILITIES"},
    {"symbol": "ADANIGREEN", "company": "Adani Green Energy", "sector": "POWER_UTILITIES"},
    {"symbol": "AMBUJACEM", "company": "Ambuja Cements", "sector": "CONSTRUCTION_MATERIALS"},
    {"symbol": "BANKBARODA", "company": "Bank of Baroda", "sector": "BANKING_FINANCE"},
    {"symbol": "BERGEPAINT", "company": "Berger Paints", "sector": "CONSUMER_DURABLES"},
    {"symbol": "BHARATFORG", "company": "Bharat Forge", "sector": "AUTOMOTIVE_FORGING"},
    {"symbol": "BOSCHLTD", "company": "Bosch Limited", "sector": "AUTOMOTIVE"},
    {"symbol": "BPCL", "company": "Bharat Petroleum", "sector": "ENERGY_OIL_GAS"},
    {"symbol": "BRITANNIA", "company": "Britannia Industries", "sector": "FMCG"},
    {"symbol": "CANBK", "company": "Canara Bank", "sector": "BANKING_FINANCE"},
    {"symbol": "CHOLAFIN", "company": "Cholamandalam Investment", "sector": "BANKING_FINANCE"},
    {"symbol": "COLPAL", "company": "Colgate-Palmolive", "sector": "FMCG"},
    {"symbol": "CUMMINSIND", "company": "Cummins India", "sector": "CAPITAL_GOODS_INFRA"},
    {"symbol": "DABUR", "company": "Dabur India", "sector": "FMCG"},
    {"symbol": "DIVISLAB", "company": "Divi's Laboratories", "sector": "HEALTHCARE"},
    {"symbol": "DIXON", "company": "Dixon Technologies", "sector": "CONSUMER_ELECTRONICS"},
    {"symbol": "DLF", "company": "DLF Limited", "sector": "REALTY"},
    {"symbol": "GAIL", "company": "GAIL India", "sector": "ENERGY_OIL_GAS"},
    {"symbol": "GODREJCP", "company": "Godrej Consumer Products", "sector": "FMCG"},
    {"symbol": "HAL", "company": "Hindustan Aeronautics", "sector": "CAPITAL_GOODS_DEFENSE"},
    {"symbol": "HAVELLS", "company": "Havells India", "sector": "CONSUMER_DURABLES"},
    {"symbol": "ICICIGI", "company": "ICICI Lombard General Ins", "sector": "BANKING_FINANCE"},
    {"symbol": "ICICIPRULI", "company": "ICICI Prudential Life Ins", "sector": "BANKING_FINANCE"},
    {"symbol": "INDIANB", "company": "Indian Bank", "sector": "BANKING_FINANCE"},
    {"symbol": "INDUSINDBK", "company": "IndusInd Bank", "sector": "BANKING_FINANCE"},
    {"symbol": "NAUKRI", "company": "Info Edge (India)", "sector": "CONSUMER_SERVICES"},
    {"symbol": "IOC", "company": "Indian Oil Corporation", "sector": "ENERGY_OIL_GAS"},
    {"symbol": "IRCTC", "company": "IRCTC", "sector": "CONSUMER_SERVICES"},
    {"symbol": "JINDALSTEL", "company": "Jindal Steel & Power", "sector": "METALS_MINING"},
    {"symbol": "LICI", "company": "Life Insurance Corp of India", "sector": "BANKING_FINANCE"},
    {"symbol": "LTIM", "company": "LTIMindtree", "sector": "INFORMATION_TECHNOLOGY"},
    {"symbol": "LUPIN", "company": "Lupin Limited", "sector": "HEALTHCARE"},
    {"symbol": "MARICO", "company": "Marico Limited", "sector": "FMCG"},
    {"symbol": "MUTHOOTFIN", "company": "Muthoot Finance", "sector": "BANKING_FINANCE"},
    {"symbol": "OFSS", "company": "Oracle Financial Services", "sector": "INFORMATION_TECHNOLOGY"},
    {"symbol": "PERSISTENT", "company": "Persistent Systems", "sector": "INFORMATION_TECHNOLOGY"},
    {"symbol": "PFC", "company": "Power Finance Corporation", "sector": "BANKING_FINANCE"},
    {"symbol": "PIDILITIND", "company": "Pidilite Industries", "sector": "CHEMICALS"},
    {"symbol": "PNB", "company": "Punjab National Bank", "sector": "BANKING_FINANCE"},
    {"symbol": "POLYCAB", "company": "Polycab India", "sector": "CAPITAL_GOODS_INFRA"},
    {"symbol": "RECLTD", "company": "REC Limited", "sector": "BANKING_FINANCE"},
    {"symbol": "SBICARD", "company": "SBI Cards & Payment", "sector": "BANKING_FINANCE"},
    {"symbol": "SHREECEM", "company": "Shree Cement", "sector": "CONSTRUCTION_MATERIALS"},
    {"symbol": "SIEMENS", "company": "Siemens Limited", "sector": "CAPITAL_GOODS_INFRA"},
    {"symbol": "TATAELXSI", "company": "Tata Elxsi", "sector": "INFORMATION_TECHNOLOGY"},
    {"symbol": "TATAPOWER", "company": "Tata Power", "sector": "POWER_UTILITIES"},
    {"symbol": "TVSMOTOR", "company": "TVS Motor Company", "sector": "AUTOMOTIVE"},
    {"symbol": "VEDL", "company": "Vedanta Limited", "sector": "METALS_MINING"},
    {"symbol": "ZOMATO", "company": "Zomato Limited", "sector": "CONSUMER_SERVICES"},
]


class Nifty100UniverseManager:
    """Manages the NIFTY 100 & NSE F&O universe with metadata and sectoral mapping."""

    def __init__(self):
        self._constituents = AUTHORITATIVE_NIFTY_100_CONSTITUENTS.copy()
        self._symbol_map = {c["symbol"]: c for c in self._constituents}
        self._sector_map = {c["symbol"]: c["sector"] for c in self._constituents}

    def get_symbols(self) -> List[str]:
        return [c["symbol"] for c in self._constituents]

    def get_tickers(self) -> List[str]:
        return [f"{c['symbol']}.NS" for c in self._constituents]

    def get_sector_map(self) -> Dict[str, str]:
        return self._sector_map.copy()

    def get_constituent(self, symbol: str) -> Optional[Dict[str, str]]:
        return self._symbol_map.get(symbol.upper())

    def get_symbols_by_sector(self, sector: str) -> List[str]:
        return [c["symbol"] for c in self._constituents if c["sector"].upper() == sector.upper()]
