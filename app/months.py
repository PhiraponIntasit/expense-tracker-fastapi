from datetime import UTC, date, datetime
from typing import Annotated

from pydantic import StringConstraints

# "YYYY-MM", e.g. "2026-10".
Month = Annotated[str, StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]


def month_start(month: str) -> date:
    year, month_number = map(int, month.split("-"))
    return date(year, month_number, 1)


def next_month(day: date) -> date:
    """First day of the month after the one containing `day`."""
    return add_months(day, 1)


def month_bounds(month: str) -> tuple[date, date]:
    """Half-open [start, end) range, which keeps queries index-friendly."""
    start = month_start(month)
    return start, next_month(start)


def add_months(day: date, months: int) -> date:
    """First day of the month `months` away from the month containing `day`."""
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def months_between(start: date, end: date) -> int:
    """Number of whole months from start's month to end's month."""
    return (end.year - start.year) * 12 + end.month - start.month


def current_month() -> date:
    # Server time (UTC). The web UI passes explicit months computed in the
    # browser's local time, so this default only matters for direct API use.
    today = datetime.now(UTC).date()
    return today.replace(day=1)
