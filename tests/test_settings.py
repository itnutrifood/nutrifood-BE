import pytest
from backend.apps.assets.exceptions import AssetStorageNotConfiguredError
from backend.apps.assets.storage import R2ObjectStorage
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


def test_r2_upload_expiration_is_loaded_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("R2_UPLOAD_URL_EXPIRE_SECONDS", "600")

    settings = Settings(_env_file=None)

    assert settings.r2_upload_url_expire_seconds == 600


def test_r2_storage_requires_complete_configuration() -> None:
    settings = Settings(
        _env_file=None,
        r2_endpoint_url="",
        r2_access_key_id="",
        r2_secret_access_key="",
        r2_bucket_name="",
        r2_public_base_url="",
    )

    with pytest.raises(AssetStorageNotConfiguredError):
        R2ObjectStorage.from_settings(settings)
