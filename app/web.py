"""Server-rendered pages. Data pages are shells: their JS loads data from /api."""

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.accounts import (
    EmailTakenError,
    authenticate,
    clear_auth_cookie,
    register_user,
    set_auth_cookie,
)
from app.deps import DbSession, PageUser
from app.models import User
from app.schemas import UserCreate

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# Pages only load same-origin scripts and styles, so a strict policy costs
# nothing. (Swagger UI at /docs loads from a CDN, so it isn't covered.)
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
}


def render(
    request: Request,
    name: str,
    context: dict[str, Any] | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, name, context or {}, status_code=status_code, headers=SECURITY_HEADERS
    )


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


def page(request: Request, user: User | None, name: str, active: str) -> Response:
    if user is None:
        return redirect("/login")
    return render(request, name, {"user": user, "active": active})


# --- authentication pages --------------------------------------------------------


@router.get("/login")
def login_page(request: Request, user: PageUser) -> Response:
    if user is not None:
        return redirect("/")
    return render(request, "login.html")


@router.post("/login")
def login_submit(
    request: Request,
    db: DbSession,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> Response:
    user = authenticate(db, email, password)
    if user is None:
        return render(
            request,
            "login.html",
            {"email": email, "error": "Incorrect email or password."},
            status.HTTP_401_UNAUTHORIZED,
        )
    response = redirect("/")
    set_auth_cookie(response, user)
    return response


@router.get("/register")
def register_page(request: Request, user: PageUser) -> Response:
    if user is not None:
        return redirect("/")
    return render(request, "register.html")


@router.post("/register")
def register_submit(
    request: Request,
    db: DbSession,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> Response:
    def form_error(message: str, status_code: int) -> Response:
        return render(request, "register.html", {"email": email, "error": message}, status_code)

    try:
        payload = UserCreate(email=email, password=password)
    except ValidationError as exc:
        field = exc.errors()[0]["loc"][0]
        message = (
            "Please enter a valid email address."
            if field == "email"
            else "Password must be 8 to 128 characters."
        )
        return form_error(message, status.HTTP_422_UNPROCESSABLE_CONTENT)
    try:
        user = register_user(db, payload.email, payload.password)
    except EmailTakenError:
        return form_error("An account with this email already exists.", status.HTTP_409_CONFLICT)

    response = redirect("/")
    set_auth_cookie(response, user)
    return response


@router.post("/logout")
def logout_submit() -> Response:
    response = redirect("/login")
    clear_auth_cookie(response)
    return response


# --- app pages -------------------------------------------------------------------


@router.get("/")
def dashboard_page(request: Request, user: PageUser) -> Response:
    return page(request, user, "dashboard.html", "dashboard")


@router.get("/transactions")
def transactions_page(request: Request, user: PageUser) -> Response:
    return page(request, user, "transactions.html", "transactions")


@router.get("/categories")
def categories_page(request: Request, user: PageUser) -> Response:
    return page(request, user, "categories.html", "categories")
