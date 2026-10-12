#!/usr/bin/env python3
import yfinance as yf
"""
Institutional Live Market Daemon for Indian Equities (NSE/BSE).
Upgraded for ZERO HUMAN INTERVENTION & END-OF-DAY (EOD) SWING TRADING (DELIVERY/CNC).

Core Architectural Upgrades:
1. Complete Elimination of Intraday 15:15 Mandatory Liquidation:
   - Open positions are NO LONGER liquidated at 15:15 IST.
   - Positions are held overnight to capture multi-day swing momentum.
2. EOD State Machine (15:00 - 15:30 IST):
   - OFF_HOURS (< 15:00:00 IST): Standby until 15:00 IST EOD wakeup.
   - EOD_CANDLE_INGESTION (15:00:00 - 15:15:00 IST): Fetches near-close daily (1d) candles,
     computes ATR14, EMA20, SMA50, and evaluates swing entry/exit signals.
   - EOD_TRADE_EXECUTION (15:15:00 - 15:25:00 IST): Evaluates exits (2.5 * ATR14 Stop Loss,
     3.5 * Risk Take Profit) and executes new swing entries with 1% fixed-fractional risk per trade.
   - EOD_PERSISTENCE (15:25:00 - 15:30:00 IST): Commits portfolio state and open positions
     to SQLite ledger ('data/swing_portfolio_ledger.db') and JSON state file to be safely held overnight.
   - SESSION_COMPLETED (15:30:00+ IST): Clean session termination with code 0 (zero intervention).
3. SQLite Overnight Ledger Engine:
   - Persists tables: 'portfolio_state', 'open_positions', 'trade_journal', 'overnight_snapshots'.
   - Guarantees crash resilience, transactional ACID commits, and overnight position tracking.
4. Statutory Delivery Friction Model:
   - STT: 0.1% on Buy and Sell legs.
   - Stamp Duty: 0.015% on Buy leg only.
   - DP Charge: Flat ₹15.34 applied only on Sell leg.
   - GST: 18% on Brokerage, Exchange, SEBI, and DP charges.
5. Calendar & Invariant Guards:
   - Validates official NSE trading calendar ('XNSE') via exchange_calendars at startup.
   - Strictly enforces ALLOW_LIVE_TRADING = False and ALLOW_REAL_BROKER_EXECUTION = False.
   - Fails closed on quarantined accounts or corrupted state.
"""

import sys
import os
import time
import json
import sqlite3
import signal
import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional, Dict, Any, List

BASE_DIR = Path(__file__).resolve().parent
venv_python = BASE_DIR / ".venv" / "bin" / "python3"
if venv_python.exists() and Path(sys.executable).resolve() != venv_python.resolve() and "-c" not in sys.argv:
    os.execv(str(venv_python), [str(venv_python)] + sys.argv)

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import exchange_calendars as xcals
import pandas as pd
import numpy as np

from services.scanner.universe_manager import Nifty50UniverseManager
from src.notification_engine import NotificationEngine, DiscordWebhookNotifier

# ==============================================================================
# ABSOLUTE SAFETY INVARIANTS (FAIL-CLOSED RUNTIME BOUNDARIES)
# ==============================================================================
ALLOW_LIVE_TRADING: bool = False
ALLOW_REAL_BROKER_EXECUTION: bool = False

def enforce_safety_invariants():
    """Fails closed immediately if live trading or real broker execution is enabled."""
    if ALLOW_LIVE_TRADING:
        raise RuntimeError(
            "FAIL-CLOSED INVARIANT VIOLATION: ALLOW_LIVE_TRADING is set to True. "
            "Live execution is strictly blocked without institutional clearance."
        )
    if ALLOW_REAL_BROKER_EXECUTION:
        raise RuntimeError(
            "FAIL-CLOSED INVARIANT VIOLATION: ALLOW_REAL_BROKER_EXECUTION is set to True. "
            "Real broker endpoints are strictly forbidden."
        )

# ==============================================================================
# CANONICAL FORWARD PAPER-TRADING ACCOUNT IDENTIFIERS
# ==============================================================================
CANONICAL_ACCOUNT_ID = "ACC-FORWARD-CANONICAL-100K-01"
PROHIBITED_QUARANTINED_ACCOUNTS = {"ACC-BASE-100K-01", "ACC-REPLAY-100K-02"}
CANONICAL_SCHEMA_VERSION = "1.0.0"


def get_nse_calendar() -> xcals.ExchangeCalendar:
    """Retrieves official XNSE calendar, registering alias to XBOM if needed."""
    if "XNSE" not in xcals.get_calendar_names():
        xcals.register_calendar_alias("XNSE", "XBOM")
    return xcals.get_calendar("XNSE")


class DaemonPhase(str, Enum):
    OFF_HOURS = "OFF_HOURS"                         # Outside 15:00 - 15:30 IST
    EOD_CANDLE_INGESTION = "EOD_CANDLE_INGESTION"   # 15:00:00 - 15:15:00 IST (Wakeup, Ingest 1d candles, Signals)
    EOD_TRADE_EXECUTION = "EOD_TRADE_EXECUTION"     # 15:15:00 - 15:25:00 IST (Evaluate Exits & Execute Entries)
    EOD_PERSISTENCE = "EOD_PERSISTENCE"             # 15:25:00 - 15:30:00 IST (Persist Open Positions to SQLite overnight)
    SESSION_COMPLETED = "SESSION_COMPLETED"         # 15:30:00+ IST (Clean Shutdown / Standby)


class AccountSegregationError(Exception):
    """Raised when account segregation rules are violated or quarantined accounts are accessed."""
    pass


class DaemonStateValidationError(Exception):
    """Raised when daemon state schema validation fails closed."""
    pass


@dataclass
class ActiveSwingPosition:
    symbol: str
    sector: str
    quantity: int
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    allocated_capital: float
    entry_time: str
    holding_period_days: int = 1
    product_type: str = "DELIVERY"
    breakeven_activated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


from decimal import Decimal, ROUND_HALF_UP


def round_inr(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_delivery_statutory_friction(
    buy_price: float,
    sell_price: float,
    quantity: int
) -> Dict[str, float]:
    """
    Enforces Indian Equity Delivery (CNC / Swing Trading) statutory friction using Decimal ROUND_HALF_UP:
    - Brokerage: ₹0.00 (Standard zero brokerage delivery model)
    - STT: 0.1% on both Buy and Sell legs
    - Stamp Duty: 0.015% on Buy leg only
    - DP Charge: Flat ₹15.34 applied only on Sell leg
    - Exchange Txn Fee: 0.00297% on total turnover
    - SEBI Turnover Fee: 0.0001% on total turnover
    - GST: 18% applied to Brokerage + Exchange + SEBI + DP Charge
    """
    d_buy = Decimal(str(round(buy_price, 2)))
    d_sell = Decimal(str(round(sell_price, 2)))
    d_qty = Decimal(quantity)

    buy_turnover = round_inr(d_buy * d_qty)
    sell_turnover = round_inr(d_sell * d_qty)
    total_turnover = buy_turnover + sell_turnover

    brokerage = Decimal("0.00")
    stt = round_inr(total_turnover * Decimal("0.0010"))
    stamp_duty = round_inr(buy_turnover * Decimal("0.00015"))
    dp_charge = Decimal("15.34")
    exchange_fee = round_inr(total_turnover * Decimal("0.0000297"))
    sebi_fee = round_inr(total_turnover * Decimal("0.0000010"))

    taxable_services = brokerage + exchange_fee + sebi_fee + dp_charge
    gst = round_inr(taxable_services * Decimal("0.18"))

    total_charges = brokerage + stt + exchange_fee + sebi_fee + stamp_duty + dp_charge + gst

    return {
        "turnover": float(total_turnover),
        "brokerage": float(brokerage),
        "stt": float(stt),
        "stamp_duty": float(stamp_duty),
        "dp_charge": float(dp_charge),
        "exchange_txn_fee": float(exchange_fee),
        "sebi_fee": float(sebi_fee),
        "gst": float(gst),
        "total_charges": float(total_charges),
    }


def validate_canonical_state(data: dict) -> dict:
    """
    Strictly validates daemon portfolio state schema.
    Fails closed if account_id is missing, quarantined, or unauthorized,
    or if required schema fields are missing or malformed.
    """
    if not isinstance(data, dict):
        raise DaemonStateValidationError("State data must be a JSON dictionary.")

    account_id = data.get("account_id")
    if not account_id:
        raise AccountSegregationError("Missing required field 'account_id' in state file.")
    if account_id in PROHIBITED_QUARANTINED_ACCOUNTS:
        raise AccountSegregationError(
            f"Account '{account_id}' is a quarantined historical baseline account and strictly prohibited for forward paper trading."
        )
    if account_id != CANONICAL_ACCOUNT_ID:
        raise AccountSegregationError(
            f"Unauthorized account_id '{account_id}'. Expected canonical account '{CANONICAL_ACCOUNT_ID}'."
        )

    schema_version = data.get("schema_version")
    if not schema_version:
        raise DaemonStateValidationError("Missing required field 'schema_version' in state file.")
    if str(schema_version) != CANONICAL_SCHEMA_VERSION:
        raise DaemonStateValidationError(
            f"Incompatible schema_version '{schema_version}'. Expected '{CANONICAL_SCHEMA_VERSION}'."
        )

    required_fields = ["cash", "equity", "peak_capital", "net_pnl"]
    for field in required_fields:
        if field not in data:
            raise DaemonStateValidationError(f"Missing required field '{field}' in state file.")
        val = data[field]
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            raise DaemonStateValidationError(f"Invalid type for field '{field}': {type(val).__name__}. Expected numeric.")

    if data["cash"] < 0:
        raise DaemonStateValidationError(f"Invalid negative cash: {data['cash']}")
    if data["equity"] <= 0:
        raise DaemonStateValidationError(f"Invalid non-positive equity: {data['equity']}")
    if data["peak_capital"] <= 0:
        raise DaemonStateValidationError(f"Invalid non-positive peak_capital: {data['peak_capital']}")

    return data


class SwingSQLiteLedger:
    """
    Authoritative SQLite Ledger for Overnight Swing Portfolio State.
    Enforces ACID transactions, auditability, and overnight position persistence.
    """
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_state (
                    account_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    market_date TEXT NOT NULL,
                    cash REAL NOT NULL,
                    equity REAL NOT NULL,
                    peak_capital REAL NOT NULL,
                    net_pnl REAL NOT NULL,
                    active_positions_count INTEGER NOT NULL,
                    schema_version TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS open_positions (
                    symbol TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    sector TEXT,
                    quantity INTEGER NOT NULL,
                    entry_price REAL NOT NULL,
                    current_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    allocated_capital REAL NOT NULL,
                    entry_time TEXT NOT NULL,
                    holding_period_days INTEGER NOT NULL DEFAULT 1,
                    product_type TEXT NOT NULL DEFAULT 'DELIVERY',
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trade_journal (
                    trade_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    gross_pnl REAL NOT NULL,
                    net_pnl REAL NOT NULL,
                    total_friction REAL NOT NULL,
                    dp_charge REAL NOT NULL DEFAULT 0.0,
                    exit_reason TEXT NOT NULL,
                    entry_time TEXT NOT NULL,
                    exit_time TEXT NOT NULL,
                    product_type TEXT NOT NULL DEFAULT 'DELIVERY',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS overnight_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    mark_date TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    cash REAL NOT NULL,
                    equity REAL NOT NULL,
                    positions_count INTEGER NOT NULL,
                    positions_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_open_positions_acc ON open_positions(account_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_journal_acc ON trade_journal(account_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_date ON overnight_snapshots(mark_date)")

    def persist_overnight_state(
        self,
        account_id: str,
        session_id: str,
        market_date: str,
        cash: float,
        equity: float,
        peak_capital: float,
        net_pnl: float,
        positions: Dict[str, Any],
        completed_trades: List[Dict[str, Any]],
        schema_version: str = CANONICAL_SCHEMA_VERSION,
    ):
        """Atomically persists complete portfolio snapshot and open positions overnight."""
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._get_connection() as conn:
            # 1. Upsert portfolio state
            conn.execute("""
                INSERT INTO portfolio_state (
                    account_id, session_id, market_date, cash, equity,
                    peak_capital, net_pnl, active_positions_count, schema_version, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                    session_id = excluded.session_id,
                    market_date = excluded.market_date,
                    cash = excluded.cash,
                    equity = excluded.equity,
                    peak_capital = excluded.peak_capital,
                    net_pnl = excluded.net_pnl,
                    active_positions_count = excluded.active_positions_count,
                    schema_version = excluded.schema_version,
                    updated_at = excluded.updated_at
            """, (
                account_id, session_id, market_date, round(cash, 2), round(equity, 2),
                round(peak_capital, 2), round(net_pnl, 2), len(positions), schema_version, now_ts
            ))

            # 2. Overwrite active open positions for this account
            conn.execute("DELETE FROM open_positions WHERE account_id = ?", (account_id,))
            for sym, pos in positions.items():
                p_dict = pos.to_dict() if hasattr(pos, "to_dict") else (asdict(pos) if hasattr(pos, "__dataclass_fields__") else pos)
                conn.execute("""
                    INSERT INTO open_positions (
                        symbol, account_id, sector, quantity, entry_price, current_price,
                        stop_loss, take_profit, allocated_capital, entry_time,
                        holding_period_days, product_type, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    sym,
                    account_id,
                    p_dict.get("sector", "GENERAL"),
                    int(p_dict.get("quantity", 0)),
                    float(p_dict.get("entry_price", 0.0)),
                    float(p_dict.get("current_price", p_dict.get("entry_price", 0.0))),
                    float(p_dict.get("stop_loss", 0.0)),
                    float(p_dict.get("take_profit", 0.0)),
                    float(p_dict.get("allocated_capital", 0.0)),
                    str(p_dict.get("entry_time", now_ts)),
                    int(p_dict.get("holding_period_days", 1)),
                    "DELIVERY",
                    now_ts
                ))

            # 3. Insert trades into trade_journal
            for idx, trade in enumerate(completed_trades):
                trade_id = trade.get("trade_id") or f"TRD-{market_date}-{trade.get('symbol', 'SYM')}-{idx}"
                charges = trade.get("charges")
                friction = charges.total_charges if hasattr(charges, "total_charges") else float(trade.get("friction", trade.get("total_charges", 0.0)))
                dp_charge = charges.dp_charge if hasattr(charges, "dp_charge") else float(trade.get("dp_charge", 15.34 if trade.get("direction") == "SELL" else 0.0))

                conn.execute("""
                    INSERT OR IGNORE INTO trade_journal (
                        trade_id, account_id, symbol, direction, quantity,
                        entry_price, exit_price, gross_pnl, net_pnl,
                        total_friction, dp_charge, exit_reason,
                        entry_time, exit_time, product_type, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    trade_id,
                    account_id,
                    trade.get("symbol", ""),
                    trade.get("direction", "SELL"),
                    int(trade.get("quantity", 0)),
                    float(trade.get("entry_price", 0.0)),
                    float(trade.get("exit_price", 0.0)),
                    float(trade.get("gross_pnl", 0.0)),
                    float(trade.get("net_pnl", 0.0)),
                    float(friction),
                    float(dp_charge),
                    str(trade.get("exit_reason", "")),
                    str(trade.get("entry_time", "")),
                    str(trade.get("exit_time", now_ts)),
                    "DELIVERY",
                    now_ts
                ))

            # 4. Record immutable overnight snapshot
            snapshot_id = f"SNAP-{market_date}-{account_id}"
            pos_json = json.dumps({k: (v.to_dict() if hasattr(v, "to_dict") else (asdict(v) if hasattr(v, "__dataclass_fields__") else v)) for k, v in positions.items()})
            conn.execute("""
                INSERT INTO overnight_snapshots (
                    snapshot_id, mark_date, account_id, cash, equity,
                    positions_count, positions_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(snapshot_id) DO UPDATE SET
                    cash = excluded.cash,
                    equity = excluded.equity,
                    positions_count = excluded.positions_count,
                    positions_json = excluded.positions_json,
                    created_at = excluded.created_at
            """, (
                snapshot_id, market_date, account_id, round(cash, 2), round(equity, 2),
                len(positions), pos_json, now_ts
            ))

    def load_portfolio_state(self, account_id: str) -> Optional[Dict[str, Any]]:
        """Loads latest portfolio state and open positions from SQLite ledger."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM portfolio_state WHERE account_id = ?", (account_id,)).fetchone()
            if not row:
                return None
            state = dict(row)

            # Load active positions
            pos_rows = conn.execute("SELECT * FROM open_positions WHERE account_id = ?", (account_id,)).fetchall()
            positions = {}
            for pr in pos_rows:
                p = dict(pr)
                positions[p["symbol"]] = ActiveSwingPosition(
                    symbol=p["symbol"],
                    sector=p.get("sector", "GENERAL"),
                    quantity=int(p["quantity"]),
                    entry_price=float(p["entry_price"]),
                    current_price=float(p.get("current_price", p["entry_price"])),
                    stop_loss=float(p["stop_loss"]),
                    take_profit=float(p["take_profit"]),
                    allocated_capital=float(p["allocated_capital"]),
                    entry_time=str(p["entry_time"]),
                    holding_period_days=int(p.get("holding_period_days", 1)),
                    product_type=p.get("product_type", "DELIVERY"),
                )
            state["positions"] = positions

            # Load trade count
            trades_count = conn.execute("SELECT COUNT(*) FROM trade_journal WHERE account_id = ?", (account_id,)).fetchone()[0]
            state["completed_trades_count"] = trades_count
            return state


class LiveAlgoLabDaemon:
    """
    Autonomous End-of-Day (EOD) Swing Trading Daemon for Indian Equities.
    - Operating Window: 15:00 - 15:30 IST
    - Timeframe: Daily (1d candles)
    - Stop Loss: 2.5 * ATR14 (survives overnight gap risk)
    - Take Profit: 3.5 * Risk (overcomes statutory delivery friction)
    - Position Sizing: Ed Thorp 1% capital risk rule
    - Persistence: SQLite overnight ledger ('data/swing_portfolio_ledger.db')
    - Anti-Liquidation: Intraday 15:15 square-off completely eliminated.
    """

    SWING_UNIVERSE = [
        "BHARTIARTL.NS", "ICICIBANK.NS", "INFY.NS", "ITC.NS",
        "RELIANCE.NS", "SBIN.NS", "TCS.NS", "HAL.NS", "LT.NS"
    ]

    def __init__(
        self,
        check_interval_seconds: int = 60,
        session_only: bool = True,
        loop_daily: bool = False,
        use_nifty_50: bool = True,
        strategy: str = "STRATEGY_SUPER_ADAPTIVE",
    ):
        enforce_safety_invariants()
        self.interval = check_interval_seconds
        self.session_only = session_only
        self.loop_daily = loop_daily
        self.running = True
        self.use_nifty_50 = use_nifty_50
        self.strategy = os.getenv("DAEMON_STRATEGY", strategy)

        self.universe_manager = Nifty50UniverseManager()
        if self.use_nifty_50:
            self.swing_universe = self.universe_manager.get_tickers()
            self.sector_map = self.universe_manager.get_sector_map()
        else:
            self.swing_universe = self.SWING_UNIVERSE
            self.sector_map = {"RELIANCE": "ENERGY"} # Fallback

        self.data_dir = BASE_DIR / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.data_dir / "live_portfolio_state.json"
        self.log_file = self.data_dir / "live_trades.jsonl"
        self.sqlite_ledger = SwingSQLiteLedger(self.data_dir / "swing_portfolio_ledger.db")

        self.account_id = CANONICAL_ACCOUNT_ID
        self.session_id = "STAGE31_FORWARD_PAPER_20260928_001"
        self.schema_version = CANONICAL_SCHEMA_VERSION
        self.initial_capital = 100000.0
        self.cash = 100000.0
        self.equity = 100000.0
        self.peak_capital = 100000.0
        self.net_pnl = 0.0

        # Swing Portfolio Parameters
        self.positions: Dict[str, ActiveSwingPosition] = {}
        self.completed_trades: List[Dict[str, Any]] = []
        if self.strategy == "STRATEGY_SUPER_ADAPTIVE":
            self.max_concurrent_positions: int = 3
            self.max_capital_per_position: float = 30000.0
            self.risk_per_trade_pct: float = 0.010  # Ed Thorp 1% risk rule
            self.atr_multiplier: float = 3.0        # 3.0 * ATR14 Stop Loss
            self.profit_multiplier: float = 5.0     # 5.0 * Risk Take Profit Target
            self.min_cash_reserve: float = 10000.0
        else:
            self.max_concurrent_positions: int = 2
            self.max_capital_per_position: float = 45000.0
            self.risk_per_trade_pct: float = 0.010  # Ed Thorp 1% risk rule
            self.atr_multiplier: float = 2.5        # 2.5 * ATR14 Stop Loss
            self.profit_multiplier: float = 3.5     # 3.5 * Risk Take Profit
            self.min_cash_reserve: float = 10000.0

        import yfinance as yf
        self.cached_market_data: Dict[str, Dict[str, Any]] = {}
        self.eod_candles_ingested: bool = False
        self.eod_trades_executed: bool = False
        self.summary_sent: bool = False

        self.load_state()
        self.notifier = NotificationEngine(account_id=self.account_id)

        signal.signal(signal.SIGINT, self.handle_exit)
        signal.signal(signal.SIGTERM, self.handle_exit)

    def handle_exit(self, signum, frame):
        self.running = False
        self.save_state()
        print("\n[INFO] Daemon shutdown signal received. State saved safely.")
        sys.exit(0)

    def check_startup_calendar_status(self) -> bool:
        """
        Checks if today is an official NSE trading day using exchange_calendars ('XNSE').
        If closed (weekend or holiday), prints diagnostics and returns False.
        """
        now_ist = self.get_ist_now()
        today_str = now_ist.strftime("%Y-%m-%d")
        cal = get_nse_calendar()

        if not cal.is_session(today_str):
            day_name = now_ist.strftime("%A")
            is_weekend = now_ist.weekday() >= 5
            reason = f"Weekend ({day_name})" if is_weekend else f"Official Exchange Holiday ({today_str})"
            print("=" * 80)
            print("  🏛️  ALGO LAB ZERO-INTERVENTION DAEMON - STARTUP CALENDAR CHECK")
            print("=" * 80)
            print(f"  • Date (IST):            {today_str} ({day_name})")
            print(f"  • Exchange Calendar:     XNSE (National Stock Exchange of India)")
            print(f"  • Session Status:        CLOSED ({reason})")
            print(f"  • Zero-Touch Action:     Market is closed today. Exiting gracefully with code 0.")
            print("=" * 80 + "\n")
            return False

        print(f"[XNSE CALENDAR CHECK] Date {today_str} is confirmed as an ACTIVE NSE TRADING DAY.")
        return True

    def load_state(self):
        """Loads state with primary SQLite ledger recovery, followed by JSON fallback."""
        sqlite_state = self.sqlite_ledger.load_portfolio_state(self.account_id)
        if sqlite_state:
            self.account_id = sqlite_state["account_id"]
            self.session_id = sqlite_state.get("session_id", self.session_id)
            self.schema_version = sqlite_state["schema_version"]
            self.cash = float(sqlite_state["cash"])
            self.equity = float(sqlite_state["equity"])
            self.peak_capital = float(sqlite_state["peak_capital"])
            self.net_pnl = float(sqlite_state["net_pnl"])
            self.positions = sqlite_state.get("positions", {})
            return

        if self.state_file.exists():
            try:
                raw_text = self.state_file.read_text(encoding="utf-8")
                data = json.loads(raw_text)
            except Exception as e:
                raise DaemonStateValidationError(f"Error reading state file '{self.state_file}': {e}")

            validated = validate_canonical_state(data)
            self.account_id = validated["account_id"]
            self.session_id = validated.get("session_id", self.session_id)
            self.schema_version = validated["schema_version"]
            self.cash = float(validated["cash"])
            self.peak_capital = float(validated["peak_capital"])
            self.net_pnl = float(validated["net_pnl"])
            self.equity = float(validated["equity"])
            self.positions = {}
            for sym, pos_data in validated.get("positions", {}).items():
                self.positions[sym] = ActiveSwingPosition(
                    symbol=sym,
                    sector=pos_data.get("sector", "GENERAL"),
                    quantity=int(pos_data.get("quantity", 0)),
                    entry_price=float(pos_data.get("entry_price", 0.0)),
                    current_price=float(pos_data.get("current_price", pos_data.get("entry_price", 0.0))),
                    stop_loss=float(pos_data.get("stop_loss", 0.0)),
                    take_profit=float(pos_data.get("take_profit", 0.0)),
                    allocated_capital=float(pos_data.get("allocated_capital", 0.0)),
                    entry_time=str(pos_data.get("entry_time", "")),
                    holding_period_days=int(pos_data.get("holding_period_days", 1)),
                    product_type="DELIVERY",
                )
        else:
            self.account_id = CANONICAL_ACCOUNT_ID
            self.session_id = "STAGE31_FORWARD_PAPER_20260928_001"
            self.schema_version = CANONICAL_SCHEMA_VERSION
            self.cash = self.initial_capital
            self.equity = self.initial_capital
            self.peak_capital = self.initial_capital
            self.net_pnl = 0.0
            self.positions = {}
            self.save_state()

    def save_state(self):
        """Atomically persists state to both JSON and SQLite ledger."""
        enforce_safety_invariants()
        positions_val = float(sum(p.quantity * p.current_price for p in self.positions.values()))
        self.equity = round(self.cash + positions_val, 2)
        if self.equity > self.peak_capital:
            self.peak_capital = self.equity

        market_date = self.get_ist_now().strftime("%Y-%m-%d")

        state = {
            "account_id": self.account_id,
            "session_id": self.session_id,
            "market_date": market_date,
            "schema_version": self.schema_version,
            "state_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "cash": round(self.cash, 2),
            "equity": round(self.equity, 2),
            "peak_capital": round(self.peak_capital, 2),
            "net_pnl": round(self.net_pnl, 2),
            "realized_pnl": round(self.net_pnl, 2),
            "unrealized_pnl": round(positions_val - sum(p.allocated_capital for p in self.positions.values()), 2),
            "positions": {k: v.to_dict() for k, v in self.positions.items()},
            "open_orders": [],
            "completed_trades": self.completed_trades,
            "active_positions_count": len(self.positions),
            "completed_trades_count": len(self.completed_trades),
            "product_type": "DELIVERY",
        }
        validated = validate_canonical_state(state)
        self.state_file.write_text(json.dumps(validated, indent=2), encoding="utf-8")

        # Persist to SQLite ledger
        self.sqlite_ledger.persist_overnight_state(
            account_id=self.account_id,
            session_id=self.session_id,
            market_date=market_date,
            cash=self.cash,
            equity=self.equity,
            peak_capital=self.peak_capital,
            net_pnl=self.net_pnl,
            positions=self.positions,
            completed_trades=self.completed_trades,
            schema_version=self.schema_version,
        )

    def log_trade_event(self, event_type: str, details: dict):
        entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "event_type": event_type,
            "details": details,
        }
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    @staticmethod
    def get_ist_now() -> datetime.datetime:
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        return now_utc + datetime.timedelta(hours=5, minutes=30)

    @classmethod
    def is_nse_trading_day(cls, dt: datetime.datetime | datetime.date) -> bool:
        """Validates whether dt is an official trading day via exchange_calendars ('XNSE')."""
        cal = get_nse_calendar()
        date_str = dt.strftime("%Y-%m-%d") if isinstance(dt, (datetime.datetime, datetime.date)) else str(dt)
        return bool(cal.is_session(date_str))

    @staticmethod
    def is_market_day(now_ist: datetime.datetime) -> bool:
        return now_ist.weekday() < 5

    @classmethod
    def is_within_market_hours(cls, now_ist: datetime.datetime) -> bool:
        """Returns True strictly during the EOD swing operating window: 15:00:00 to 15:30:00 IST on market days."""
        if not cls.is_market_day(now_ist):
            return False
        time_str = now_ist.strftime("%H:%M:%S")
        return "15:00:00" <= time_str < "15:30:00"

    @classmethod
    def get_next_market_start_ist(cls, now_ist: datetime.datetime) -> datetime.datetime:
        """Calculates the exact 15:00:00 IST timestamp for the next trading session."""
        target = now_ist.replace(hour=15, minute=0, second=0, microsecond=0)
        if cls.is_market_day(now_ist) and now_ist < target:
            return target

        target += datetime.timedelta(days=1)
        while target.weekday() >= 5:
            target += datetime.timedelta(days=1)
        return target

    @classmethod
    def determine_phase(cls, now_ist: datetime.datetime) -> DaemonPhase:
        """
        Evaluates current IST time and transitions autonomously through the EOD Swing lifecycle:
        - OFF_HOURS (< 15:00:00 IST)
        - EOD_CANDLE_INGESTION (15:00:00 - 15:15:00 IST)
        - EOD_TRADE_EXECUTION (15:15:00 - 15:25:00 IST)
        - EOD_PERSISTENCE (15:25:00 - 15:30:00 IST)
        - SESSION_COMPLETED (15:30:00+ IST)
        """
        time_str = now_ist.strftime("%H:%M:%S")
        if time_str < "15:00:00":
            return DaemonPhase.OFF_HOURS
        elif "15:00:00" <= time_str < "15:15:00":
            return DaemonPhase.EOD_CANDLE_INGESTION
        elif "15:15:00" <= time_str < "15:25:00":
            return DaemonPhase.EOD_TRADE_EXECUTION
        elif "15:25:00" <= time_str < "15:30:00":
            return DaemonPhase.EOD_PERSISTENCE
        else:
            return DaemonPhase.SESSION_COMPLETED

    def ingest_near_close_daily_candles(self) -> int:
        """
        Ingests near-close daily (1d) candles for swing universe.
        Calculates ATR14, EMA5, EMA8, and EMA13 for CFI Fibonacci Strategy.
        """
        ingested_count = 0
        for sym in self.swing_universe:
            try:
                df = yf.download(sym, period="250d", interval="1d", progress=False)
                if df.empty or len(df) < 20:
                    continue

                # Calculate indicators
                high = df["High"].squeeze()
                low = df["Low"].squeeze()
                close = df["Close"].squeeze()
                vol_series = df["Volume"].squeeze()

                tr1 = high - low
                tr2 = (high - close.shift(1)).abs()
                tr3 = (low - close.shift(1)).abs()
                tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
                atr14 = float(tr.rolling(14).mean().iloc[-1])

                # ALGO LAB UPGRADE: Multi-Regime & Donchian Breakout Indicators
                sma20_series = close.rolling(20).mean()
                sma50_series = close.rolling(50).mean()
                sma200_series = close.rolling(200).mean()
                
                sma20 = float(np.asarray(sma20_series).flatten()[-1])
                sma50 = float(np.asarray(sma50_series).flatten()[-1])
                sma200 = float(np.asarray(sma200_series).flatten()[-1])
                
                prev_sma20 = float(np.asarray(sma20_series).flatten()[-2])
                prev_sma50 = float(np.asarray(sma50_series).flatten()[-2])

                current_price = float(np.asarray(close).flatten()[-1])
                high_price = float(np.asarray(high).flatten()[-1])
                low_price = float(np.asarray(low).flatten()[-1])

                # Donchian 50d high and 20d low levels
                high_50s = high.shift(1).rolling(50).max()
                low_20s = low.shift(1).rolling(20).min()
                h_50 = float(np.asarray(high_50s).flatten()[-1]) if len(high_50s) >= 50 and not np.isnan(high_50s.iloc[-1]) else high_price
                l_20 = float(np.asarray(low_20s).flatten()[-1]) if len(low_20s) >= 20 and not np.isnan(low_20s.iloc[-1]) else low_price

                # Volume SMA 20
                vol_sma20_series = vol_series.rolling(20).mean()
                curr_vol = float(np.asarray(vol_series).flatten()[-1]) if not vol_series.empty else 0.0
                vol_sma20 = float(np.asarray(vol_sma20_series).flatten()[-1]) if len(vol_sma20_series) >= 20 and not np.isnan(vol_sma20_series.iloc[-1]) else max(1.0, curr_vol)

                # 60-day Momentum
                mom60 = float((current_price / close.iloc[-60]) - 1.0) if len(close) >= 60 and close.iloc[-60] > 0 else 0.0

                # ADX 14 calculation
                plus_dm_raw = high.diff()
                minus_dm_raw = low.diff().abs()
                plus_dm = pd.Series(np.where((plus_dm_raw > minus_dm_raw) & (plus_dm_raw > 0), plus_dm_raw, 0.0), index=df.index)
                minus_dm = pd.Series(np.where((minus_dm_raw > plus_dm_raw) & (minus_dm_raw > 0), minus_dm_raw, 0.0), index=df.index)
                tr_sum = tr.rolling(14).sum()
                plus_di = 100 * (plus_dm.rolling(14).sum() / (tr_sum + 1e-6))
                minus_di = 100 * (minus_dm.rolling(14).sum() / (tr_sum + 1e-6))
                dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-6))
                adx14 = float(dx.rolling(14).mean().iloc[-1]) if len(dx) >= 28 and not np.isnan(dx.iloc[-1]) else 20.0

                # 🧠 QUANTAMENTAL UPGRADE: Apply Fundamental Filter
                fundamental_pass = False
                try:
                    info = yf.Ticker(sym).info
                    roe = info.get('returnOnEquity', 0)
                    rev_growth = info.get('revenueGrowth', 0)
                    roe = roe if roe is not None else 0
                    rev_growth = rev_growth if rev_growth is not None else 0
                    if roe >= 0.15 and rev_growth > 0:
                        fundamental_pass = True
                except:
                    pass

                # Strategy Signal Selection
                if self.strategy == "STRATEGY_SUPER_ADAPTIVE":
                    is_uptrend = (current_price > sma200) and (sma50 > sma200)
                    is_breakout = (current_price >= h_50)
                    is_vol_confirmed = (curr_vol >= vol_sma20 * 1.05)
                    is_trend_strength = (adx14 >= 15.0)
                    buy_signal = is_uptrend and is_breakout and is_vol_confirmed and is_trend_strength and fundamental_pass
                else:
                    technical_signal = (prev_sma20 <= prev_sma50) and (sma20 > sma50) and (current_price > sma200)
                    buy_signal = technical_signal and fundamental_pass
                signal_val = 1 if buy_signal else 0

                # Candle freshness & completeness validation
                now_ist = self.get_ist_now()
                candle_time = df.index[-1]
                # If market hasn't closed (15:30 IST), today's candle is developing
                is_developing = now_ist.time() < datetime.time(15, 30) and candle_time.date() == now_ist.date()
                candle_status = "developing" if is_developing else "completed"

                self.cached_market_data[sym] = {
                    "price": current_price,
                    "high": high_price,
                    "low": low_price,
                    "atr14": atr14,
                    "sma20": sma20,
                    "sma50": sma50,
                    "sma200": sma200,
                    "prev_sma20": prev_sma20,
                    "prev_sma50": prev_sma50,
                    "h_50": h_50,
                    "l_20": l_20,
                    "curr_vol": curr_vol,
                    "vol_sma20": vol_sma20,
                    "mom60": mom60,
                    "adx14": adx14,
                    "signal": signal_val,
                    "candle_status": candle_status,
                    "candle_timestamp": candle_time.isoformat(),
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
                ingested_count += 1
            except Exception as e:
                print(f"[WARN] Error fetching daily candle for {sym}: {e}")

        return ingested_count

    def execute_eod_trades(self, timestamp_str: str) -> List[str]:
        """
        Executes EOD trades:
        1. Evaluates open positions against 2.5 * ATR14 Trailing Stop Loss, 3.5 * Risk Take Profit, and CFI 5-8-13 exit.
        2. Does NOT square off surviving positions — holds them overnight!
        3. Scans for new swing entries with 1% fixed-fractional risk per trade and delivery statutory taxes.
        """
        actions = []

        # 1. Evaluate open positions for Exits
        for sym in list(self.positions.keys()):
            pos = self.positions[sym]
            market_info = self.cached_market_data.get(sym)
            current_price = market_info["price"] if market_info else pos.entry_price
            pos.current_price = current_price

            # Trailing stop mechanism (Highest High since entry)
            highest_high = getattr(pos, "highest_high", pos.entry_price)
            if market_info and market_info.get("high"):
                highest_high = max(highest_high, market_info["high"])
            setattr(pos, "highest_high", highest_high)
            
            # Asymmetric ratchet & exit mechanism for STRATEGY_SUPER_ADAPTIVE
            if self.strategy == "STRATEGY_SUPER_ADAPTIVE":
                gain = highest_high - pos.entry_price
                init_sl = getattr(pos, "initial_sl", pos.stop_loss)
                r = pos.entry_price - init_sl
                if r > 0:
                    if gain >= 1.5 * r:
                        # Ratchet to breakeven + 0.5% (covers STT, DP charge, slippage)
                        pos.stop_loss = max(pos.stop_loss, round(pos.entry_price * 1.005, 2))
                    if gain >= 3.0 * r:
                        # Lock in 1.5R minimum profit
                        pos.stop_loss = max(pos.stop_loss, round(pos.entry_price + (1.5 * r), 2))
                    if gain >= 5.0 * r:
                        # Chandelier trail from highest high
                        if market_info and market_info.get("atr14"):
                            pos.stop_loss = max(pos.stop_loss, round(highest_high - (2.0 * market_info["atr14"]), 2))

                # Donchian 20-day low breach exit
                l_20 = market_info.get("l_20") if market_info else None
                if l_20 is not None and current_price <= l_20:
                    exit_reason = "DONCHIAN_20D_EXIT"
            elif market_info and market_info.get("atr14"):
                trailing_sl = highest_high - (self.atr_multiplier * market_info["atr14"])
                pos.stop_loss = max(pos.stop_loss, round(trailing_sl, 2))

            exit_reason = None
            if current_price <= pos.stop_loss:
                exit_reason = "TRAILING_STOP_LOSS_HIT"
            elif current_price >= pos.take_profit:
                exit_reason = "TAKE_PROFIT_HIT"
            elif self.strategy == "STRATEGY_SUPER_ADAPTIVE":
                l_20 = market_info.get("l_20") if market_info else None
                if l_20 is not None and current_price <= l_20:
                    exit_reason = "DONCHIAN_20D_EXIT"
            elif market_info:
                # CFI 5-8-13 Technical Exit: Sell when 5 EMA crosses below 13 EMA
                sma20 = market_info.get("sma20")
                sma50 = market_info.get("sma50")
                prev_sma20 = market_info.get("prev_sma20")
                prev_sma50 = market_info.get("prev_sma50")
                
                if sma20 and sma50 and prev_sma20 and prev_sma50:
                    if prev_sma20 >= prev_sma50 and sma20 < sma50:
                        exit_reason = "CFI_FIBONACCI_CROSS_EXIT"

            if exit_reason:
                # Close position with statutory delivery friction (including ₹15.34 DP charge)
                friction_info = calculate_delivery_statutory_friction(
                    buy_price=pos.entry_price,
                    sell_price=current_price,
                    quantity=pos.quantity
                )
                gross_pnl = round((current_price - pos.entry_price) * pos.quantity, 2)
                net_pnl = round(gross_pnl - friction_info["total_charges"], 2)
                recovered_cash = round((pos.quantity * current_price) - friction_info["total_charges"], 2)

                self.cash = round(self.cash + recovered_cash, 2)
                self.net_pnl = round(self.net_pnl + net_pnl, 2)

                trade_record = {
                    "symbol": sym,
                    "sector": pos.sector,
                    "direction": "SELL",
                    "quantity": pos.quantity,
                    "entry_price": pos.entry_price,
                    "exit_price": current_price,
                    "gross_pnl": gross_pnl,
                    "net_pnl": net_pnl,
                    "friction": friction_info["total_charges"],
                    "dp_charge": friction_info["dp_charge"],
                    "exit_reason": exit_reason,
                    "entry_time": pos.entry_time,
                    "exit_time": timestamp_str,
                    "product_type": "DELIVERY",
                }
                self.completed_trades.append(trade_record)
                self.log_trade_event("POSITION_CLOSED", trade_record)
                self.notifier.send_trade_alert(
                    action="SELL",
                    symbol=sym,
                    quantity=pos.quantity,
                    price=current_price,
                    net_pnl=net_pnl,
                    gross_pnl=gross_pnl,
                    exit_reason=exit_reason,
                    sector=pos.sector,
                    holding_period_days=pos.holding_period_days,
                    friction=friction_info["total_charges"],
                )
                del self.positions[sym]
                actions.append(f"Closed {sym} [{exit_reason}]: Net P&L ₹{net_pnl:,.2f}")
            else:
                # SURVIVES: Remains OPEN and held overnight!
                pos.holding_period_days += 1

        # 2. Check for new swing entries if capacity exists
        if self.strategy == "STRATEGY_SUPER_ADAPTIVE":
            candidate_items = sorted(
                self.cached_market_data.items(),
                key=lambda x: x[1].get("mom60", 0.0),
                reverse=True
            )
        else:
            candidate_items = list(self.cached_market_data.items())

        if len(self.positions) < self.max_concurrent_positions and self.cash >= 15000.0:
            for sym, data in candidate_items:
                if len(self.positions) >= self.max_concurrent_positions:
                    break
                if sym in self.positions:
                    continue

                sector = self.sector_map.get(sym, "GENERAL")
                active_sectors = [p.sector for p in self.positions.values()]
                if sector in active_sectors:
                    continue

                if data.get("signal", 0) == 1:
                    price = data.get("price")
                    if not price:
                        continue
                    atr14 = data.get("atr14", price * 0.015)
                    stop_distance = max(atr14 * self.atr_multiplier, price * 0.02)
                    stop_loss = round(price - stop_distance, 2)
                    take_profit = round(price + (stop_distance * self.profit_multiplier), 2)

                    import math
                    if not (math.isfinite(price) and math.isfinite(atr14) and math.isfinite(stop_distance)):
                        continue
                    if price <= 0 or stop_distance <= 0.0 or atr14 <= 0:
                        continue

                    # 1% fixed-fractional risk per trade
                    total_equity = self.cash + sum(p.quantity * p.current_price for p in self.positions.values())
                    if not math.isfinite(total_equity) or total_equity <= 0:
                        continue
                        
                    risk_capital = total_equity * self.risk_per_trade_pct
                    shares_by_risk = int(risk_capital / stop_distance)
                    
                    # Respect cash limits: preserve a configurable minimum cash reserve
                    min_cash_reserve = getattr(self, "min_cash_reserve", 10000.0)
                    max_spend = min(self.max_capital_per_position, max(0.0, self.cash - min_cash_reserve))
                    shares_by_cash = int(max_spend / price)
                    
                    qty = max(0, min(shares_by_risk, shares_by_cash))
                    
                    if qty == 0:
                        continue

                    cost = round(qty * price, 2)
                    if cost <= self.cash - 5000.0:
                        new_pos = ActiveSwingPosition(
                            symbol=sym,
                            sector=sector,
                            quantity=qty,
                            entry_price=price,
                            current_price=price,
                            stop_loss=stop_loss,
                            take_profit=take_profit,
                            allocated_capital=cost,
                            entry_time=timestamp_str,
                            holding_period_days=1,
                            product_type="DELIVERY",
                        )
                        setattr(new_pos, "initial_sl", stop_loss)
                        setattr(new_pos, "highest_high", price)
                        self.positions[sym] = new_pos
                        self.cash = round(self.cash - cost, 2)
                        trade_record = {
                            "symbol": sym,
                            "sector": sector,
                            "direction": "BUY",
                            "quantity": qty,
                            "entry_price": price,
                            "stop_loss": stop_loss,
                            "take_profit": take_profit,
                            "allocated_capital": cost,
                            "entry_time": timestamp_str,
                            "product_type": "DELIVERY",
                        }
                        self.log_trade_event("POSITION_OPENED", trade_record)
                        self.notifier.send_trade_alert(
                            action="BUY",
                            symbol=sym,
                            quantity=qty,
                            price=price,
                            stop_loss=stop_loss,
                            take_profit=take_profit,
                            sector=sector,
                        )
                        actions.append(f"Opened Swing {sym}: {qty} shares @ ₹{price:,.2f} (SL: ₹{stop_loss}, TP: ₹{take_profit})")

        return actions

    def step(self) -> int:
        """
        Executes a single step of the EOD Swing state machine.
        Transitions autonomously through the End-of-Day trading lifecycle.
        """
        enforce_safety_invariants()
        now_ist = self.get_ist_now()
        timestamp_str = now_ist.strftime("%Y-%m-%d %H:%M:%S")
        date_str = now_ist.strftime("%Y-%m-%d")

        # 1. Exchange Holiday & Weekend Check via exchange_calendars ('XNSE')
        if not self.is_nse_trading_day(now_ist):
            print(f"[{timestamp_str} IST] Market is CLOSED today per XNSE calendar. Zero intervention needed.")
            if self.session_only or not self.loop_daily:
                self.running = False
                return 0
            next_start = self.get_next_market_start_ist(now_ist)
            return int((next_start - now_ist).total_seconds())

        # 2. Time-Based State Machine Transition
        phase = self.determine_phase(now_ist)

        # STATE 1: OFF_HOURS (Before 15:00 IST)
        if phase == DaemonPhase.OFF_HOURS:
            self.summary_sent = False
            self.eod_candles_ingested = False
            self.eod_trades_executed = False
            target_start = now_ist.replace(hour=15, minute=0, second=0, microsecond=0)
            wait_sec = int((target_start - now_ist).total_seconds())
            hours, rem = divmod(wait_sec, 3600)
            mins, _ = divmod(rem, 60)
            print(f"[{timestamp_str} IST] Phase: OFF_HOURS | Standing by until 15:00:00 IST EOD wakeup ({hours}h {mins}m remaining)")
            return min(wait_sec, 300)

        # STATE 2: EOD_CANDLE_INGESTION (15:00 - 15:15 IST)
        elif phase == DaemonPhase.EOD_CANDLE_INGESTION:
            if not self.eod_candles_ingested:
                print(f"[{timestamp_str} IST] Phase: EOD_CANDLE_INGESTION (15:00) | Waking up. Ingesting near-close daily (1d) candles & computing ATR14/Signals...")
                self.notifier.send_info(
                    f"EOD Scan Initiated for {len(self.swing_universe)} Nifty Universe. Ingesting near-close 1d candles & calculating ATR/momentum signals..."
                )
                ingested = self.ingest_near_close_daily_candles()
                self.eod_candles_ingested = True
                print(f"[{timestamp_str} IST] Phase: EOD_CANDLE_INGESTION | Ingestion complete for {ingested} universe tickers.")
            else:
                print(f"[{timestamp_str} IST] Phase: EOD_CANDLE_INGESTION | Daily candles ready. Standing by for 15:15 EOD trade execution window.")
            self.save_state()
            return self.interval

        # STATE 3: EOD_TRADE_EXECUTION (15:15 - 15:25 IST)
        elif phase == DaemonPhase.EOD_TRADE_EXECUTION:
            # 1. Enforce mandatory 15:15 IST auto-square-off for any active intraday paper sessions
            intraday_db = BASE_DIR / "data" / "paper_intraday_sessions.db"
            if intraday_db.exists():
                try:
                    from services.paper_engine.session import PaperTradingEngine, SessionStatus
                    from services.paper_engine.trailing_stop_engine import TrailingStopEngine
                    p_engine = PaperTradingEngine(str(intraday_db))
                    for sess in p_engine.list_sessions():
                        if sess.status == SessionStatus.RUNNING and sess.portfolio.positions:
                            t_engine = TrailingStopEngine(p_engine, sess.session_id)
                            sq_results = t_engine.auto_square_off_all_positions(reason="AUTO_SQUARE_OFF_1515_IST")
                            if sq_results:
                                print(f"[{timestamp_str} IST] 🚨 Auto-squared off {len(sq_results)} intraday positions in session {sess.session_id}")
                except Exception as e:
                    print(f"[{timestamp_str} IST] [WARN] Intraday square-off hook exception: {e}")

            if not self.cached_market_data:
                self.ingest_near_close_daily_candles()

            actions = self.execute_eod_trades(timestamp_str)
            active_count = len(self.positions)
            cash_val = self.cash
            equity_val = self.equity
            print(
                f"[{timestamp_str} IST] Phase: EOD_TRADE_EXECUTION (15:15-15:25) | Positions: {active_count} | "
                f"Cash: ₹{cash_val:,.2f} | Equity: ₹{equity_val:,.2f} | Actions: {actions if actions else 'Holding overnight swing positions'}"
            )
            self.eod_trades_executed = True
            self.save_state()
            return self.interval

        # STATE 4: EOD_PERSISTENCE (15:25 - 15:30 IST)
        elif phase == DaemonPhase.EOD_PERSISTENCE:
            self.save_state()
            print(
                f"[{timestamp_str} IST] Phase: EOD_PERSISTENCE (15:25-15:30) | "
                f"Successfully committed {len(self.positions)} open positions to SQLite ledger ('swing_portfolio_ledger.db'). "
                f"All positions held overnight safely with 2.5*ATR14 stops."
            )
            return self.interval

        # STATE 5: SESSION_COMPLETED (15:30+ IST)
        else:
            self.save_state()
            if not self.summary_sent:
                self.notifier.send_summary(
                    active_positions_count=len(self.positions),
                    cash=self.cash,
                    equity=self.equity,
                    net_pnl=self.net_pnl,
                    completed_trades_count=len(self.completed_trades),
                    market_date=date_str,
                )
                self.summary_sent = True

            print(
                f"[{timestamp_str} IST] Phase: SESSION_COMPLETED (15:30+) | "
                f"EOD swing trading session finished cleanly. Equity: ₹{self.equity:,.2f}, Net P&L: ₹{self.net_pnl:,.2f}. "
                f"Positions held overnight: {len(self.positions)}."
            )
            if self.session_only or not self.loop_daily:
                print(f"[{timestamp_str} IST] Clean shutdown complete. Exiting with code 0.")
                self.running = False
                return 0

            next_start = self.get_next_market_start_ist(now_ist)
            wait_sec = int((next_start - now_ist).total_seconds())
            hours, rem = divmod(wait_sec, 3600)
            mins, _ = divmod(rem, 60)
            print(f"[{timestamp_str} IST] Standing by for next session: {next_start.strftime('%Y-%m-%d %H:%M')} IST ({hours}h {mins}m remaining)")
            return wait_sec

    def run_forever(self):
        print("=" * 80)
        print("  🏛️  ALGO LAB ZERO-INTERVENTION EOD SWING TRADING DAEMON (NSE/BSE)")
        print("=" * 80)
        print("  Exchange Calendar:       XNSE (exchange_calendars)")
        print("  Trading Strategy:        Swing Trading (Delivery / CNC)")
        print("  Timeframe:               Daily (1d near-close candles)")
        print("  Risk Controls:           Ed Thorp 1% Risk Sizing | 2.5*ATR14 Stop Loss")
        print("  Profit Multiplier:       3.5 * Risk (Overcomes statutory delivery friction)")
        print("  Overnight Persistence:   SQLite Ledger ('data/swing_portfolio_ledger.db')")
        print("  Autonomous Lifecycle:    15:00 (Wakeup/Ingest) -> 15:15 (EOD Execution)")
        print("                           -> 15:25 (Overnight Persistence) -> 15:30 (Completion)")
        print("  Operating Mode:          Zero Human Intervention")
        print("=" * 80 + "\n")

        # 1. Automatic Startup Calendar Verification
        if not self.check_startup_calendar_status():
            sys.exit(0)

        # 2. Main Autonomous State Machine Loop
        while self.running:
            try:
                sleep_sec = self.step()
                if not self.running:
                    break

                actual_sleep = min(sleep_sec if sleep_sec else self.interval, 300)
                time.sleep(actual_sleep)
            except Exception as e:
                print(f"[ERROR] Live daemon exception: {e}")
                time.sleep(self.interval)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Algo Lab Autonomous EOD Swing Market Daemon (Zero-Touch)")
    parser.add_argument("--interval", type=int, default=60, help="Polling interval in seconds (default: 60)")
    parser.add_argument("--session-only", action="store_true", default=True, help="Run only current day session through 15:30 IST and exit (default: True)")
    parser.add_argument("--loop-daily", action="store_true", default=False, help="Keep running indefinitely across multiple market days")
    parser.add_argument("--once", action="store_true", help="Execute single state machine tick and exit")

    args = parser.parse_args()

    daemon = LiveAlgoLabDaemon(
        check_interval_seconds=args.interval,
        session_only=not args.loop_daily,
        loop_daily=args.loop_daily,
    )

    if args.once:
        daemon.step()
    else:
        daemon.run_forever()


if __name__ == "__main__":
    main()
