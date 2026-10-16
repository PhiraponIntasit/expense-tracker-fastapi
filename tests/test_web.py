import pytest
from fastapi.testclient import TestClient

from app.security import ACCESS_TOKEN_COOKIE
from tests.conftest import PASSWORD, register

APP_PAGES = ["/", "/transactions", "/categories"]


def log_in_with_form(client: TestClient, email: str, password: str = PASSWORD) -> None:
    response = client.post(
        "/login", data={"email": email, "password": password}, follow_redirects=False
    )
    assert response.status_code == 303, response.text


@pytest.mark.parametrize("path", APP_PAGES)
def test_app_pages_redirect_to_login_when_logged_out(client: TestClient, path: str) -> None:
    response = client.get(path, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


@pytest.mark.parametrize("path", APP_PAGES)
def test_app_pages_render_for_logged_in_user(client: TestClient, path: str) -> None:
    register(client, "alice@example.com")
    log_in_with_form(client, "alice@example.com")

    response = client.get(path)

    assert response.status_code == 200
    assert "alice@example.com" in response.text
    assert "default-src 'self'" in response.headers["content-security-policy"]


def test_bearer_header_alone_does_not_open_pages(client: TestClient) -> None:
    register(client, "alice@example.com")
    token = client.post(
        "/api/auth/token", data={"username": "alice@example.com", "password": PASSWORD}
    ).json()["access_token"]
    client.cookies.clear()

    response = client.get("/", headers={"Authorization": f"Bearer {token}"}, follow_redirects=False)

    assert response.status_code == 303


def test_register_form_creates_account_and_logs_in(client: TestClient) -> None:
    response = client.post(
        "/register",
        data={"email": "New@Example.com", "password": PASSWORD},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert ACCESS_TOKEN_COOKIE in client.cookies
    assert client.get("/api/users/me").json()["email"] == "new@example.com"
    assert len(client.get("/api/categories").json()) > 0


@pytest.mark.parametrize(
    ("email", "password", "status", "message"),
    [
        ("not-an-email", PASSWORD, 422, "valid email"),
        ("bob@example.com", "short", 422, "8 to 128"),
        ("alice@example.com", PASSWORD, 409, "already exists"),
    ],
)
def test_register_form_shows_errors(
    client: TestClient, email: str, password: str, status: int, message: str
) -> None:
    register(client, "alice@example.com")

    response = client.post("/register", data={"email": email, "password": password})

    assert response.status_code == status
    assert message in response.text
    assert f'value="{email}"' in response.text  # keeps what the user typed


def test_login_form_rejects_bad_password(client: TestClient) -> None:
    register(client, "alice@example.com")

    response = client.post(
        "/login", data={"email": "alice@example.com", "password": "wrong-password"}
    )

    assert response.status_code == 401
    assert "Incorrect email or password" in response.text
    assert ACCESS_TOKEN_COOKIE not in client.cookies


def test_login_page_redirects_when_already_logged_in(client: TestClient) -> None:
    register(client, "alice@example.com")
    log_in_with_form(client, "alice@example.com")

    for path in ("/login", "/register"):
        assert client.get(path, follow_redirects=False).headers["location"] == "/"


def test_logout_form_clears_session(client: TestClient) -> None:
    register(client, "alice@example.com")
    log_in_with_form(client, "alice@example.com")

    response = client.post("/logout", follow_redirects=False)

    assert response.headers["location"] == "/login"
    assert client.get("/", follow_redirects=False).status_code == 303


def test_form_output_is_html_escaped(client: TestClient) -> None:
    response = client.post("/login", data={"email": '"><script>alert(1)</script>', "password": "x"})

    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_cross_origin_writes_are_rejected(client: TestClient) -> None:
    register(client, "alice@example.com")

    cross_site = client.post(
        "/login",
        data={"email": "alice@example.com", "password": PASSWORD},
        headers={"Origin": "https://evil.example"},
        follow_redirects=False,
    )
    same_site = client.post(
        "/login",
        data={"email": "alice@example.com", "password": PASSWORD},
        headers={"Origin": "http://testserver"},
        follow_redirects=False,
    )
    cross_site_read = client.get("/api/categories", headers={"Origin": "https://evil.example"})

    assert cross_site.status_code == 403
    assert same_site.status_code == 303
    assert cross_site_read.status_code == 200  # reads are protected by CORS, not this check


def test_static_assets_are_served(client: TestClient) -> None:
    for path in (
        "/static/vendor/pico.min.css",
        "/static/vendor/chart.umd.min.js",
        "/static/js/dashboard.js",
    ):
        assert client.get(path).status_code == 200, path
