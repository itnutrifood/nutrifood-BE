#!/usr/bin/env python3

import os
import secrets
from pathlib import Path
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE_PATH = PROJECT_ROOT / ".env.example"
ENV_PATH = PROJECT_ROOT / ".env"


def _environment_values(template: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in template.splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def render_environment(
    template: str,
    *,
    postgres_password: str,
    admin_token_secret: str,
) -> str:
    values = _environment_values(template)
    postgres_user = values.get("POSTGRES_USER", "nutrifood")
    postgres_db = values.get("POSTGRES_DB", "nutrifood")
    postgres_host = values.get("POSTGRES_HOST", "db")
    postgres_port = values.get("POSTGRES_PORT", "5432")
    encoded_user = quote(postgres_user, safe="")
    encoded_password = quote(postgres_password, safe="")
    encoded_db = quote(postgres_db, safe="")
    authority = f"{encoded_user}:{encoded_password}@{postgres_host}:{postgres_port}"
    replacements = {
        "POSTGRES_PASSWORD": postgres_password,
        "DATABASE_URL": f"postgresql://{authority}/{encoded_db}",
        "GOOSE_DBSTRING": f"postgresql://{authority}/{encoded_db}?sslmode=disable",
        "ADMIN_TOKEN_SECRET": admin_token_secret,
    }

    rendered_lines: list[str] = []
    for line in template.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _value = line.split("=", 1)
            if key in replacements:
                line = f"{key}={replacements[key]}"
        rendered_lines.append(line)
    return "\n".join(rendered_lines) + "\n"


def initialize_environment() -> bool:
    template = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")
    rendered = render_environment(
        template,
        postgres_password=secrets.token_urlsafe(32),
        admin_token_secret=secrets.token_urlsafe(48),
    )

    try:
        descriptor = os.open(ENV_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print(f"Environment already exists: {ENV_PATH}")
        return False

    with os.fdopen(descriptor, "w", encoding="utf-8") as environment_file:
        environment_file.write(rendered)
    print(f"Generated secure environment: {ENV_PATH}")
    print("Set ADMIN_USERNAME and ADMIN_PASSWORD before running `make seed-admin`.")
    return True


if __name__ == "__main__":
    initialize_environment()
