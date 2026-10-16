import pytest
from pydantic import ValidationError

from app.config import DEV_SECRET_KEY, Settings

STRONG_KEY = "x" * 40


@pytest.mark.parametrize(
    "url",
    ["postgres://u:p@host/db", "postgresql://u:p@host/db?sslmode=require"],
)
def test_hosted_database_urls_get_the_psycopg_driver(url: str) -> None:
    settings = Settings(database_url=url)

    assert settings.database_url.startswith("postgresql+psycopg://u:p@host/db")


def test_production_requires_a_real_secret_key() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(environment="production", secret_key=DEV_SECRET_KEY, cookie_secure=True)


def test_production_requires_secure_cookies() -> None:
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings(environment="production", secret_key=STRONG_KEY, cookie_secure=False)


def test_short_secret_keys_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(secret_key="too-short")


def test_valid_production_settings() -> None:
    settings = Settings(environment="production", secret_key=STRONG_KEY, cookie_secure=True)

    assert settings.environment == "production"
