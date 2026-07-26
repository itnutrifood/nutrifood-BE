import pytest
from backend.config.settings import Settings


def test_cors_origins_are_loaded_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "CORS_ORIGINS",
        '["https://app.example.com","https://admin.example.com"]',
    )

    settings = Settings(_env_file=None)

    assert settings.cors_origins == (
        "https://app.example.com",
        "https://admin.example.com",
    )
