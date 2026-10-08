from collections.abc import Awaitable, Callable
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app import web
from app.api import api_router, health

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


async def reject_cross_origin_writes(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """CSRF defence in depth on top of the SameSite=Lax cookie.

    Browsers send an Origin header on cross-site writes; refuse those whose
    host differs from ours. Non-browser clients (curl, tests) send no Origin.
    """
    origin = request.headers.get("origin")
    if (
        request.method in UNSAFE_METHODS
        and origin is not None
        and urlsplit(origin).netloc != request.headers.get("host")
    ):
        return PlainTextResponse("Cross-origin request blocked", status.HTTP_403_FORBIDDEN)
    return await call_next(request)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Expense Tracker",
        summary="Track income and expenses, with monthly summaries.",
        version="0.1.0",
    )
    app.middleware("http")(reject_cross_origin_writes)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    app.include_router(health.router)
    app.include_router(api_router)
    app.include_router(web.router)
    return app


app = create_app()
