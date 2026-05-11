"""
Indian market calendar utilities.
NSE/BSE trading hours: 9:15 AM - 3:30 PM IST, Mon-Fri.
Handles weekends and basic market hour checks.
"""

from datetime import datetime, time, date
import pytz

IST = pytz.timezone("Asia/Kolkata")

# NSE/BSE trading window in IST
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)

# Known NSE holidays 2025 (extend as needed)
# Source: NSE official holiday calendar
NSE_HOLIDAYS_2025: set[date] = {
    date(2025, 1, 26),   # Republic Day
    date(2025, 2, 26),   # Mahashivratri
    date(2025, 3, 14),   # Holi
    date(2025, 3, 31),   # Id-Ul-Fitr (Ramzan Eid)
    date(2025, 4, 14),   # Dr. Baba Saheb Ambedkar Jayanti
    date(2025, 4, 18),   # Good Friday
    date(2025, 5, 1),    # Maharashtra Day
    date(2025, 8, 15),   # Independence Day
    date(2025, 8, 27),   # Ganesh Chaturthi
    date(2025, 10, 2),   # Gandhi Jayanti / Dussehra
    date(2025, 10, 24),  # Diwali Laxmi Puja
    date(2025, 10, 25),  # Diwali Balipratipada
    date(2025, 11, 5),   # Prakash Gurpurb
    date(2025, 12, 25),  # Christmas
}


def is_trading_day(dt: datetime) -> bool:
    """Returns True if the given UTC datetime falls on an NSE trading day."""
    ist_dt = dt.astimezone(IST)
    d = ist_dt.date()
    if ist_dt.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    if d in NSE_HOLIDAYS_2025:
        return False
    return True


def is_market_open(dt: datetime) -> bool:
    """Returns True if the market is currently open."""
    if not is_trading_day(dt):
        return False
    ist_dt = dt.astimezone(IST)
    return MARKET_OPEN <= ist_dt.time() <= MARKET_CLOSE


def filter_trading_days(dates: list[datetime]) -> list[datetime]:
    """Filter a list of UTC datetimes to only include trading days."""
    return [d for d in dates if is_trading_day(d)]
