from configparser import ConfigParser
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR_DIRECTORY = PROJECT_ROOT / "deploy" / "supervisor"


def supervisor_program(config_name: str, program_name: str) -> ConfigParser:
    config = ConfigParser(interpolation=None)
    config.read(SUPERVISOR_DIRECTORY / config_name)
    assert config.sections() == [f"program:{program_name}"]
    return config


def assert_managed_process(config: ConfigParser, program_name: str) -> None:
    process = config[f"program:{program_name}"]
    assert process["directory"] == "__PROJECT_PATH__"
    assert process["user"] == "__APP_USER__"
    assert process.getboolean("autostart") is True
    assert process.getboolean("autorestart") is True
    assert process.getboolean("stopasgroup") is True
    assert process.getboolean("killasgroup") is True


def test_supervisor_runs_api() -> None:
    config = supervisor_program("nutrifood.conf", "nutrifood")
    assert_managed_process(config, "nutrifood")

    api = config["program:nutrifood"]
    assert api["command"] == (
        "__VENV_PATH__/bin/uvicorn backend.config.asgi:app --host 127.0.0.1 --port 8000 "
        "--workers 2 --proxy-headers --forwarded-allow-ips=127.0.0.1"
    )
    assert 'LOG_COMPONENT="api"' in api["environment"]


def test_supervisor_runs_celery_worker_on_application_queues() -> None:
    config = supervisor_program(
        "nutrifood-celery-worker.conf",
        "nutrifood-celery-worker",
    )
    assert_managed_process(config, "nutrifood-celery-worker")

    worker = config["program:nutrifood-celery-worker"]
    assert worker["command"] == (
        "__VENV_PATH__/bin/celery -A backend.config.celery_app:app worker "
        "--loglevel=INFO --queues=default,periodic"
    )
    assert 'LOG_COMPONENT="celery-worker"' in worker["environment"]


def test_supervisor_runs_celery_beat_with_persistent_schedule() -> None:
    config = supervisor_program(
        "nutrifood-celery-beat.conf",
        "nutrifood-celery-beat",
    )
    assert_managed_process(config, "nutrifood-celery-beat")

    beat = config["program:nutrifood-celery-beat"]
    assert beat["command"] == (
        "__VENV_PATH__/bin/celery -A backend.config.celery_app:app beat --loglevel=INFO "
        "--schedule=/var/lib/nutrifood/celerybeat-schedule"
    )
    assert 'LOG_COMPONENT="celery-beat"' in beat["environment"]


def test_installer_renders_and_manages_all_backend_processes() -> None:
    installer = (SUPERVISOR_DIRECTORY / "install.sh").read_text()

    assert "nutrifood-celery-worker" in installer
    assert "nutrifood-celery-beat" in installer
    assert 'for template in "$template_directory"/*.conf' in installer
    assert "supervisorctl reread" in installer
    assert "supervisorctl update" in installer
    assert 'supervisorctl restart "${programs[@]}"' in installer
    assert 'supervisorctl status "${programs[@]}"' in installer


@pytest.mark.parametrize("environment", ["dev", "prod"])
def test_deployment_workflow_installs_supervisor_processes(environment: str) -> None:
    workflow = (PROJECT_ROOT / ".github" / "workflows" / f"{environment}.yml").read_text()

    assert "DEPLOY_APP_USER: ${{ vars.APP_USER || 'nutrifood' }}" in workflow
    assert 'bash "$project_path/deploy/supervisor/install.sh"' in workflow
    assert '"$DEPLOY_APP_USER"' in workflow
    assert "app_user=$4" in workflow
