import re
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

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
    statistics_cache_url: str = "redis://redis:6379/2"

    admin_username: str = ""
    admin_password: str = ""
    admin_token_secret: str = ""
    admin_token_algorithm: Literal["HS256"] = "HS256"
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

    @model_validator(mode="after")
    def validate_production_security(self) -> Self:
        if not self.is_production:
            return self

        errors: list[str] = []
        if self.debug:
            errors.append("DEBUG must be false in production")
        if self.postgres_password in {"", "nutrifood"}:
            errors.append("POSTGRES_PASSWORD must be a non-default secret in production")
        database_password = urlsplit(self.database_url).password
        if database_password in {None, "", "nutrifood"}:
            errors.append("DATABASE_URL must contain a non-default password in production")
        if self.admin_username == "admin@mail.com":
            errors.append("ADMIN_USERNAME must not use the published bootstrap identity")
        if self.admin_password == "123456" or (
            self.admin_password and len(self.admin_password) < 14
        ):
            errors.append("ADMIN_PASSWORD must be empty or contain at least 14 characters")
        if (
            len(self.admin_token_secret.encode("utf-8")) < 32
            or self.admin_token_secret == "change-me-to-a-long-random-secret"
        ):
            errors.append(
                "ADMIN_TOKEN_SECRET must contain at least 32 bytes of unique key material"
            )

        if errors:
            raise ValueError("; ".join(errors))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
