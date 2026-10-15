from collections import Counter
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.defaults import DEFAULT_CATEGORIES
from app.demo import purge_expired_demo_users
from app.models import CategoryType, Transaction, User
from app.sample_data import sample_transactions
from app.security import ACCESS_TOKEN_COOKIE
from tests.conftest import register

CATEGORY_IDS = {
    (kind, name): index
    for index, (kind, name) in enumerate(
        (kind, name) for kind, names in DEFAULT_CATEGORIES.items() for name in names
    )
}


# --- sample data ---------------------------------------------------------------


def test_sample_data_covers_twelve_months_up_to_today() -> None:
    today = date(2026, 10, 15)

    rows = sample_transactions(CATEGORY_IDS, today, seed=1)

    days = [row["occurred_on"] for row in rows]
    assert min(days) == date(2025, 11, 1)
    assert max(days) <= today
    assert {f"{d:%Y-%m}" for d in days if isinstance(d, date)} == {
        f"{year}-{month:02d}"
        for year, month in [(2025, 11), (2025, 12)] + [(2026, m) for m in range(1, 11)]
    }
    assert all(isinstance(r["amount"], Decimal) and r["amount"] > 0 for r in rows)


def test_sample_data_has_salary_each_past_month_and_rent_every_month() -> None:
    by_category = Counter(
        row["category_id"] for row in sample_transactions(CATEGORY_IDS, date(2026, 10, 15), seed=1)
    )

    # Salary lands on the 25th, so October 2026 (still the 15th) has none yet.
    assert by_category[CATEGORY_IDS[(CategoryType.INCOME, "Salary")]] == 11
    assert by_category[CATEGORY_IDS[(CategoryType.EXPENSE, "Housing")]] == 12


def test_sample_data_is_deterministic_per_seed() -> None:
    today = date(2026, 10, 15)

    assert sample_transactions(CATEGORY_IDS, today, seed=3) == sample_transactions(
        CATEGORY_IDS, today, seed=3
    )
    assert sample_transactions(CATEGORY_IDS, today, seed=3) != sample_transactions(
        CATEGORY_IDS, today, seed=4
    )


# --- demo accounts -------------------------------------------------------------


def test_demo_endpoint_logs_into_a_fresh_account_with_sample_data(client: TestClient) -> None:
    response = client.post("/api/auth/demo")

    assert response.status_code == 201
    assert response.json()["is_demo"] is True
    assert ACCESS_TOKEN_COOKIE in client.cookies
    months = client.get("/api/summary/monthly").json()
    assert len(months) == 12
    assert all(Decimal(m["expense"]) > 0 for m in months)
    assert sum(Decimal(m["income"]) for m in months) > 0


def test_each_demo_visitor_gets_a_separate_account(client: TestClient) -> None:
    first = client.post("/api/auth/demo").json()
    first_transaction = client.get("/api/transactions?limit=1").json()["items"][0]
    client.cookies.clear()

    second = client.post("/api/auth/demo").json()

    assert first["id"] != second["id"]
    assert first["email"] != second["email"]
    url = f"/api/transactions/{first_transaction['id']}"
    assert client.get(url).status_code == 404


def test_demo_accounts_cannot_log_in_with_a_password(client: TestClient) -> None:
    email = client.post("/api/auth/demo").json()["email"]

    for password in ("", "demo", "password", "demo-password"):
        response = client.post("/api/auth/token", data={"username": email, "password": password})
        assert response.status_code in (401, 422)


def age_user(db: Session, user_id: int, hours: int) -> None:
    db.execute(
        update(User)
        .where(User.id == user_id)
        .values(created_at=func.now() - text(f"interval '{hours} hours'"))
    )


def test_purge_removes_only_expired_demo_accounts_and_their_data(
    client: TestClient, db: Session
) -> None:
    expired = client.post("/api/auth/demo").json()["id"]
    fresh = client.post("/api/auth/demo").json()["id"]
    regular = register(client, "alice@example.com")["id"]
    assert isinstance(regular, int)
    age_user(db, expired, hours=25)
    age_user(db, fresh, hours=23)
    age_user(db, regular, hours=24 * 365)

    assert purge_expired_demo_users(db) == 1

    remaining = set(db.scalars(select(User.id)))
    assert expired not in remaining
    assert {fresh, regular} <= remaining
    orphaned = db.scalar(
        select(func.count()).select_from(Transaction).where(Transaction.user_id == expired)
    )
    assert orphaned == 0


def test_creating_a_demo_purges_expired_ones(client: TestClient, db: Session) -> None:
    expired = client.post("/api/auth/demo").json()["id"]
    age_user(db, expired, hours=25)

    client.post("/api/auth/demo")

    assert db.get(User, expired) is None


def test_demo_refuses_when_at_capacity(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "demo_max_users", 1)
    assert client.post("/api/auth/demo").status_code == 201
    client.cookies.clear()

    api = client.post("/api/auth/demo")
    page = client.post("/demo")

    assert api.status_code == 503
    assert page.status_code == 503
    assert "demo is busy" in page.text
    assert ACCESS_TOKEN_COOKIE not in client.cookies


# --- web -------------------------------------------------------------------------


def test_login_page_offers_the_demo(client: TestClient) -> None:
    assert 'action="/demo"' in client.get("/login").text


def test_demo_form_logs_in_and_shows_demo_banner(client: TestClient) -> None:
    response = client.post("/demo", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert "demo account" in client.get("/").text


def test_demo_users_can_still_open_register_page(client: TestClient) -> None:
    client.post("/demo")

    assert client.get("/register", follow_redirects=False).status_code == 200


def test_regular_users_see_no_demo_banner(client: TestClient) -> None:
    register(client, "alice@example.com")
    client.post("/login", data={"email": "alice@example.com", "password": "correct-horse-battery"})

    assert "demo account" not in client.get("/").text
