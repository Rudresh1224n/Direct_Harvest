from datetime import datetime, timezone, timedelta

# IST is UTC + 5:30
IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_now() -> datetime:
    """Return the current datetime in Indian Standard Time (naive or timezone-aware)."""
    return datetime.now(IST).replace(tzinfo=None)

def format_ist_datetime(dt: datetime, fmt: str = "%d %b %Y, %I:%M %p") -> str:
    """Format a datetime to readable IST string."""
    if not dt:
        return "N/A"
    return dt.strftime(fmt)
