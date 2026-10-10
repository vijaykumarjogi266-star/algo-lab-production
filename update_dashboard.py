import re

with open("apps/api/routers/dashboard.py", "r") as f:
    content = f.read()

# Update the get_system_status endpoint
status_block_old = """    return {
        "mode": "PAPER TRADING",
        "allow_live_trading": False,
        "allow_real_broker_execution": False,
        "next_execution": "15:00 IST",
        "execution_window": "15:00 - 15:30 IST",
        "market_session": "EOD Swing Scanning",
        "timeframe": "Daily (1d candles)",
        "strategy": "Adaptive Swing Trading (Delivery / CNC)",
        "risk_model": "Ed Thorp 1.0% Capital Risk | 2.5x ATR Stop Loss | 3.5x Risk Target",
        "canonical_account": "ACC-FORWARD-CANONICAL-100K-01",
        "server_time_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "server_time_ist": now_ist.strftime("%Y-%m-%d %H:%M:%S IST"),
        "ledger_persistence": "SQLite ACID Enabled",
    }"""

status_block_new = """    return {
        "mode": "PAPER TRADING",
        "allow_live_trading": False,
        "allow_real_broker_execution": False,
        "next_execution": "15:00 IST",
        "execution_window": "15:00 - 15:30 IST",
        "market_session": "EOD Swing Scanning",
        "timeframe": "Daily (1d candles)",
        "strategy": "Adaptive Swing Trading (Delivery / CNC)",
        "risk_model": "1% fixed-fractional risk per trade | 2.5x ATR Stop Loss | 3.5x Risk Target",
        "canonical_account": "ACC-FORWARD-CANONICAL-100K-01",
        "server_time_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "server_time_ist": now_ist.strftime("%Y-%m-%d %H:%M:%S IST"),
        "ledger_persistence": "SQLite ACID Enabled",
        "last_successful_engine_run": "N/A - PENDING",
        "market_data_freshness": "TBD",
        "last_reconciliation": "N/A - PENDING",
        "unresolved_orders": 0,
        "protection_status": "EOD Evaluation Only (No Continuous Stop Orders)",
        "engine_health": "UNKNOWN - PENDING FIRST RUN",
    }"""

content = content.replace(status_block_old, status_block_new)

with open("apps/api/routers/dashboard.py", "w") as f:
    f.write(content)
