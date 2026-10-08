from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.security import ACCESS_TOKEN_COOKIE, decode_access_token

# auto_error=False: a missing header is fine as long as the cookie is present.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def _user_from_token(db: Session, token: str | None) -> User | None:
    user_id = decode_access_token(token) if token else None
    return db.get(User, user_id) if user_id is not None else None


def get_current_user(
    db: DbSession,
    bearer_token: Annotated[str | None, Depends(oauth2_scheme)],
    cookie_token: Annotated[str | None, Cookie(alias=ACCESS_TOKEN_COOKIE)] = None,
) -> User:
    # An explicit Authorization header wins over the browser cookie.
    user = _user_from_token(db, bearer_token or cookie_token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_page_user(
    db: DbSession,
    cookie_token: Annotated[str | None, Cookie(alias=ACCESS_TOKEN_COOKIE)] = None,
) -> User | None:
    """The logged-in user for web pages (cookie only), or None."""
    return _user_from_token(db, cookie_token)


PageUser = Annotated[User | None, Depends(get_page_user)]
