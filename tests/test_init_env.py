from scripts.init_env import render_environment


def test_render_environment_generates_consistent_secrets() -> None:
    template = """POSTGRES_DB=nutrifood
POSTGRES_USER=nutrifood
POSTGRES_PASSWORD=
POSTGRES_HOST=db
POSTGRES_PORT=5432
DATABASE_URL=
GOOSE_DBSTRING=
ADMIN_USERNAME=
ADMIN_PASSWORD=
ADMIN_TOKEN_SECRET=
"""

    rendered = render_environment(
        template,
        postgres_password="generated-database-password",
        admin_token_secret="generated-admin-token-secret",
    )

    assert "POSTGRES_PASSWORD=generated-database-password" in rendered
    assert (
        "DATABASE_URL=postgresql://nutrifood:generated-database-password@db:5432/nutrifood"
        in rendered
    )
    assert (
        "GOOSE_DBSTRING=postgresql://nutrifood:generated-database-password"
        "@db:5432/nutrifood?sslmode=disable" in rendered
    )
    assert "ADMIN_TOKEN_SECRET=generated-admin-token-secret" in rendered
    assert "ADMIN_USERNAME=\n" in rendered
    assert "ADMIN_PASSWORD=\n" in rendered
