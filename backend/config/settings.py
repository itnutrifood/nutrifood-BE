import re
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "NutriFood"
    environment: str = "local"
    debug: bool = True
    api_prefix: str = "/api"
    cors_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://localhost:5173",
    )

    postgres_db: str = "nutrifood"
    postgres_user: str = "nutrifood"
    postgres_password: str = "nutrifood"
    postgres_host: str = "db"
    postgres_port: int = 5432
    database_url: str = Field(
        default="postgresql://nutrifood:nutrifood@db:5432/nutrifood",
        validation_alias="DATABASE_URL",
    )

    admin_username: str = ""
    admin_password: str = ""
    admin_token_secret: str = ""
    admin_token_algorithm: str = "HS256"
    admin_access_token_expire_minutes: int = Field(default=15, gt=0)
    admin_refresh_token_expire_days: int = Field(default=7, gt=0)

    firebase_credentials_path: Path | None = None
    firebase_project_id: str | None = None
    firebase_require_verified_email: bool = True
    firebase_allowed_sign_in_providers: frozenset[str] = frozenset({"password", "google.com"})

    r2_endpoint_url: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = ""
    r2_public_base_url: str = ""
    r2_upload_url_expire_seconds: int = Field(default=900, ge=60, le=3600)

    @property
    def api_root_prefix(self) -> str:
        prefix = self.api_prefix.rstrip("/") or "/api"
        base_prefix, _, last_segment = prefix.rpartition("/")
        if base_prefix and re.fullmatch(r"v[0-9]+", last_segment):
            return base_prefix
        return prefix

    @property
    def is_production(self) -> bool:
        return self.environment.strip().casefold() in {"prod", "production"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
