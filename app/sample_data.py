"""Realistic-looking sample transactions for demo accounts and local seeding.

The generator is a pure function of (categories, today, seed), so tests can
pin its output. It covers the 12 months ending today and never goes past
today, with the rhythms a Bangkok office worker's budget would have: rent on
the 1st, salary on the 25th, a hot-season electricity spike, a Songkran trip,
and 11.11 / year-end shopping.
"""

import random
from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal

from app.models import CategoryType

INCOME = CategoryType.INCOME
EXPENSE = CategoryType.EXPENSE

CategoryIds = dict[tuple[CategoryType, str], int]

FOOD_NOTES = ["ข้าวมันไก่", "ก๋วยเตี๋ยว", "Lunch", "Coffee", "Groceries", "ส้มตำ", "Dinner", None]
TRANSPORT_NOTES = ["BTS", "MRT", "Grab", None]


def baht(value: float) -> Decimal:
    return Decimal(str(round(value, 2))).quantize(Decimal("0.01"))


def first_of_month_months_ago(today: date, months: int) -> date:
    index = today.year * 12 + today.month - 1 - months
    return date(index // 12, index % 12 + 1, 1)


def sample_transactions(
    category_ids: CategoryIds, today: date, seed: int = 0
) -> list[dict[str, object]]:
    """Rows for `transactions` (without user_id) from 11 months ago up to today."""
    rng = random.Random(seed)
    rows: list[dict[str, object]] = []

    def add(
        kind: CategoryType, name: str, amount: Decimal, day: date, note: str | None = None
    ) -> None:
        rows.append(
            {
                "category_id": category_ids[(kind, name)],
                "amount": amount,
                "occurred_on": day,
                "note": note,
            }
        )

    freelance_months = {m for m in range(1, 13) if rng.random() < 0.45}

    for day in _days(first_of_month_months_ago(today, 11), today):
        weekend = day.weekday() >= 5

        # Fixed monthly items.
        if day.day == 1:
            add(EXPENSE, "Housing", Decimal("9500.00"), day, "Condo rent")
        if day.day == 5:
            hot_season = day.month in (3, 4, 5)
            electricity = rng.uniform(1800, 3200) if hot_season else rng.uniform(900, 1600)
            add(EXPENSE, "Bills & Utilities", baht(electricity), day, "Electricity")
        if day.day == 10:
            add(EXPENSE, "Bills & Utilities", Decimal("599.00"), day, "Home internet")
        if day.day == 25:
            add(INCOME, "Salary", Decimal("42000.00"), day, "Monthly salary")
            if day.month == 12:
                add(INCOME, "Bonus", Decimal("42000.00"), day, "Year-end bonus")
        if day.day == 18 and day.month in freelance_months:
            add(INCOME, "Freelance", baht(rng.uniform(3000, 15000)), day, "Web project")

        # Everyday spending.
        for _ in range(rng.choice((1, 1, 2, 2, 3))):
            add(
                EXPENSE, "Food & Dining", Decimal(rng.randint(45, 350)), day, rng.choice(FOOD_NOTES)
            )
        if not weekend and rng.random() < 0.7:
            add(
                EXPENSE, "Transport", Decimal(rng.randint(16, 62)), day, rng.choice(TRANSPORT_NOTES)
            )
        if rng.random() < 0.15:
            add(EXPENSE, "Transport", Decimal(rng.randint(80, 260)), day, "Grab")

        # Occasional and seasonal spending.
        shopping_odds = (
            0.5 if (day.month, day.day) == (11, 11) else 0.12 if day.month == 12 else 0.06
        )
        if rng.random() < shopping_odds:
            add(EXPENSE, "Shopping", baht(rng.uniform(300, 3500)), day)
        if weekend and rng.random() < 0.3:
            add(EXPENSE, "Entertainment", Decimal(rng.randint(180, 1200)), day, "Movies & outings")
        if (day.month, day.day) == (4, 12):
            add(EXPENSE, "Entertainment", baht(rng.uniform(4000, 8000)), day, "Songkran trip")
        if rng.random() < 0.025:
            add(EXPENSE, "Health", baht(rng.uniform(150, 1800)), day, "Clinic / pharmacy")
        if rng.random() < 0.01:
            add(EXPENSE, "Other", baht(rng.uniform(300, 2000)), day, "Gift")

    return rows


def _days(start: date, end: date) -> Iterator[date]:
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)
