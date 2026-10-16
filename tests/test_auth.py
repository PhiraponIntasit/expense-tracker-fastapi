from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient

from app.config import get_settings
from app.security import ACCESS_TOKEN_COOKIE, ALGORITHM, create_access_token
from tests.conftest import PASSWORD, bearer_headers, register


def test_register_creates_user_with_normalized_email(client: TestClient) -> None:
    body = register(client, "  Alice@Example.COM ")

    assert body["email"] == "alice@example.com"
    assert body["is_demo"] is False
    assert "password" not in body
    assert "password_hash" not in body


def test_register_rejects_duplicate_email_regardless_of_case(client: TestClient) -> None:
    register(client, "alice@example.com")

    response = client.post(
        "/api/auth/register", json={"email": "ALICE@example.com", "password": PASSWORD}
    )

    assert response.status_code == 409


def test_register_validates_email_and_password_length(client: TestClient) -> None:
    bad_email = client.post("/api/auth/register", json={"email": "nope", "password": PASSWORD})
    short_password = client.post(
        "/api/auth/register", json={"email": "bob@example.com", "password": "short"}
    )

    assert bad_email.status_code == 422
    assert short_password.status_code == 422


def test_login_returns_bearer_token_usable_on_api(client: TestClient) -> None:
    register(client, "alice@example.com")

    headers = bearer_headers(client, "Alice@Example.com")
    me = client.get("/api/users/me", headers=headers)

    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"


def test_login_sets_httponly_lax_cookie_that_authenticates(client: TestClient) -> None:
    register(client, "alice@example.com")

    response = client.post(
        "/api/auth/token", data={"username": "alice@example.com", "password": PASSWORD}
    )

    set_cookie = response.headers["set-cookie"].lower()
    assert set_cookie.startswith(f"{ACCESS_TOKEN_COOKIE}=")
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert client.get("/api/users/me").json()["email"] == "alice@example.com"


def test_login_rejects_wrong_password_and_unknown_email_alike(client: TestClient) -> None:
    register(client, "alice@example.com")

    wrong_password = client.post(
        "/api/auth/token", data={"username": "alice@example.com", "password": "wrong-password"}
    )
    unknown_email = client.post(
        "/api/auth/token", data={"username": "nobody@example.com", "password": PASSWORD}
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert ACCESS_TOKEN_COOKIE not in client.cookies


def test_me_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/users/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_logout_clears_cookie(client: TestClient) -> None:
    register(client, "alice@example.com")
    client.post("/api/auth/token", data={"username": "alice@example.com", "password": PASSWORD})

    logout = client.post("/api/auth/logout")

    assert logout.status_code == 204
    assert client.get("/api/users/me").status_code == 401


def test_bearer_header_takes_precedence_over_cookie(client: TestClient) -> None:
    register(client, "alice@example.com")
    register(client, "bob@example.com")
    bob_headers = bearer_headers(client, "bob@example.com")
    client.post("/api/auth/token", data={"username": "alice@example.com", "password": PASSWORD})

    me = client.get("/api/users/me", headers=bob_headers)

    assert me.json()["email"] == "bob@example.com"


def test_rejects_expired_tampered_and_orphaned_tokens(client: TestClient) -> None:
    user_id = register(client, "alice@example.com")["id"]
    assert isinstance(user_id, int)
    settings = get_settings()
    expired = jwt.encode(
        {"sub": str(user_id), "exp": datetime.now(UTC) - timedelta(minutes=1)},
        settings.secret_key,
        algorithm=ALGORITHM,
    )
    wrong_key = jwt.encode(
        {"sub": str(user_id), "exp": datetime.now(UTC) + timedelta(minutes=5)},
        "a-different-secret-that-is-long-enough",
        algorithm=ALGORITHM,
    )
    no_such_user = create_access_token(user_id + 10_000)

    for token in (expired, wrong_key, no_such_user, "garbage"):
        response = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401, token
