import csv
import io
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import AuthedUser, create_category


@pytest.fixture
def food(client: TestClient, alice: AuthedUser) -> dict[str, Any]:
    return create_category(client, alice, "Food")


@pytest.fixture
def salary(client: TestClient, alice: AuthedUser) -> dict[str, Any]:
    return create_category(client, alice, "Paycheck", type="income")


def add(
    client: TestClient,
    user: AuthedUser,
    category: dict[str, Any],
    amount: str,
    on: str,
    note: str | None = None,
) -> dict[str, Any]:
    response = client.post(
        "/api/transactions",
        json={"category_id": category["id"], "amount": amount, "occurred_on": on, "note": note},
        headers=user.headers,
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def listing(client: TestClient, user: AuthedUser, query: str = "") -> dict[str, Any]:
    response = client.get(f"/api/transactions?{query}", headers=user.headers)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


# --- create / validation ---------------------------------------------------------


def test_create_returns_category_and_exact_amount(
    client: TestClient, alice: AuthedUser, food: dict[str, Any]
) -> None:
    created = add(client, alice, food, "1234.5", "2026-10-08", note="  Lunch  ")

    assert created["amount"] == "1234.50"
    assert created["occurred_on"] == "2026-10-08"
    assert created["note"] == "Lunch"
    assert created["category"] == {"id": food["id"], "name": "Food", "type": "expense"}


@pytest.mark.parametrize("amount", ["0", "-5", "1.005", "10000000000.00", "abc"])
def test_create_rejects_invalid_amounts(
    client: TestClient, alice: AuthedUser, food: dict[str, Any], amount: str
) -> None:
    response = client.post(
        "/api/transactions",
        json={"category_id": food["id"], "amount": amount, "occurred_on": "2026-10-08"},
        headers=alice.headers,
    )

    assert response.status_code == 422


def test_blank_note_is_stored_as_null_and_long_note_is_rejected(
    client: TestClient, alice: AuthedUser, food: dict[str, Any]
) -> None:
    blank = add(client, alice, food, "10", "2026-10-08", note="   ")
    too_long = client.post(
        "/api/transactions",
        json={
            "category_id": food["id"],
            "amount": "10",
            "occurred_on": "2026-10-08",
            "note": "x" * 201,
        },
        headers=alice.headers,
    )

    assert blank["note"] is None
    assert too_long.status_code == 422


def test_create_with_unknown_or_foreign_category_is_404(
    client: TestClient, alice: AuthedUser, bob: AuthedUser
) -> None:
    bobs = create_category(client, bob, "Bob's")

    for category_id in (bobs["id"], 999_999):
        response = client.post(
            "/api/transactions",
            json={"category_id": category_id, "amount": "10", "occurred_on": "2026-10-08"},
            headers=alice.headers,
        )
        assert response.status_code == 404


# --- read / update / delete ------------------------------------------------------


def test_update_changes_fields_and_clears_note_only_when_sent(
    client: TestClient, alice: AuthedUser, food: dict[str, Any], salary: dict[str, Any]
) -> None:
    created = add(client, alice, food, "10", "2026-10-08", note="Lunch")
    url = f"/api/transactions/{created['id']}"

    moved = client.patch(
        url, json={"category_id": salary["id"], "amount": "99.99"}, headers=alice.headers
    ).json()
    assert moved["category"]["type"] == "income"
    assert moved["amount"] == "99.99"
    assert moved["note"] == "Lunch"

    cleared = client.patch(url, json={"note": None}, headers=alice.headers).json()
    assert cleared["note"] is None
    assert cleared["amount"] == "99.99"


def test_update_rejects_foreign_category_and_invalid_amount(
    client: TestClient, alice: AuthedUser, bob: AuthedUser, food: dict[str, Any]
) -> None:
    created = add(client, alice, food, "10", "2026-10-08")
    bobs = create_category(client, bob, "Bob's")
    url = f"/api/transactions/{created['id']}"

    foreign = client.patch(url, json={"category_id": bobs["id"]}, headers=alice.headers)
    negative = client.patch(url, json={"amount": "-1"}, headers=alice.headers)

    assert foreign.status_code == 404
    assert negative.status_code == 422
    assert client.get(url, headers=alice.headers).json()["category"]["id"] == food["id"]


def test_delete_transaction_then_its_category_can_be_deleted(
    client: TestClient, alice: AuthedUser, food: dict[str, Any]
) -> None:
    created = add(client, alice, food, "10", "2026-10-08")
    category_url = f"/api/categories/{food['id']}"
    assert client.delete(category_url, headers=alice.headers).status_code == 409

    deleted = client.delete(f"/api/transactions/{created['id']}", headers=alice.headers)

    assert deleted.status_code == 204
    assert (
        client.get(f"/api/transactions/{created['id']}", headers=alice.headers).status_code == 404
    )
    assert client.delete(category_url, headers=alice.headers).status_code == 204


def test_users_cannot_see_or_touch_each_others_transactions(
    client: TestClient, alice: AuthedUser, bob: AuthedUser, food: dict[str, Any]
) -> None:
    created = add(client, alice, food, "10", "2026-10-08")
    url = f"/api/transactions/{created['id']}"

    assert listing(client, bob)["total"] == 0
    assert listing(client, bob, f"category_id={food['id']}")["total"] == 0
    assert client.get(url, headers=bob.headers).status_code == 404
    assert client.patch(url, json={"amount": "1"}, headers=bob.headers).status_code == 404
    assert client.delete(url, headers=bob.headers).status_code == 404
    assert client.get(url, headers=alice.headers).json()["amount"] == "10.00"


def test_transactions_require_authentication(client: TestClient) -> None:
    assert client.get("/api/transactions").status_code == 401
    assert client.get("/api/transactions/export.csv").status_code == 401


# --- listing, filters, totals ----------------------------------------------------


def test_month_filter_includes_first_and_last_day_only(
    client: TestClient, alice: AuthedUser, food: dict[str, Any]
) -> None:
    for day in ("2026-09-30", "2026-10-01", "2026-10-31", "2026-11-01"):
        add(client, alice, food, "1", day)

    october = listing(client, alice, "month=2026-10")

    assert [t["occurred_on"] for t in october["items"]] == ["2026-10-31", "2026-10-01"]
    assert october["total"] == 2


def test_december_filter_does_not_leak_into_next_year(
    client: TestClient, alice: AuthedUser, food: dict[str, Any]
) -> None:
    add(client, alice, food, "1", "2026-12-31")
    add(client, alice, food, "1", "2027-01-01")

    assert listing(client, alice, "month=2026-12")["total"] == 1


@pytest.mark.parametrize("month", ["2026-13", "2026-1", "26-10", "october"])
def test_invalid_month_is_rejected(client: TestClient, alice: AuthedUser, month: str) -> None:
    response = client.get(f"/api/transactions?month={month}", headers=alice.headers)

    assert response.status_code == 422


def test_filters_by_type_and_category_and_totals_split_by_type(
    client: TestClient, alice: AuthedUser, food: dict[str, Any], salary: dict[str, Any]
) -> None:
    add(client, alice, food, "100.10", "2026-10-02")
    add(client, alice, food, "0.20", "2026-10-03")
    add(client, alice, salary, "50000", "2026-10-01")

    everything = listing(client, alice)
    expenses = listing(client, alice, "type=expense")
    by_category = listing(client, alice, f"category_id={salary['id']}")

    assert (everything["total"], everything["income"], everything["expense"]) == (
        3,
        "50000.00",
        "100.30",
    )
    assert (expenses["total"], expenses["income"], expenses["expense"]) == (2, "0.00", "100.30")
    assert by_category["total"] == 1
    assert by_category["items"][0]["category"]["id"] == salary["id"]


def test_pagination_is_newest_first_and_totals_cover_all_pages(
    client: TestClient, alice: AuthedUser, food: dict[str, Any]
) -> None:
    for day in range(1, 6):
        add(client, alice, food, "10", f"2026-10-0{day}")

    first = listing(client, alice, "limit=2")
    last = listing(client, alice, "limit=2&offset=4")

    assert [t["occurred_on"] for t in first["items"]] == ["2026-10-05", "2026-10-04"]
    assert [t["occurred_on"] for t in last["items"]] == ["2026-10-01"]
    assert first["total"] == last["total"] == 5
    assert first["expense"] == "50.00"


def test_page_size_is_bounded(client: TestClient, alice: AuthedUser) -> None:
    assert client.get("/api/transactions?limit=101", headers=alice.headers).status_code == 422
    assert client.get("/api/transactions?limit=0", headers=alice.headers).status_code == 422


# --- CSV export ------------------------------------------------------------------


def test_export_csv_applies_filters_and_names_file_by_month(
    client: TestClient, alice: AuthedUser, food: dict[str, Any], salary: dict[str, Any]
) -> None:
    add(client, alice, food, "45.5", "2026-10-02", note="ข้าวมันไก่")
    add(client, alice, salary, "50000", "2026-10-01")
    add(client, alice, food, "10", "2026-09-30")

    response = client.get("/api/transactions/export.csv?month=2026-10", headers=alice.headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert 'filename="transactions-2026-10.csv"' in response.headers["content-disposition"]
    assert response.text.startswith("﻿")
    rows = list(csv.reader(io.StringIO(response.text.removeprefix("﻿"))))
    assert rows == [
        ["date", "type", "category", "amount", "note"],
        ["2026-10-02", "expense", "Food", "45.50", "ข้าวมันไก่"],
        ["2026-10-01", "income", "Paycheck", "50000.00", ""],
    ]


def test_export_csv_neutralizes_spreadsheet_formulas(
    client: TestClient, alice: AuthedUser, food: dict[str, Any]
) -> None:
    add(client, alice, food, "1", "2026-10-01", note='=HYPERLINK("http://evil")')

    response = client.get("/api/transactions/export.csv", headers=alice.headers)

    note = list(csv.reader(io.StringIO(response.text.removeprefix("﻿"))))[1][4]
    assert note == '\'=HYPERLINK("http://evil")'


def test_export_csv_only_contains_own_transactions(
    client: TestClient, alice: AuthedUser, bob: AuthedUser, food: dict[str, Any]
) -> None:
    add(client, alice, food, "1", "2026-10-01")

    response = client.get("/api/transactions/export.csv", headers=bob.headers)

    assert response.text.removeprefix("﻿").strip() == "date,type,category,amount,note"
