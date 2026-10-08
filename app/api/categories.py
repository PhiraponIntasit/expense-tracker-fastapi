from fastapi import APIRouter, HTTPException, status
from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError

from app.deps import CurrentUser, DbSession
from app.models import Category, CategoryType, Transaction, User
from app.schemas import CategoryCreate, CategoryRead, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["categories"])

NAME_TAKEN = "A category with this name and type already exists"
IN_USE = "Category has transactions; move them to another category first"


def get_owned_category(db: DbSession, user: User, category_id: int) -> Category:
    # 404 rather than 403 for other users' categories, so ids don't leak.
    category = db.scalar(
        select(Category).where(Category.id == category_id, Category.user_id == user.id)
    )
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    return category


def _name_taken(
    db: DbSession, user: User, name: str, category_type: CategoryType, exclude_id: int | None
) -> bool:
    query = select(Category.id).where(
        Category.user_id == user.id,
        Category.type == category_type,
        func.lower(Category.name) == name.lower(),
    )
    if exclude_id is not None:
        query = query.where(Category.id != exclude_id)
    return db.scalar(query) is not None


def _in_use(db: DbSession, category: Category) -> bool:
    return bool(db.scalar(select(exists().where(Transaction.category_id == category.id))))


def _commit_or_conflict(db: DbSession) -> None:
    try:
        db.commit()
    except IntegrityError:  # lost a race with a concurrent request
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, NAME_TAKEN) from None


@router.get("")
def list_categories(
    db: DbSession, user: CurrentUser, type: CategoryType | None = None
) -> list[CategoryRead]:
    query = select(Category).where(Category.user_id == user.id)
    if type is not None:
        query = query.where(Category.type == type)
    categories = db.scalars(query.order_by(Category.type, func.lower(Category.name)))
    return [CategoryRead.model_validate(category) for category in categories]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_category(payload: CategoryCreate, db: DbSession, user: CurrentUser) -> CategoryRead:
    if _name_taken(db, user, payload.name, payload.type, exclude_id=None):
        raise HTTPException(status.HTTP_409_CONFLICT, NAME_TAKEN)
    category = Category(user_id=user.id, name=payload.name, type=payload.type)
    db.add(category)
    _commit_or_conflict(db)
    return CategoryRead.model_validate(category)


@router.get("/{category_id}")
def read_category(category_id: int, db: DbSession, user: CurrentUser) -> CategoryRead:
    return CategoryRead.model_validate(get_owned_category(db, user, category_id))


@router.patch("/{category_id}")
def update_category(
    category_id: int, payload: CategoryUpdate, db: DbSession, user: CurrentUser
) -> CategoryRead:
    category = get_owned_category(db, user, category_id)
    new_name = payload.name or category.name
    new_type = payload.type or category.type

    # A transaction's type comes from its category, so retyping a category in use
    # would silently turn past expenses into income.
    if new_type != category.type and _in_use(db, category):
        raise HTTPException(status.HTTP_409_CONFLICT, IN_USE)
    if _name_taken(db, user, new_name, new_type, exclude_id=category.id):
        raise HTTPException(status.HTTP_409_CONFLICT, NAME_TAKEN)

    category.name = new_name
    category.type = new_type
    _commit_or_conflict(db)
    return CategoryRead.model_validate(category)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, db: DbSession, user: CurrentUser) -> None:
    category = get_owned_category(db, user, category_id)
    if _in_use(db, category):
        raise HTTPException(status.HTTP_409_CONFLICT, IN_USE)
    db.delete(category)
    db.commit()
