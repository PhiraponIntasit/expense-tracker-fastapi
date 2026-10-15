import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app import web
from app.api import api_router, health
from app.db import SessionLocal
from app.demo import purge_expired_demo_users

logger = logging.getLogger(__name__)

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


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Free hosting has no cron, so expired demo accounts are also purged on
    # startup (and every time a new demo account is created).
    try:
        with SessionLocal() as db:
            purged = purge_expired_demo_users(db)
        if purged:
            logger.info("Purged %d expired demo accounts", purged)
    except Exception:  # never block startup on housekeeping
        logger.exception("Could not purge expired demo accounts")
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Expense Tracker",
        summary="Track income and expenses, with monthly summaries.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.middleware("http")(reject_cross_origin_writes)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    app.include_router(health.router)
    app.include_router(api_router)
    app.include_router(web.router)
    return app


app = create_app()
