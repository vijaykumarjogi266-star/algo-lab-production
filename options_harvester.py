import json
import sqlite3
import pandas as pd
import requests
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

DB_PATH = "/home/ubuntu/algolab/data/institutional_warehouse.db"
INDICES = ["NIFTY", "BANKNIFTY"]

# NSE India requires browser headers to allow requests
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br'
}

def harvest_options_chain(conn):
    date_str = datetime.now().strftime('%Y-%m-%d')
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🚜 Starting Options (F&O) Data Harvest...")

    session = requests.Session()
    session.headers.update(HEADERS)
    
    # Hit the main page first to get cookies
    try:
        session.get("https://www.nseindia.com", timeout=10)
    except:
        pass

    for symbol in INDICES:
        print(f"  -> Harvesting Option Chain for {symbol}...")
        try:
            url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
            response = session.get(url, timeout=10)
            
            if response.status_code == 200:
                payload = response.json()
                records = payload.get('records', {}).get('data', [])
                
                insert_rows = []
                for record in records:
                    strike = record.get('strikePrice')
                    expiry = record.get('expiryDate')
                    
                    if 'CE' in record:
                        ce = record['CE']
                        insert_rows.append((
                            date_str, symbol, expiry, strike, 'CE',
                            ce.get('lastPrice', 0), ce.get('change', 0), ce.get('pChange', 0),
                            ce.get('totalTradedVolume', 0), ce.get('openInterest', 0),
                            ce.get('changeinOpenInterest', 0), ce.get('impliedVolatility', 0)
                        ))
                    if 'PE' in record:
                        pe = record['PE']
                        insert_rows.append((
                            date_str, symbol, expiry, strike, 'PE',
                            pe.get('lastPrice', 0), pe.get('change', 0), pe.get('pChange', 0),
                            pe.get('totalTradedVolume', 0), pe.get('openInterest', 0),
                            pe.get('changeinOpenInterest', 0), pe.get('impliedVolatility', 0)
                        ))
                
                if insert_rows:
                    conn.executemany("""
                        INSERT OR REPLACE INTO options_data 
                        (date, symbol, expiry, strike, opt_type, last_price, change, pchange, volume, open_interest, change_in_oi, implied_volatility)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, insert_rows)
                    conn.commit()
                    print(f"     ✅ Saved {len(insert_rows)} Option Contracts for {symbol}")
            else:
                print(f"  [WARN] NSE API returned status code {response.status_code}")
                
        except Exception as e:
            print(f"  [WARN] Failed harvesting options for {symbol}: {e}")

if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    harvest_options_chain(conn)
    conn.close()
