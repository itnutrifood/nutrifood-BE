import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

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

    log_directory: Path = Path("logs")
    log_component: str = Field(default="api", pattern=r"^[a-z0-9][a-z0-9_-]*$")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_retention_days: int = Field(default=30, ge=1, le=3650)
    log_rotation_utc: bool = True

    postgres_db: str = "nutrifood"
    postgres_user: str = "nutrifood"
    postgres_password: str = "nutrifood"
    postgres_host: str = "db"
    postgres_port: int = 5432
    database_url: str = Field(
        default="postgresql://nutrifood:nutrifood@db:5432/nutrifood",
        validation_alias="DATABASE_URL",
    )
    catalog_currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")

    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
    celery_timezone: str = "UTC"
    celery_result_expires_seconds: int = Field(default=604_800, ge=60)
    celery_worker_concurrency: int = Field(default=2, ge=1)

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
    fcm_registration_stale_days: int = Field(default=30, ge=1)

    sendgrid_api_key: str = ""
    sendgrid_from_email: str = ""

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
