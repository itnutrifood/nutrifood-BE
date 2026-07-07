# Repository Guidelines

## Project Structure & Module Organization

NutriFood is a FastAPI backend using Python 3.13, Poetry, PostgreSQL, Docker Compose, and Goose migrations. Application code lives in `backend/`. `backend/config/` contains ASGI startup, settings, database setup, and URL aggregation. Feature modules live under `backend/apps/<domain>/`, usually with a `routers.py` file, for example `backend/apps/accounts/routers.py`. Tests live in `tests/` and currently cover health and Auth0 behavior. SQL migrations live in `migrations/`. Runtime configuration is copied from `.env.example` to `.env`.

## Build, Test, and Development Commands

- `make init`: create `.env` from `.env.example` when missing.
- `make up`: build and start the Docker Compose stack.
- `make down`: stop the stack.
- `make logs`: follow API container logs.
- `make migrate`: run Goose database migrations.
- `make migration name=create_users`: create a new SQL migration.
- `make lint`: run Ruff checks and strict mypy on `backend/`.
- `make format`: format and auto-fix with Ruff.
- `make test`: run the pytest suite.
- `poetry run uvicorn backend.config.asgi:app --reload`: run the API locally without Docker.

## Coding Style & Naming Conventions

Use Python 3.13 syntax and type annotations. Ruff is configured for 100-character lines and rules `E`, `F`, `I`, `B`, `UP`, and `ASYNC`; run `make format` before submitting changes. Mypy is strict and requires typed function definitions in `backend/`. Keep app modules domain-oriented under `backend/apps/`, name routers `router`, and expose route handlers with clear async function names such as `read_current_user`.

## Testing Guidelines

Tests use `pytest`, `pytest-asyncio`, and FastAPI `TestClient`. Add tests under `tests/` with filenames matching `test_*.py` and functions named `test_*`. Prefer dependency overrides and monkeypatching for external services such as Auth0 or database pools. Run `make test` for the full suite and `poetry run pytest tests/test_auth.py` for a focused run.

## Commit & Pull Request Guidelines

This checkout does not include Git history, so no repository-specific commit convention is visible. Use concise, imperative commit subjects such as `Add account status route` or `Fix Auth0 token handling`. Pull requests should include a short summary, test results (`make lint`, `make test`), migration notes when `migrations/` changes, and API examples or screenshots of `/docs` when route behavior changes.

## Security & Configuration Tips

Do not commit secrets. Keep local overrides in `.env` and update `.env.example` when adding required settings. Auth0 settings are read through `backend/config/settings.py`; ensure protected routes use `RequireAuth` from `backend.apps.accounts.auth`.
