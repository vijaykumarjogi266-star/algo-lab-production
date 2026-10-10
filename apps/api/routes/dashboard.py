"""
Swing Trading Dashboard API Router.
Connects directly to the SQLite overnight ledger to provide real-time
paper-trading metrics, open positions, and system invariants.
"""

import sqlite3
import datetime
from pathlib import Path
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["Swing Trading Dashboard"])

DEFAULT_LEDGER_PATH = Path("/home/ubuntu/algolab-sandbox/disposable_sandbox/data/swing_portfolio_ledger.db")


def get_db_connection(ledger_path: Path = DEFAULT_LEDGER_PATH) -> sqlite3.Connection:
    """Creates a read-only SQLite connection to the swing portfolio ledger."""
    if not ledger_path.exists():
        raise FileNotFoundError(f"Swing portfolio ledger database not found at {ledger_path}")
    conn = sqlite3.connect(f"file:{ledger_path}?mode=ro", uri=True, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/api/dashboard/portfolio", summary="Get Latest Portfolio State")
@router.get("/api/v1/dashboard/portfolio", summary="Get Latest Portfolio State (v1 alias)")
async def get_portfolio_state() -> Dict[str, Any]:
    """
    Connects to swing_portfolio_ledger.db and returns the latest row from
    the portfolio_state table (Cash Balance, Total Equity, Net PnL).
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT 
                    account_id,
                    session_id,
                    market_date,
                    cash,
                    equity,
                    peak_capital,
                    net_pnl,
                    active_positions_count,
                    schema_version,
                    updated_at
                FROM portfolio_state
                ORDER BY updated_at DESC
                LIMIT 1
            """)
            row = cur.fetchone()

            if not row:
                # Return clean default primed state
                return {
                    "account_id": "ACC-FORWARD-CANONICAL-100K-01",
                    "session_id": "STAGE31_FORWARD_PAPER_20260928_001",
                    "market_date": datetime.date.today().isoformat(),
                    "cash_balance": 100000.0,
                    "cash": 100000.0,
                    "total_equity": 100000.0,
                    "equity": 100000.0,
                    "peak_capital": 100000.0,
                    "net_pnl": 0.0,
                    "net_realized_pnl": 0.0,
                    "active_positions_count": 0,
                    "schema_version": "1.0.0",
                    "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "status": "PRIMED",
                }

            cash_val = float(row["cash"])
            equity_val = float(row["equity"])
            net_pnl_val = float(row["net_pnl"])
            peak_val = float(row["peak_capital"])

            return {
                "account_id": row["account_id"],
                "session_id": row["session_id"],
                "market_date": row["market_date"],
                "cash_balance": cash_val,
                "cash": cash_val,
                "total_equity": equity_val,
                "equity": equity_val,
                "peak_capital": peak_val,
                "net_pnl": net_pnl_val,
                "net_realized_pnl": net_pnl_val,
                "active_positions_count": int(row["active_positions_count"]),
                "schema_version": row["schema_version"],
                "updated_at": row["updated_at"],
                "status": "ACTIVE",
            }
    except Exception as e:
        # Fallback graceful response
        return {
            "account_id": "ACC-FORWARD-CANONICAL-100K-01",
            "cash_balance": 100000.0,
            "cash": 100000.0,
            "total_equity": 100000.0,
            "equity": 100000.0,
            "peak_capital": 100000.0,
            "net_pnl": 0.0,
            "net_realized_pnl": 0.0,
            "active_positions_count": 0,
            "status": "DEGRADED",
            "error": str(e),
        }


@router.get("/api/dashboard/positions", summary="Get Active Swing Positions")
@router.get("/api/v1/dashboard/positions", summary="Get Active Swing Positions (v1 alias)")
async def get_active_positions() -> Dict[str, Any]:
    """
    Queries the open_positions table and returns all active swing trades.
    Computes unrealized P&L per position.
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT 
                    symbol,
                    account_id,
                    sector,
                    quantity,
                    entry_price,
                    current_price,
                    stop_loss,
                    take_profit,
                    allocated_capital,
                    entry_time,
                    holding_period_days,
                    product_type,
                    updated_at
                FROM open_positions
                ORDER BY entry_time DESC
            """)
            rows = cur.fetchall()

            positions = []
            for r in rows:
                qty = int(r["quantity"])
                entry_p = float(r["entry_price"])
                curr_p = float(r["current_price"])
                unrealized_pnl = round((curr_p - entry_p) * qty, 2)
                unrealized_pnl_pct = round(((curr_p - entry_p) / entry_p) * 100.0, 2) if entry_p > 0 else 0.0

                positions.append({
                    "symbol": r["symbol"],
                    "account_id": r["account_id"],
                    "sector": r["sector"] or "GENERAL",
                    "quantity": qty,
                    "entry_price": entry_p,
                    "current_price": curr_p,
                    "stop_loss": float(r["stop_loss"]),
                    "take_profit": float(r["take_profit"]),
                    "allocated_capital": float(r["allocated_capital"]),
                    "entry_time": r["entry_time"],
                    "holding_period_days": int(r["holding_period_days"]),
                    "product_type": r["product_type"] or "DELIVERY",
                    "unrealized_pnl": unrealized_pnl,
                    "unrealized_pnl_pct": unrealized_pnl_pct,
                    "updated_at": r["updated_at"],
                })

            return {
                "positions": positions,
                "count": len(positions),
                "total_unrealized_pnl": round(sum(p["unrealized_pnl"] for p in positions), 2),
            }
    except Exception as e:
        return {
            "positions": [],
            "count": 0,
            "total_unrealized_pnl": 0.0,
            "error": str(e),
        }


@router.get("/api/dashboard/system-status", summary="Get Swing System & Invariant Status")
@router.get("/api/v1/dashboard/system-status", summary="Get Swing System & Invariant Status (v1 alias)")
async def get_system_status() -> Dict[str, Any]:
    """
    Returns system operational mode, safety invariants, and next scheduled execution.
    """
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
        "risk_model": "Ed Thorp 1.0% Capital Risk | 2.5x ATR Stop Loss | 3.5x Risk Target",
        "canonical_account": "ACC-FORWARD-CANONICAL-100K-01",
        "server_time_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "server_time_ist": now_ist.strftime("%Y-%m-%d %H:%M:%S IST"),
        "ledger_persistence": "SQLite ACID Enabled",
    }
