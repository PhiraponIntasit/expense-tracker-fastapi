import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.orm import Session

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://expense:expense@localhost:5432/expense_test",
)
# Must be set before anything imports app.config / app.db.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import engine, get_db  # noqa: E402
from app.main import create_app  # noqa: E402


def _ensure_database_exists() -> None:
    url = make_url(TEST_DATABASE_URL)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def _migrated_database() -> None:
    _ensure_database_exists()
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture
def connection() -> Iterator[Connection]:
    # Every test runs inside one outer transaction that is rolled back at the
    # end, so tests never see each other's data and need no cleanup.
    with engine.connect() as conn:
        outer = conn.begin()
        yield conn
        outer.rollback()


@pytest.fixture
def db(connection: Connection) -> Iterator[Session]:
    # Commits inside the app become savepoints within the outer transaction.
    with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client


PASSWORD = "correct-horse-battery"


def register(client: TestClient, email: str, password: str = PASSWORD) -> dict[str, object]:
    response = client.post("/api/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


def bearer_headers(client: TestClient, email: str, password: str = PASSWORD) -> dict[str, str]:
    """Log in and return an Authorization header, leaving no auth cookie behind."""
    response = client.post("/api/auth/token", data={"username": email, "password": password})
    assert response.status_code == 200, response.text
    client.cookies.clear()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
