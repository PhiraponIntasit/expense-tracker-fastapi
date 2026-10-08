from decimal import Decimal

from sqlalchemy import ColumnElement, Numeric, cast, func

from app.models import Category, CategoryType, Transaction


def sum_by_type(category_type: CategoryType) -> ColumnElement[Decimal]:
    """SUM(amount) over rows of one category type, for use in an aggregate query
    that joins transactions to categories.

    The cast keeps two decimal places even when nothing matches ("0.00", not "0").
    """
    return cast(
        func.coalesce(func.sum(Transaction.amount).filter(Category.type == category_type), 0),
        Numeric(12, 2),
    )
