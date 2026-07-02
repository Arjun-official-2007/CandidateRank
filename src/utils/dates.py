"""
utils/dates.py — Null-safe date parsing and arithmetic utilities.
All functions return None on failure — never raise exceptions.
"""

from datetime import datetime
from typing import Optional
import re


# ---------------------------------------------------------------------------
# Supported date format patterns (tried in order)
# ---------------------------------------------------------------------------
_DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y-%m",
    "%m/%Y",
    "%d/%m/%Y",
    "%m-%Y",
    "%B %Y",    # "January 2020"
    "%b %Y",    # "Jan 2020"
    "%Y",
]

_PRESENT_ALIASES = {"present", "current", "now", "ongoing", "till date", "till now", ""}


def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """
    Parse a date string in ISO or common formats.
    Returns None on failure, None input, or unrecognised formats — never raises.
    """
    if not date_str:
        return None

    text = str(date_str).strip()

    if text.lower() in _PRESENT_ALIASES:
        return None

    # Try each known format
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    # Try extracting a bare year with regex as last resort
    m = re.search(r"\b(19|20)\d{2}\b", text)
    if m:
        try:
            return datetime.strptime(m.group(0), "%Y")
        except ValueError:
            pass

    return None


def months_between(
    start: Optional[str],
    end: Optional[str],
    ref_today: datetime,
) -> Optional[float]:
    """
    Compute the number of months between two date strings.
    If `end` is None / "present" / blank, uses ref_today.
    Returns None if `start` is unparseable.
    """
    start_dt = parse_date(start)
    if start_dt is None:
        return None

    if end and str(end).strip().lower() not in _PRESENT_ALIASES:
        end_dt = parse_date(end)
        if end_dt is None:
            end_dt = ref_today
    else:
        end_dt = ref_today

    # Clamp: end must be >= start
    if end_dt < start_dt:
        end_dt = start_dt

    delta_months = (
        (end_dt.year - start_dt.year) * 12
        + (end_dt.month - start_dt.month)
        + (end_dt.day - start_dt.day) / 30.0
    )
    return max(0.0, delta_months)


def days_since(
    date_str: Optional[str],
    ref_today: datetime,
) -> Optional[int]:
    """
    Return the number of days between a date string and ref_today.
    Returns None if date_str is unparseable or None.
    """
    dt = parse_date(date_str)
    if dt is None:
        return None

    delta = ref_today - dt
    return delta.days
