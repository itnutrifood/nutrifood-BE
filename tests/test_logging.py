import gzip
import logging
import os
import subprocess
import sys
from pathlib import Path

from backend.config.logging import (
    LOG_FORMAT,
    UTCFormatter,
    configure_logging,
    create_daily_file_handler,
)
from backend.config.settings import Settings


def test_daily_handler_rotates_and_compresses_the_previous_file(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        log_directory=tmp_path,
        log_component="rollover",
        log_retention_days=17,
    )
    handler = create_daily_file_handler(settings)
    handler.setFormatter(UTCFormatter(LOG_FORMAT))
    logger = logging.Logger("test.rollover", level=logging.INFO)
    logger.addHandler(handler)

    logger.info("before rollover")
    handler.doRollover()
    logger.info("after rollover")
    handler.close()

    archives = list(tmp_path.glob("rollover.log.*.gz"))
    assert handler.when == "MIDNIGHT"
    assert handler.utc is True
    assert handler.backupCount == 17
    assert len(archives) == 1
    assert "before rollover" in gzip.decompress(archives[0].read_bytes()).decode()
    assert "after rollover" in (tmp_path / "rollover.log").read_text(encoding="utf-8")


def test_logging_configuration_is_idempotent_and_captures_framework_logs(
    tmp_path: Path,
) -> None:
    script = """
import logging
import os
from pathlib import Path

from backend.config.logging import configure_logging
from backend.config.settings import Settings

settings = Settings(
    _env_file=None,
    log_directory=Path(os.environ["LOG_TEST_DIRECTORY"]),
    log_component="integration",
)
configure_logging(settings)
configure_logging(settings)
logging.getLogger().info("root-marker")
logging.getLogger("uvicorn.access").info("access-marker")
logging.getLogger("celery.task.example").info("task-marker")
logging.shutdown()
"""
    environment = os.environ.copy()
    environment["LOG_TEST_DIRECTORY"] = str(tmp_path)

    subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
    )

    contents = (tmp_path / "integration.log").read_text(encoding="utf-8")
    assert contents.count("root-marker") == 1
    assert contents.count("access-marker") == 1
    assert contents.count("task-marker") == 1
    assert "Z INFO pid=" in contents


def test_multiple_processes_can_write_to_the_same_component_file(tmp_path: Path) -> None:
    script = """
import logging
import os
from pathlib import Path

from backend.config.logging import configure_logging
from backend.config.settings import Settings

configure_logging(
    Settings(
        _env_file=None,
        log_directory=Path(os.environ["LOG_TEST_DIRECTORY"]),
        log_component="worker",
    )
)
for index in range(20):
    logging.getLogger("celery.task.concurrent").info(
        "concurrent-marker process=%s index=%d",
        os.environ["LOG_TEST_PROCESS"],
        index,
    )
logging.shutdown()
"""
    processes: list[subprocess.Popen[str]] = []
    for process_index in range(3):
        environment = os.environ.copy()
        environment["LOG_TEST_DIRECTORY"] = str(tmp_path)
        environment["LOG_TEST_PROCESS"] = str(process_index)
        processes.append(
            subprocess.Popen(
                [sys.executable, "-c", script],
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        )

    for process in processes:
        _stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, stderr

    contents = (tmp_path / "worker.log").read_text(encoding="utf-8")
    assert contents.count("concurrent-marker") == 60


def test_http_client_info_logs_are_suppressed_to_protect_query_secrets(
    tmp_path: Path,
) -> None:
    configure_logging(
        Settings(
            _env_file=None,
            log_directory=tmp_path,
            log_component="sensitive-http",
            log_level="DEBUG",
        )
    )

    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
