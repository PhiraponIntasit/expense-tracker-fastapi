from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET_KEY = "dev-only-insecure-secret-key-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "production"] = "development"
    database_url: str = "postgresql+psycopg://expense:expense@localhost:5432/expense"
    # HS256 needs at least 32 bytes of key. The default is for local development only.
    secret_key: str = Field(default=DEV_SECRET_KEY, min_length=32)
    access_token_expire_minutes: int = 60 * 24
    # Set to true in production so the auth cookie is only sent over HTTPS.
    cookie_secure: bool = False
    # Demo accounts are deleted after this many hours, and at most this many
    # can exist at once (each holds about a year of sample transactions).
    demo_max_age_hours: int = 24
    demo_max_users: int = 500

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        # Hosted providers (Neon, Render) hand out plain postgres:// URLs;
        # SQLAlchemy needs the driver spelled out.
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value.removeprefix(prefix)
        return value

    @model_validator(mode="after")
    def production_is_locked_down(self) -> Self:
        # Fail at startup rather than run production with a guessable token key
        # or an auth cookie that could travel over plain HTTP.
        if self.environment == "production":
            if self.secret_key == DEV_SECRET_KEY:
                raise ValueError("SECRET_KEY must be set in production")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
