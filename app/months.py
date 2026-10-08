from datetime import date
from typing import Annotated

from pydantic import StringConstraints

# "YYYY-MM", e.g. "2026-10".
Month = Annotated[str, StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]


def month_start(month: str) -> date:
    year, month_number = map(int, month.split("-"))
    return date(year, month_number, 1)


def next_month(day: date) -> date:
    """First day of the month after the one containing `day`."""
    return date(day.year + day.month // 12, day.month % 12 + 1, 1)


def month_bounds(month: str) -> tuple[date, date]:
    """Half-open [start, end) range, which keeps queries index-friendly."""
    start = month_start(month)
    return start, next_month(start)
