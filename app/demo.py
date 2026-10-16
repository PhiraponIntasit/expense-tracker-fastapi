"""Throwaway demo accounts: one fresh account per visitor, purged after a day."""

import secrets
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.defaults import add_default_categories
from app.models import Category, Transaction, User
from app.sample_data import sample_transactions
from app.security import hash_password

# Nobody knows this password; demo accounts are only reachable through the
# cookie set when they're created. Hashed once at startup because Argon2 is
# deliberately slow, and hashing per demo would cost that on every click.
UNUSABLE_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


class DemoCapacityError(Exception):
    """Too many live demo accounts; refuse instead of growing the database."""


def add_sample_data(db: Session, user: User, today: date, seed: int) -> int:
    """Insert 12 months of sample transactions for `user`. The caller commits."""
    categories = db.execute(
        select(Category.type, Category.name, Category.id).where(Category.user_id == user.id)
    )
    category_ids = {(kind, name): category_id for kind, name, category_id in categories}
    rows = sample_transactions(category_ids, today, seed)
    # One multi-row INSERT (one round trip). Passing a list of dicts to
    # execute() would let the ORM split rows into ~250 statements whenever a
    # row's note is None or not, which made demo creation take seconds on a
    # remote database.
    db.execute(insert(Transaction).values([{**row, "user_id": user.id} for row in rows]))
    return len(rows)


def purge_expired_demo_users(db: Session) -> int:
    """Delete demo accounts older than the configured age (their data cascades)."""
    max_age = timedelta(hours=get_settings().demo_max_age_hours)
    deleted = db.scalars(
        delete(User).where(User.is_demo, User.created_at < func.now() - max_age).returning(User.id)
    ).all()
    db.commit()
    return len(deleted)


def create_demo_user(db: Session) -> User:
    purge_expired_demo_users(db)
    live = db.scalar(select(func.count()).select_from(User).where(User.is_demo))
    if live is not None and live >= get_settings().demo_max_users:
        raise DemoCapacityError

    token = secrets.token_hex(6)
    user = User(
        email=f"demo-{token}@example.com",
        password_hash=UNUSABLE_PASSWORD_HASH,
        is_demo=True,
    )
    db.add(user)
    db.flush()
    add_default_categories(db, user)
    db.flush()
    add_sample_data(db, user, datetime.now(UTC).date(), seed=secrets.randbits(32))
    db.commit()
    return user
