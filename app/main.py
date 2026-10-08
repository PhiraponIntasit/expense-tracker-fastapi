from fastapi import FastAPI

from app.api import api_router, health


def create_app() -> FastAPI:
    app = FastAPI(
        title="Expense Tracker",
        summary="Track income and expenses, with monthly summaries.",
        version="0.1.0",
    )
    app.include_router(health.router)
    app.include_router(api_router)
    return app


app = create_app()
