from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://expense:expense@localhost:5432/expense"
    # HS256 needs at least 32 bytes of key. The default is for local development only.
    secret_key: str = Field(default="dev-only-insecure-secret-key-change-me", min_length=32)
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
