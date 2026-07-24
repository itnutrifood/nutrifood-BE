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

    user_token_secret: str = ""
    user_token_algorithm: str = "HS256"
    user_access_token_expire_minutes: int = Field(default=15, gt=0)
    user_refresh_token_expire_days: int = Field(default=30, gt=0)

    firebase_credentials_path: Path | None = None
    firebase_project_id: str | None = None

    @property
    def api_root_prefix(self) -> str:
        prefix = self.api_prefix.rstrip("/") or "/api"
        base_prefix, _, last_segment = prefix.rpartition("/")
        if base_prefix and re.fullmatch(r"v[0-9]+", last_segment):
            return base_prefix
        return prefix


@lru_cache
def get_settings() -> Settings:
    return Settings()
