"""Account operations shared by the JSON API and the web pages."""

from fastapi import Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.defaults import add_default_categories
from app.models import User
from app.security import (
    ACCESS_TOKEN_COOKIE,
    DUMMY_HASH,
    create_access_token,
    hash_password,
    verify_password,
)


class EmailTakenError(Exception):
    pass


def register_user(db: Session, email: str, password: str) -> User:
    """Create a user with the default categories. `email` must already be normalized."""
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise EmailTakenError
    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    try:
        db.flush()
        add_default_categories(db, user)
        db.commit()
    except IntegrityError:  # lost a race with a concurrent registration
        db.rollback()
        raise EmailTakenError from None
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    # Verify against a dummy hash for unknown emails so the response time
    # doesn't reveal whether an account exists.
    password_ok = verify_password(password, user.password_hash if user else DUMMY_HASH)
    return user if user is not None and password_ok else None


def set_auth_cookie(response: Response, user: User) -> str:
    """Issue an access token, set it as the auth cookie, and return it."""
    token = create_access_token(user.id)
    settings = get_settings()
    response.set_cookie(
        ACCESS_TOKEN_COOKIE,
        token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return token


def clear_auth_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        ACCESS_TOKEN_COOKIE, httponly=True, secure=settings.cookie_secure, samesite="lax"
    )
