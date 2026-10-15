from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from app.accounts import (
    EmailTakenError,
    authenticate,
    clear_auth_cookie,
    register_user,
    set_auth_cookie,
)
from app.demo import DemoCapacityError, create_demo_user
from app.deps import DbSession
from app.schemas import Token, UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: DbSession) -> UserRead:
    try:
        user = register_user(db, payload.email, payload.password)
    except EmailTakenError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "An account with this email already exists"
        ) from None
    return UserRead.model_validate(user)


@router.post("/token")
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession,
    response: Response,
) -> Token:
    """Log in with email (as `username`) and password.

    Returns a bearer token for API clients and also sets it as an httpOnly
    cookie for the web UI.
    """
    user = authenticate(db, form.username, form.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=set_auth_cookie(response, user))


DEMO_BUSY = "The demo is busy right now. Please try again later or create an account."


@router.post("/demo", status_code=status.HTTP_201_CREATED)
def start_demo(db: DbSession, response: Response) -> UserRead:
    """Create a temporary account with a year of sample data and log in as it.

    Demo accounts are deleted automatically after 24 hours.
    """
    try:
        user = create_demo_user(db)
    except DemoCapacityError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, DEMO_BUSY) from None
    set_auth_cookie(response, user)
    return UserRead.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    clear_auth_cookie(response)
