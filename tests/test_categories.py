from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.defaults import DEFAULT_CATEGORIES
from app.models import Category, CategoryType, Transaction, User
from tests.conftest import AuthedUser, create_category


def add_transaction(db: Session, user: AuthedUser, category_id: object) -> None:
    assert isinstance(category_id, int)
    db.add(
        Transaction(
            user_id=user.id,
            category_id=category_id,
            amount=Decimal("100.00"),
            occurred_on=date(2026, 10, 1),
        )
    )
    db.flush()


def test_new_users_get_default_categories(client: TestClient, alice: AuthedUser) -> None:
    categories = client.get("/api/categories", headers=alice.headers).json()

    by_type = {t: {c["name"] for c in categories if c["type"] == t} for t in CategoryType}
    assert by_type[CategoryType.EXPENSE] == set(DEFAULT_CATEGORIES[CategoryType.EXPENSE])
    assert by_type[CategoryType.INCOME] == set(DEFAULT_CATEGORIES[CategoryType.INCOME])


def test_list_filters_by_type(client: TestClient, alice: AuthedUser) -> None:
    income = client.get("/api/categories?type=income", headers=alice.headers).json()

    assert income
    assert {c["type"] for c in income} == {"income"}


def test_create_strips_name_and_rejects_blank_or_unknown_type(
    client: TestClient, alice: AuthedUser
) -> None:
    created = create_category(client, alice, "  Pets  ")
    blank = client.post(
        "/api/categories", json={"name": "   ", "type": "expense"}, headers=alice.headers
    )
    bad_type = client.post(
        "/api/categories", json={"name": "Pets", "type": "savings"}, headers=alice.headers
    )

    assert created["name"] == "Pets"
    assert blank.status_code == 422
    assert bad_type.status_code == 422


def test_names_are_unique_per_type_ignoring_case(client: TestClient, alice: AuthedUser) -> None:
    create_category(client, alice, "Pets")

    duplicate = client.post(
        "/api/categories", json={"name": "PETS", "type": "expense"}, headers=alice.headers
    )
    same_name_other_type = client.post(
        "/api/categories", json={"name": "Pets", "type": "income"}, headers=alice.headers
    )

    assert duplicate.status_code == 409
    assert same_name_other_type.status_code == 201


def test_database_enforces_case_insensitive_uniqueness(db: Session, alice: AuthedUser) -> None:
    db.add(Category(user_id=alice.id, name="TRANSPORT", type=CategoryType.EXPENSE))

    with pytest.raises(IntegrityError):
        db.flush()


def test_rename_and_retype_unused_category(client: TestClient, alice: AuthedUser) -> None:
    category = create_category(client, alice, "Pets")

    response = client.patch(
        f"/api/categories/{category['id']}",
        json={"name": "Side gigs", "type": "income"},
        headers=alice.headers,
    )

    assert response.status_code == 200
    assert response.json() == {"id": category["id"], "name": "Side gigs", "type": "income"}


def test_rename_to_existing_name_conflicts(client: TestClient, alice: AuthedUser) -> None:
    category = create_category(client, alice, "Pets")

    response = client.patch(
        f"/api/categories/{category['id']}", json={"name": "transport"}, headers=alice.headers
    )

    assert response.status_code == 409


def test_delete_unused_category(client: TestClient, alice: AuthedUser) -> None:
    category = create_category(client, alice, "Pets")

    deleted = client.delete(f"/api/categories/{category['id']}", headers=alice.headers)

    assert deleted.status_code == 204
    assert client.get(f"/api/categories/{category['id']}", headers=alice.headers).status_code == 404


def test_category_in_use_cannot_be_deleted_or_retyped_but_can_be_renamed(
    client: TestClient, db: Session, alice: AuthedUser
) -> None:
    category = create_category(client, alice, "Pets")
    add_transaction(db, alice, category["id"])
    url = f"/api/categories/{category['id']}"

    deleted = client.delete(url, headers=alice.headers)
    retyped = client.patch(url, json={"type": "income"}, headers=alice.headers)
    renamed = client.patch(url, json={"name": "Pet care"}, headers=alice.headers)

    assert deleted.status_code == 409
    assert retyped.status_code == 409
    assert renamed.status_code == 200


def test_users_cannot_see_or_touch_each_others_categories(
    client: TestClient, alice: AuthedUser, bob: AuthedUser
) -> None:
    alices = create_category(client, alice, "Pets")
    url = f"/api/categories/{alices['id']}"

    bobs_list = client.get("/api/categories", headers=bob.headers).json()
    assert alices["id"] not in {c["id"] for c in bobs_list}
    assert client.get(url, headers=bob.headers).status_code == 404
    assert client.patch(url, json={"name": "Mine"}, headers=bob.headers).status_code == 404
    assert client.delete(url, headers=bob.headers).status_code == 404
    assert client.get(url, headers=alice.headers).json()["name"] == "Pets"


def test_categories_require_authentication(client: TestClient) -> None:
    assert client.get("/api/categories").status_code == 401


def test_database_rejects_transaction_with_another_users_category(
    client: TestClient, db: Session, alice: AuthedUser, bob: AuthedUser
) -> None:
    bobs = create_category(client, bob, "Bob only")

    with pytest.raises(IntegrityError):
        add_transaction(db, alice, bobs["id"])


def test_database_rejects_non_positive_amount(
    client: TestClient, db: Session, alice: AuthedUser
) -> None:
    category = create_category(client, alice, "Pets")
    db.add(
        Transaction(
            user_id=alice.id,
            category_id=category["id"],
            amount=Decimal("0"),
            occurred_on=date(2026, 10, 1),
        )
    )

    with pytest.raises(IntegrityError):
        db.flush()


def test_deleting_a_user_cascades_to_categories_and_transactions(
    client: TestClient, db: Session, alice: AuthedUser
) -> None:
    category = create_category(client, alice, "Pets")
    add_transaction(db, alice, category["id"])

    db.execute(delete(User).where(User.id == alice.id))

    assert db.scalar(select(func.count()).select_from(Category)) == 0
    assert db.scalar(select(func.count()).select_from(Transaction)) == 0
