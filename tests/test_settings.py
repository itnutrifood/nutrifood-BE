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


def test_celery_settings_are_loaded_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://queue.example.test:6379/2")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://results.example.test:6379/3")
    monkeypatch.setenv("CELERY_TIMEZONE", "Asia/Yerevan")
    monkeypatch.setenv("CELERY_RESULT_EXPIRES_SECONDS", "3600")
    monkeypatch.setenv("CELERY_WORKER_CONCURRENCY", "4")
    monkeypatch.setenv("FCM_REGISTRATION_STALE_DAYS", "45")

    settings = Settings(_env_file=None)

    assert settings.celery_broker_url == "redis://queue.example.test:6379/2"
    assert settings.celery_result_backend == "redis://results.example.test:6379/3"
    assert settings.celery_timezone == "Asia/Yerevan"
    assert settings.celery_result_expires_seconds == 3600
    assert settings.celery_worker_concurrency == 4
    assert settings.fcm_registration_stale_days == 45


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
