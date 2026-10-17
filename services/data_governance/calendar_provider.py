"""Algo Lab Versioned Market Calendar & Session Provider Interface.

Workstream E Compliance:
- Decouples hardcoded year lists into versioned calendar provider interface.
- Supports regular sessions, weekend exclusions, official exchange holidays,
  and special trading sessions (e.g. Diwali Muhurat Trading).
- Provides deterministic session bounds and next-trading-day calculations.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Dict, Optional, Set, Tuple
from zoneinfo import ZoneInfo

IST_TZ = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class SpecialSession:
    """Special trading session (e.g. Diwali Muhurat trading) with custom start/end times."""
    name: str
    session_date: date
    start_time: time
    end_time: time


class CalendarProvider(ABC):
    """Authoritative abstract interface for exchange market calendars."""

    @abstractmethod
    def is_trading_day(self, dt: datetime | date) -> bool:
        """Returns True if the date is a regular trading day or special session day."""
        pass

    @abstractmethod
    def is_holiday(self, dt: datetime | date) -> bool:
        """Returns True if the date is an exchange holiday."""
        pass

    @abstractmethod
    def is_special_session(self, dt: datetime | date) -> bool:
        """Returns True if date has special market hours."""
        pass

    @abstractmethod
    def get_session_bounds(self, dt: datetime | date) -> Tuple[time, time]:
        """Returns (start_time, end_time) in IST for the given date."""
        pass

    @abstractmethod
    def is_regular_trading_session(self, dt: datetime) -> bool:
        """Returns True if the timestamp falls within active market hours."""
        pass

    @abstractmethod
    def get_next_trading_day(self, dt: datetime | date) -> date:
        """Returns the next valid trading date after dt."""
        pass


class VersionedMarketCalendarProvider(CalendarProvider):
    """
    Versioned Indian Equity (NSE/BSE) Market Calendar Provider.
    
    Supports versioned holiday datasets, special session registries, and session rules.
    """

    DEFAULT_CALENDAR_VERSION = "2024-2026.1"

    # Default Standard IST Equity Hours
    DEFAULT_OPEN = time(9, 15)
    DEFAULT_CLOSE = time(15, 30)

    # Versioned holiday records
    DEFAULT_HOLIDAYS: Set[date] = {
        # 2024
        date(2024, 1, 26), date(2024, 3, 8), date(2024, 3, 25), date(2024, 4, 11),
        date(2024, 4, 17), date(2024, 5, 1), date(2024, 6, 17), date(2024, 7, 17),
        date(2024, 8, 15), date(2024, 10, 2), date(2024, 11, 1), date(2024, 11, 15),
        date(2024, 12, 25),
        # 2025
        date(2025, 1, 26), date(2025, 3, 14), date(2025, 3, 31), date(2025, 4, 14),
        date(2025, 5, 1), date(2025, 8, 15), date(2025, 10, 2), date(2025, 10, 21),
        date(2025, 11, 5), date(2025, 12, 25),
        # 2026
        date(2026, 1, 26), date(2026, 3, 6), date(2026, 3, 20), date(2026, 4, 3),
        date(2026, 5, 1), date(2026, 8, 15), date(2026, 10, 2), date(2026, 11, 8),
        date(2026, 12, 25),
    }

    # Special session definitions (e.g. Diwali Muhurat trading sessions)
    DEFAULT_SPECIAL_SESSIONS: Dict[date, SpecialSession] = {
        date(2024, 11, 1): SpecialSession(
            name="Diwali Muhurat Trading 2024",
            session_date=date(2024, 11, 1),
            start_time=time(18, 0),
            end_time=time(19, 0),
        ),
        date(2025, 10, 21): SpecialSession(
            name="Diwali Muhurat Trading 2025",
            session_date=date(2025, 10, 21),
            start_time=time(18, 15),
            end_time=time(19, 15),
        ),
        date(2026, 11, 8): SpecialSession(
            name="Diwali Muhurat Trading 2026",
            session_date=date(2026, 11, 8),
            start_time=time(18, 15),
            end_time=time(19, 15),
        ),
    }

    def __init__(
        self,
        version: str = DEFAULT_CALENDAR_VERSION,
        holidays: Optional[Set[date]] = None,
        special_sessions: Optional[Dict[date, SpecialSession]] = None,
    ):
        self.version = version
        self.holidays: Set[date] = holidays if holidays is not None else set(self.DEFAULT_HOLIDAYS)
        self.special_sessions: Dict[date, SpecialSession] = (
            special_sessions if special_sessions is not None else dict(self.DEFAULT_SPECIAL_SESSIONS)
        )

    def is_holiday(self, dt: datetime | date) -> bool:
        d = dt.date() if isinstance(dt, datetime) else dt
        # If there is a special session on that date (e.g. Muhurat), it's traded despite being a holiday
        if d in self.special_sessions:
            return False
        return d in self.holidays

    def is_weekend(self, dt: datetime | date) -> bool:
        d = dt.date() if isinstance(dt, datetime) else dt
        return d.weekday() >= 5

    def is_special_session(self, dt: datetime | date) -> bool:
        d = dt.date() if isinstance(dt, datetime) else dt
        return d in self.special_sessions

    def is_trading_day(self, dt: datetime | date) -> bool:
        d = dt.date() if isinstance(dt, datetime) else dt
        if d in self.special_sessions:
            return True
        if self.is_weekend(d):
            return False
        return d not in self.holidays

    def get_session_bounds(self, dt: datetime | date) -> Tuple[time, time]:
        d = dt.date() if isinstance(dt, datetime) else dt
        if d in self.special_sessions:
            spec = self.special_sessions[d]
            return spec.start_time, spec.end_time
        return self.DEFAULT_OPEN, self.DEFAULT_CLOSE

    def is_regular_trading_session(self, dt: datetime) -> bool:
        if dt.tzinfo is None:
            ist_dt = dt.replace(tzinfo=IST_TZ)
        else:
            ist_dt = dt.astimezone(IST_TZ)

        d = ist_dt.date()
        if not self.is_trading_day(d):
            return False

        start_t, end_t = self.get_session_bounds(d)
        cur_t = ist_dt.time()
        return start_t <= cur_t <= end_t

    def get_next_trading_day(self, dt: datetime | date) -> date:
        current = (dt.date() if isinstance(dt, datetime) else dt) + timedelta(days=1)
        while not self.is_trading_day(current):
            current += timedelta(days=1)
        return current


# Default shared calendar provider
default_calendar_provider = VersionedMarketCalendarProvider()
