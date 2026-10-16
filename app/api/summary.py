from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import Date, DateTime, Interval, cast, func, literal, select

from app.deps import CurrentUser, DbSession
from app.models import Category, CategoryType, Transaction
from app.months import Month, add_months, current_month, month_start, months_between
from app.queries import sum_by_type
from app.schemas import CategoryTotal, MonthTotals

router = APIRouter(prefix="/summary", tags=["summary"])

MAX_MONTHS = 120


@router.get("/monthly")
def monthly_summary(
    db: DbSession,
    user: CurrentUser,
    from_: Annotated[Month | None, Query(alias="from", description="YYYY-MM")] = None,
    to: Annotated[Month | None, Query(description="YYYY-MM")] = None,
) -> list[MonthTotals]:
    """Income, expense and net for every month in the range (inclusive).

    Months without transactions are returned with zeros so a chart's time axis
    has no gaps. Defaults to the 12 months ending with the current month (UTC).
    """
    last = month_start(to) if to else current_month()
    first = month_start(from_) if from_ else add_months(last, -11)
    span = months_between(first, last) + 1
    if span < 1:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "'from' must not be after 'to'")
    if span > MAX_MONTHS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Range is limited to {MAX_MONTHS} months"
        )

    # Bucket by calendar month using plain TIMESTAMP (no time zone) throughout,
    # so month boundaries are pure date arithmetic.
    month_of = func.date_trunc("month", cast(Transaction.occurred_on, DateTime())).label("month")
    totals = (
        select(
            month_of,
            sum_by_type(CategoryType.INCOME).label("income"),
            sum_by_type(CategoryType.EXPENSE).label("expense"),
        )
        .join(Transaction.category)
        .where(
            Transaction.user_id == user.id,
            Transaction.occurred_on >= first,
            Transaction.occurred_on < add_months(last, 1),
        )
        .group_by(month_of)
        .subquery()
    )
    months = select(
        func.generate_series(
            cast(literal(first), DateTime()),
            cast(literal(last), DateTime()),
            cast(literal("1 month"), Interval()),
        ).label("month")
    ).subquery()

    zero = cast(literal(0), totals.c.income.type)
    income = func.coalesce(totals.c.income, zero)
    expense = func.coalesce(totals.c.expense, zero)
    rows = db.execute(
        select(cast(months.c.month, Date), income, expense)
        .select_from(months)
        .outerjoin(totals, totals.c.month == months.c.month)
        .order_by(months.c.month)
    )
    return [
        MonthTotals(month=f"{month:%Y-%m}", income=income, expense=expense, net=income - expense)
        for month, income, expense in rows
    ]


@router.get("/by-category")
def category_summary(
    db: DbSession,
    user: CurrentUser,
    month: Annotated[Month | None, Query(description="YYYY-MM")] = None,
    type: CategoryType = CategoryType.EXPENSE,
) -> list[CategoryTotal]:
    """Totals per category for one month, largest first. Categories with no
    transactions that month are left out. Defaults to the current month (UTC)."""
    start = month_start(month) if month else current_month()
    end = add_months(start, 1)
    total = func.sum(Transaction.amount).label("total")
    rows = db.execute(
        select(Category.id, Category.name, total)
        .join(Transaction.category)
        .where(
            Transaction.user_id == user.id,
            Category.type == type,
            Transaction.occurred_on >= start,
            Transaction.occurred_on < end,
        )
        .group_by(Category.id, Category.name)
        .order_by(total.desc(), Category.name)
    )
    return [
        CategoryTotal(category_id=category_id, name=name, total=total)
        for category_id, name, total in rows
    ]
