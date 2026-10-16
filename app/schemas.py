from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.models import CategoryType


def _normalize_email(value: str) -> str:
    return value.strip().lower()


NormalizedEmail = Annotated[EmailStr, AfterValidator(_normalize_email)]


class UserCreate(BaseModel):
    email: NormalizedEmail
    password: str = Field(min_length=8, max_length=128)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    is_demo: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


CategoryName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class CategoryCreate(BaseModel):
    name: CategoryName
    type: CategoryType


class CategoryUpdate(BaseModel):
    name: CategoryName | None = None
    type: CategoryType | None = None


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: CategoryType


def _blank_to_none(value: str | None) -> str | None:
    return value or None


Note = Annotated[
    str | None,
    StringConstraints(strip_whitespace=True, max_length=200),
    AfterValidator(_blank_to_none),
]
# Positive, at most 2 decimal places, up to 9,999,999,999.99 (numeric(12, 2)).
Amount = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]


class TransactionCreate(BaseModel):
    category_id: int
    amount: Amount
    occurred_on: date
    note: Note = None


class TransactionUpdate(BaseModel):
    category_id: int | None = None
    amount: Amount | None = None
    occurred_on: date | None = None
    # Send null explicitly to clear the note; leave it out to keep it.
    note: Note = None


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: Decimal
    occurred_on: date
    note: str | None
    category: CategoryRead
    created_at: datetime
    updated_at: datetime


class TransactionPage(BaseModel):
    items: list[TransactionRead]
    total: int = Field(description="Number of transactions matching the filters")
    income: Decimal = Field(description="Sum of income matching the filters (all pages)")
    expense: Decimal = Field(description="Sum of expenses matching the filters (all pages)")


class MonthTotals(BaseModel):
    month: str = Field(examples=["2026-10"])
    income: Decimal
    expense: Decimal
    net: Decimal = Field(description="income - expense")


class CategoryTotal(BaseModel):
    category_id: int
    name: str
    total: Decimal
