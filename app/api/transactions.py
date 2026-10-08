import csv
import io
from collections.abc import Iterable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.orm import contains_eager

from app.api.categories import get_owned_category
from app.deps import CurrentUser, DbSession
from app.models import Category, CategoryType, Transaction, User
from app.months import Month, month_bounds
from app.queries import sum_by_type
from app.schemas import TransactionCreate, TransactionPage, TransactionRead, TransactionUpdate

router = APIRouter(prefix="/transactions", tags=["transactions"])


class TransactionFilters:
    def __init__(
        self,
        month: Annotated[Month | None, Query(description="YYYY-MM")] = None,
        type: CategoryType | None = None,
        category_id: int | None = None,
    ) -> None:
        self.month = month
        self.type = type
        self.category_id = category_id

    def conditions(self, user: User) -> list[ColumnElement[bool]]:
        conditions = [Transaction.user_id == user.id]
        if self.month is not None:
            start, end = month_bounds(self.month)
            conditions += [Transaction.occurred_on >= start, Transaction.occurred_on < end]
        if self.type is not None:
            conditions.append(Category.type == self.type)
        if self.category_id is not None:
            conditions.append(Transaction.category_id == self.category_id)
        return conditions


Filters = Annotated[TransactionFilters, Depends()]


def _filtered_query(filters: TransactionFilters, user: User) -> Select[Transaction]:
    return (
        select(Transaction)
        .join(Transaction.category)
        # Reuse the filter join to load the category instead of joining it twice.
        .options(contains_eager(Transaction.category))
        .where(*filters.conditions(user))
        .order_by(Transaction.occurred_on.desc(), Transaction.id.desc())
    )


def get_owned_transaction(db: DbSession, user: User, transaction_id: int) -> Transaction:
    transaction = db.scalar(
        select(Transaction).where(Transaction.id == transaction_id, Transaction.user_id == user.id)
    )
    if transaction is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    return transaction


@router.get("")
def list_transactions(
    db: DbSession,
    user: CurrentUser,
    filters: Filters,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TransactionPage:
    items = db.scalars(_filtered_query(filters, user).limit(limit).offset(offset))

    total, income, expense = db.execute(
        select(
            func.count(),
            sum_by_type(CategoryType.INCOME),
            sum_by_type(CategoryType.EXPENSE),
        )
        .select_from(Transaction)
        .join(Transaction.category)
        .where(*filters.conditions(user))
    ).one()

    return TransactionPage(
        items=[TransactionRead.model_validate(t) for t in items],
        total=total,
        income=income,
        expense=expense,
    )


CSV_HEADER = ("date", "type", "category", "amount", "note")


def _csv_safe(value: str) -> str:
    # Spreadsheets run cells starting with these characters as formulas
    # (CSV injection); a leading apostrophe makes them plain text.
    return "'" + value if value.startswith(("=", "+", "-", "@", "\t", "\r")) else value


def _to_csv(transactions: Iterable[Transaction]) -> str:
    buffer = io.StringIO()
    # The BOM makes Excel read the file as UTF-8, so Thai text displays correctly.
    buffer.write("﻿")
    writer = csv.writer(buffer)
    writer.writerow(CSV_HEADER)
    for t in transactions:
        writer.writerow(
            (
                t.occurred_on.isoformat(),
                t.category.type.value,
                _csv_safe(t.category.name),
                f"{t.amount:.2f}",
                _csv_safe(t.note or ""),
            )
        )
    return buffer.getvalue()


# Declared before "/{transaction_id}" so the path isn't parsed as an id.
@router.get(
    "/export.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "CSV file"}},
)
def export_transactions(db: DbSession, user: CurrentUser, filters: Filters) -> Response:
    """Download all transactions matching the filters (no pagination) as CSV."""
    transactions = db.scalars(_filtered_query(filters, user))
    filename = f"transactions-{filters.month}.csv" if filters.month else "transactions.csv"
    return Response(
        content=_to_csv(transactions),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: TransactionCreate, db: DbSession, user: CurrentUser
) -> TransactionRead:
    get_owned_category(db, user, payload.category_id)
    transaction = Transaction(user_id=user.id, **payload.model_dump())
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return TransactionRead.model_validate(transaction)


@router.get("/{transaction_id}")
def read_transaction(transaction_id: int, db: DbSession, user: CurrentUser) -> TransactionRead:
    return TransactionRead.model_validate(get_owned_transaction(db, user, transaction_id))


@router.patch("/{transaction_id}")
def update_transaction(
    transaction_id: int, payload: TransactionUpdate, db: DbSession, user: CurrentUser
) -> TransactionRead:
    transaction = get_owned_transaction(db, user, transaction_id)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("category_id") is not None:
        get_owned_category(db, user, changes["category_id"])

    for field, value in changes.items():
        # Only the note can be cleared; null for any other field means "no change".
        if value is not None or field == "note":
            setattr(transaction, field, value)
    db.commit()
    db.refresh(transaction)
    return TransactionRead.model_validate(transaction)


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(transaction_id: int, db: DbSession, user: CurrentUser) -> None:
    db.delete(get_owned_transaction(db, user, transaction_id))
    db.commit()
