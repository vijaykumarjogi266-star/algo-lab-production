"""
QUANT-OS Stage 6 - NSE Calendar Integration Service (calendar_service.py)
Provides authoritative validation of National Stock Exchange (NSE) of India
holiday schedule, weekend exclusions, regular market hours (09:00 - 15:30 IST),
and 08:00 AM IST dynamic morning shift verification.
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, Any, Optional, Set, Tuple
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal

IST_TZ = ZoneInfo("Asia/Kolkata")

# Standard NSE Session Times (IST)
PRE_MARKET_START = time(9, 0)
PRE_MARKET_END = time(9, 15)
REGULAR_MARKET_START = time(9, 15)
REGULAR_MARKET_END = time(15, 30)

OFFICIAL_HOLIDAYS_NSE: Set[date] = {
    date(2024, 1, 26), date(2024, 3, 8), date(2024, 3, 25), date(2024, 4, 11),
    date(2024, 4, 17), date(2024, 5, 1), date(2024, 6, 17), date(2024, 7, 17),
    date(2024, 8, 15), date(2024, 10, 2), date(2024, 11, 1), date(2024, 11, 15),
    date(2024, 12, 25),
    # 2025
    date(2025, 1, 26), date(2025, 3, 14), date(2025, 3, 31), date(2025, 4, 10),
    date(2025, 4, 14), date(2025, 4, 18), date(2025, 5, 1), date(2025, 6, 7),
    date(2025, 8, 15), date(2025, 10, 2), date(2025, 10, 21), date(2025, 11, 1),
    date(2025, 12, 25),
    # 2026
    date(2026, 1, 26), date(2026, 3, 3), date(2026, 3, 20), date(2026, 4, 3),
    date(2026, 4, 14), date(2026, 5, 1), date(2026, 5, 27), date(2026, 8, 15),
    date(2026, 10, 2), date(2026, 11, 8), date(2026, 11, 24), date(2026, 12, 25),
}


class NSECalendarService:
    """Provides authoritative validation for NSE India market calendar and sessions."""

    def __init__(self, custom_holidays: Optional[Set[date]] = None):
        try:
            self.mcal_nse = mcal.get_calendar("NSE")
        except Exception:
            self.mcal_nse = None
        self.holidays = custom_holidays or OFFICIAL_HOLIDAYS_NSE

    def to_ist(self, dt: Optional[datetime] = None) -> datetime:
        """Converts datetime to Indian Standard Time (Asia/Kolkata)."""
        if dt is None:
            dt = datetime.now(timezone.utc)
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(IST_TZ)

    def is_trading_day(self, dt: Optional[datetime | date] = None) -> bool:
        """Determines if a given calendar day is a scheduled trading day (Mon-Fri, non-holiday)."""
        if dt is None:
            dt = self.to_ist()
        d = dt.date() if isinstance(dt, datetime) else dt

        # 1. Day of Week Guard: Saturday (5) or Sunday (6)
        if d.weekday() >= 5:
            return False

        # 2. Official Holiday Guard
        if d in self.holidays:
            return False

        # 3. pandas_market_calendars cross-check
        if self.mcal_nse is not None:
            try:
                sched = self.mcal_nse.schedule(start_date=d, end_date=d)
                if sched.empty:
                    return False
            except Exception:
                pass

        return True

    def get_market_status(self, dt: Optional[datetime] = None) -> Dict[str, Any]:
        """Returns market phase and openness status."""
        ist_dt = self.to_ist(dt)
        d = ist_dt.date()
        t = ist_dt.time()

        if not self.is_trading_day(d):
            reason = f"Weekend ({d.strftime('%A')})" if d.weekday() >= 5 else f"Official Exchange Holiday ({d.strftime('%Y-%m-%d')})"
            return {
                "is_trading_day": False,
                "is_market_open": False,
                "phase": "MARKET_CLOSED",
                "reason": f"Market Closed: {reason}",
                "timestamp_ist": ist_dt.isoformat(),
            }

        if t < PRE_MARKET_START:
            return {
                "is_trading_day": True,
                "is_market_open": False,
                "phase": "PRE_0900_IDLE",
                "reason": f"Before Pre-Market Ritual ({t.strftime('%H:%M:%S')} < 09:00:00 IST)",
                "timestamp_ist": ist_dt.isoformat(),
            }
        elif PRE_MARKET_START <= t < REGULAR_MARKET_START:
            return {
                "is_trading_day": True,
                "is_market_open": False,
                "phase": "PRE_MARKET_RITUAL",
                "reason": "Pre-Market Phase (09:00 - 09:15 IST)",
                "timestamp_ist": ist_dt.isoformat(),
            }
        elif REGULAR_MARKET_START <= t <= REGULAR_MARKET_END:
            return {
                "is_trading_day": True,
                "is_market_open": True,
                "phase": "ACTIVE_TRADING_SESSION",
                "reason": "Regular NSE Trading Session (09:15 - 15:30 IST)",
                "timestamp_ist": ist_dt.isoformat(),
            }
        else:
            return {
                "is_trading_day": True,
                "is_market_open": False,
                "phase": "POST_MARKET_CLOSE",
                "reason": f"After Market Close ({t.strftime('%H:%M:%S')} > 15:30:00 IST)",
                "timestamp_ist": ist_dt.isoformat(),
            }

    def verify_morning_dynamic_shift(self, dt: Optional[datetime] = None) -> Dict[str, Any]:
        """08:00 AM IST Morning Dynamic-Shift Guard."""
        ist_dt = self.to_ist(dt)
        is_trade_day = self.is_trading_day(ist_dt)
        reason = "Valid Trading Day" if is_trade_day else ("Weekend" if ist_dt.weekday() >= 5 else "Exchange Holiday")
        return {
            "check_time_ist": ist_dt.isoformat(),
            "target_date": ist_dt.date().strftime("%Y-%m-%d"),
            "day_of_week": ist_dt.strftime("%A"),
            "is_trading_day": is_trade_day,
            "reason": reason,
            "decision": "SCHEDULE_PREFLIGHT" if is_trade_day else "SKIP_TO_EOD_CLOSED",
        }
