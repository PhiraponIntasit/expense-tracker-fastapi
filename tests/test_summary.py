from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.conftest import AuthedUser, create_category


@pytest.fixture
def food(client: TestClient, alice: AuthedUser) -> dict[str, Any]:
    return create_category(client, alice, "Food")


@pytest.fixture
def rent(client: TestClient, alice: AuthedUser) -> dict[str, Any]:
    return create_category(client, alice, "Rent")


@pytest.fixture
def salary(client: TestClient, alice: AuthedUser) -> dict[str, Any]:
    return create_category(client, alice, "Paycheck", type="income")


def add(
    client: TestClient, user: AuthedUser, category: dict[str, Any], amount: str, on: str
) -> None:
    response = client.post(
        "/api/transactions",
        json={"category_id": category["id"], "amount": amount, "occurred_on": on},
        headers=user.headers,
    )
    assert response.status_code == 201, response.text


def get(client: TestClient, user: AuthedUser, url: str) -> Any:
    response = client.get(url, headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


# --- monthly ---------------------------------------------------------------------


def test_monthly_fills_empty_months_with_zero(
    client: TestClient, alice: AuthedUser, food: dict[str, Any], salary: dict[str, Any]
) -> None:
    add(client, alice, salary, "30000", "2026-08-25")
    add(client, alice, food, "120.50", "2026-08-03")
    add(client, alice, food, "80", "2026-10-15")

    months = get(client, alice, "/api/summary/monthly?from=2026-07&to=2026-11")

    assert months == [
        {"month": "2026-07", "income": "0.00", "expense": "0.00", "net": "0.00"},
        {"month": "2026-08", "income": "30000.00", "expense": "120.50", "net": "29879.50"},
        {"month": "2026-09", "income": "0.00", "expense": "0.00", "net": "0.00"},
        {"month": "2026-10", "income": "0.00", "expense": "80.00", "net": "-80.00"},
        {"month": "2026-11", "income": "0.00", "expense": "0.00", "net": "0.00"},
    ]


def test_monthly_keeps_month_edges_and_crosses_year_boundary(
    client: TestClient, alice: AuthedUser, food: dict[str, Any]
) -> None:
    for day, amount in [
        ("2026-11-30", "1"),
        ("2026-12-01", "2"),
        ("2026-12-31", "4"),
        ("2027-01-01", "8"),
        ("2027-01-31", "16"),
        ("2027-02-01", "32"),
    ]:
        add(client, alice, food, amount, day)

    months = get(client, alice, "/api/summary/monthly?from=2026-12&to=2027-01")

    assert [(m["month"], m["expense"]) for m in months] == [
        ("2026-12", "6.00"),
        ("2027-01", "24.00"),
    ]


def test_monthly_totals_are_exact_decimals(
    client: TestClient, alice: AuthedUser, food: dict[str, Any]
) -> None:
    for _ in range(3):
        add(client, alice, food, "0.10", "2026-10-01")
    add(client, alice, food, "0.20", "2026-10-02")

    (october,) = get(client, alice, "/api/summary/monthly?from=2026-10&to=2026-10")

    assert october["expense"] == "0.50"


@pytest.mark.parametrize("zone", ["Pacific/Kiritimati", "America/Los_Angeles", "Asia/Bangkok"])
def test_monthly_is_unaffected_by_database_time_zone(
    client: TestClient, db: Session, alice: AuthedUser, food: dict[str, Any], zone: str
) -> None:
    add(client, alice, food, "10", "2026-10-31")
    add(client, alice, food, "20", "2026-11-01")
    db.execute(text(f"SET TIME ZONE '{zone}'"))

    months = get(client, alice, "/api/summary/monthly?from=2026-10&to=2026-11")

    assert [m["expense"] for m in months] == ["10.00", "20.00"]


def test_monthly_defaults_to_twelve_months_ending_this_month(
    client: TestClient, alice: AuthedUser
) -> None:
    months = get(client, alice, "/api/summary/monthly")

    assert len(months) == 12
    assert months[-1]["month"] == f"{datetime.now(UTC):%Y-%m}"


def test_monthly_only_counts_own_transactions(
    client: TestClient, alice: AuthedUser, bob: AuthedUser, food: dict[str, Any]
) -> None:
    add(client, alice, food, "10", "2026-10-01")

    (october,) = get(client, bob, "/api/summary/monthly?from=2026-10&to=2026-10")

    assert october["expense"] == "0.00"


@pytest.mark.parametrize(
    "query",
    [
        "from=2026-11&to=2026-10",  # reversed
        "from=2016-10&to=2026-10",  # 121 months
        "from=2026-13&to=2026-12",  # not a month
        "to=26-10",
    ],
)
def test_monthly_rejects_invalid_ranges(client: TestClient, alice: AuthedUser, query: str) -> None:
    response = client.get(f"/api/summary/monthly?{query}", headers=alice.headers)

    assert response.status_code == 422


def test_monthly_accepts_maximum_range(client: TestClient, alice: AuthedUser) -> None:
    months = get(client, alice, "/api/summary/monthly?from=2016-11&to=2026-10")

    assert len(months) == 120


# --- by category -----------------------------------------------------------------


def test_by_category_sorts_largest_first_and_skips_empty_categories(
    client: TestClient,
    alice: AuthedUser,
    food: dict[str, Any],
    rent: dict[str, Any],
    salary: dict[str, Any],
) -> None:
    add(client, alice, food, "100", "2026-10-01")
    add(client, alice, food, "150.25", "2026-10-31")
    add(client, alice, rent, "8000", "2026-10-05")
    add(client, alice, rent, "8000", "2026-09-05")  # other month
    add(client, alice, salary, "30000", "2026-10-25")  # other type

    totals = get(client, alice, "/api/summary/by-category?month=2026-10")

    assert totals == [
        {"category_id": rent["id"], "name": "Rent", "total": "8000.00"},
        {"category_id": food["id"], "name": "Food", "total": "250.25"},
    ]


def test_by_category_for_income(
    client: TestClient, alice: AuthedUser, food: dict[str, Any], salary: dict[str, Any]
) -> None:
    add(client, alice, food, "100", "2026-10-01")
    add(client, alice, salary, "30000", "2026-10-25")

    totals = get(client, alice, "/api/summary/by-category?month=2026-10&type=income")

    assert totals == [{"category_id": salary["id"], "name": "Paycheck", "total": "30000.00"}]


def test_by_category_only_counts_own_transactions(
    client: TestClient, alice: AuthedUser, bob: AuthedUser, food: dict[str, Any]
) -> None:
    add(client, alice, food, "10", "2026-10-01")

    assert get(client, bob, "/api/summary/by-category?month=2026-10") == []


def test_summary_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/summary/monthly").status_code == 401
    assert client.get("/api/summary/by-category").status_code == 401
