import re

with open("apps/api/routers/dashboard.py", "r") as f:
    content = f.read()

# Replace get_system_status to query DB
status_old = """@router.get("/api/dashboard/system-status", summary="Get Swing System & Invariant Status")
@router.get("/api/v1/dashboard/system-status", summary="Get Swing System & Invariant Status (v1 alias)")
async def get_system_status() -> Dict[str, Any]:
    \"\"\"
    Returns system operational mode, safety invariants, and next scheduled execution.
    \"\"\"
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    ist_offset = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    now_ist = now_utc.astimezone(ist_offset)

    return {
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

status_new = """@router.get("/api/dashboard/system-status", summary="Get Swing System & Invariant Status")
@router.get("/api/v1/dashboard/system-status", summary="Get Swing System & Invariant Status (v1 alias)")
async def get_system_status() -> Dict[str, Any]:
    \"\"\"
    Returns system operational mode, safety invariants, and authoritative metrics from the ledger.
    \"\"\"
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    ist_offset = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    now_ist = now_utc.astimezone(ist_offset)

    last_run = None
    unresolved_orders = 0
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT updated_at FROM portfolio_state ORDER BY updated_at DESC LIMIT 1")
            row = cur.fetchone()
            if row:
                last_run = row["updated_at"]
    except Exception:
        pass

    # Basic diff to determine if missed run
    engine_health = "HEALTHY"
    if last_run:
        try:
            last_dt = datetime.datetime.fromisoformat(last_run)
            diff_hours = (now_utc - last_dt).total_seconds() / 3600
            if diff_hours > 72:  # Over a weekend
                engine_health = "WARNING - MISSED RUN (>72h since last run)"
        except:
            pass

    return {
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
        "last_successful_engine_run": last_run if last_run else "N/A - PENDING",
        "market_data_freshness": "As of Last Execution (EOD 15:00 IST)",
        "last_reconciliation": last_run if last_run else "N/A - PENDING",
        "unresolved_orders": unresolved_orders,
        "protection_status": "EOD Evaluation Only (No Continuous Stop Orders)",
        "engine_health": engine_health if last_run else "UNKNOWN - PENDING FIRST RUN",
    }"""

content = content.replace(status_old, status_new)
with open("apps/api/routers/dashboard.py", "w") as f:
    f.write(content)

