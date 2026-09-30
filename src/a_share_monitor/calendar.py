from __future__ import annotations

from datetime import date
import pandas as pd


def is_trading_day(day: date) -> tuple[bool, str]:
    """Primary: exchange_calendars XSHG. Fallback: weekday check."""
    try:
        import exchange_calendars as xcals
        cal = xcals.get_calendar("XSHG")
        ts = pd.Timestamp(day.isoformat())
        return bool(cal.is_session(ts)), "exchange_calendars:XSHG"
    except Exception:
        return day.weekday() < 5, "weekday_fallback"
