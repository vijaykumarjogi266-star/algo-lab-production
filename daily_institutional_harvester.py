import yfinance as yf
import pandas as pd
import sqlite3
from datetime import datetime
import json
import warnings

warnings.filterwarnings('ignore')

DB_PATH = "/home/ubuntu/algolab/data/institutional_warehouse.db"
# Subset of top Nifty stocks for demonstration speed
NIFTY_UNIVERSE = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", "SBIN.NS", "BHARTIARTL.NS", "ITC.NS"]

def initialize_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Price Data Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS historical_prices (
        date TEXT, symbol TEXT, open REAL, high REAL, low REAL, close REAL, volume INTEGER,
        PRIMARY KEY (date, symbol)
    )""")
    # Corporate Actions Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS corporate_actions (
        date TEXT, symbol TEXT, action_type TEXT, value REAL,
        PRIMARY KEY (date, symbol, action_type)
    )""")
    # News & Sentiment Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS market_news (
        timestamp TEXT, symbol TEXT, title TEXT, publisher TEXT, link TEXT,
        PRIMARY KEY (timestamp, symbol)
    )""")
    conn.commit()
    return conn

def harvest_daily_data(conn):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🚜 Starting Institutional Data Harvest...")
    
    for sym in NIFTY_UNIVERSE:
        print(f"  -> Harvesting Multi-Factor Data for {sym}...")
        ticker = yf.Ticker(sym)
        
        try:
            # 1. Price Data
            hist = ticker.history(period="5d")
            if not hist.empty:
                for idx, row in hist.iterrows():
                    date_str = idx.strftime('%Y-%m-%d')
                    conn.execute(
                        "INSERT OR IGNORE INTO historical_prices (date, symbol, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (date_str, sym, row['Open'], row['High'], row['Low'], row['Close'], row['Volume'])
                    )
            
            # 2. Corporate Actions (Dividends/Splits)
            actions = ticker.actions
            if not actions.empty:
                for idx, row in actions.iterrows():
                    date_str = idx.strftime('%Y-%m-%d')
                    if row['Dividends'] > 0:
                        conn.execute("INSERT OR IGNORE INTO corporate_actions (date, symbol, action_type, value) VALUES (?, ?, ?, ?)", (date_str, sym, 'DIVIDEND', row['Dividends']))
                    if row['Stock Splits'] > 0:
                        conn.execute("INSERT OR IGNORE INTO corporate_actions (date, symbol, action_type, value) VALUES (?, ?, ?, ?)", (date_str, sym, 'SPLIT', row['Stock Splits']))

            # 3. Market News & Events
            news = ticker.news
            if news:
                for article in news:
                    ts = pd.to_datetime(article.get('providerPublishTime', 0), unit='s').strftime('%Y-%m-%d %H:%M:%S')
                    conn.execute(
                        "INSERT OR IGNORE INTO market_news (timestamp, symbol, title, publisher, link) VALUES (?, ?, ?, ?, ?)",
                        (ts, sym, article.get('title', ''), article.get('publisher', ''), article.get('link', ''))
                    )
                    
            conn.commit()
        except Exception as e:
            print(f"  [WARN] Failed harvesting {sym}: {e}")

    print("✅ Harvest Complete. Data safely stored in Institutional Warehouse.")

if __name__ == "__main__":
    conn = initialize_database()
    harvest_daily_data(conn)
    conn.close()
