from sqlalchemy.orm import Session

from app.models import Category, CategoryType, User

DEFAULT_CATEGORIES: dict[CategoryType, tuple[str, ...]] = {
    CategoryType.EXPENSE: (
        "Food & Dining",
        "Transport",
        "Housing",
        "Bills & Utilities",
        "Shopping",
        "Health",
        "Entertainment",
        "Other",
    ),
    CategoryType.INCOME: ("Salary", "Bonus", "Freelance", "Other"),
}


def add_default_categories(db: Session, user: User) -> None:
    """Give a new user a starter set of categories. The caller commits."""
    db.add_all(
        Category(user_id=user.id, name=name, type=category_type)
        for category_type, names in DEFAULT_CATEGORIES.items()
        for name in names
    )
