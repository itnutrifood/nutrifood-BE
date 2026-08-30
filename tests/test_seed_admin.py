import pytest
from scripts.seed_admin import validate_admin_seed_configuration


def test_admin_seed_rejects_published_defaults() -> None:
    with pytest.raises(SystemExit, match="published example identity"):
        validate_admin_seed_configuration(
            "admin@mail.com",
            "123456",
            "change-me-to-a-long-random-secret",
        )


def test_admin_seed_rejects_short_password() -> None:
    with pytest.raises(SystemExit, match="at least 14 characters"):
        validate_admin_seed_configuration(
            "operations@example.test",
            "too-short",
            "unique-admin-token-secret-with-at-least-32-bytes",
        )


def test_admin_seed_accepts_unique_strong_configuration() -> None:
    validate_admin_seed_configuration(
        "operations@example.test",
        "a-long-unique-admin-password",
        "unique-admin-token-secret-with-at-least-32-bytes",
    )
