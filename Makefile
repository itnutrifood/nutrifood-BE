DOCKER_COMPOSE ?= docker compose

.PHONY: help init build up down restart logs celery-logs celery-status ps shell db-shell migrate migrate-status migration seed-admin seed-catalog seed lint format test

help:
	@printf "NutriFood commands:\n"
	@printf "  make init             Generate a secure .env when missing\n"
	@printf "  make build            Build Docker images\n"
	@printf "  make up               Start the stack\n"
	@printf "  make down             Stop the stack\n"
	@printf "  make logs             Follow API logs\n"
	@printf "  make celery-logs      Follow worker, Beat, and Redis logs\n"
	@printf "  make celery-status    Ping running Celery workers\n"
	@printf "  make shell            Open a shell in the API container\n"
	@printf "  make db-shell         Open psql in the database container\n"
	@printf "  make migrate          Run Goose migrations\n"
	@printf "  make migrate-status   Show Goose migration status\n"
	@printf "  make migration name=x Create a SQL migration\n"
	@printf "  make seed-admin       Seed or update the admin user from .env\n"
	@printf "  make seed-catalog     Seed catalog content and testimonials\n"
	@printf "  make seed             Seed admin and catalog data\n"
	@printf "  make lint             Run Ruff and mypy\n"
	@printf "  make format           Format code with Ruff\n"
	@printf "  make test             Run tests\n"

init:
	@python3 scripts/init_env.py

build:
	$(DOCKER_COMPOSE) build

up: init
	$(DOCKER_COMPOSE) up --build

down:
	$(DOCKER_COMPOSE) down

restart: down up

logs:
	$(DOCKER_COMPOSE) logs -f api

celery-logs:
	$(DOCKER_COMPOSE) logs -f celery-worker celery-beat redis

celery-status:
	$(DOCKER_COMPOSE) exec celery-worker celery -A backend.config.celery_app:app inspect ping

ps:
	$(DOCKER_COMPOSE) ps

shell:
	$(DOCKER_COMPOSE) run --rm api sh

db-shell:
	$(DOCKER_COMPOSE) exec db psql -U "$${POSTGRES_USER:-nutrifood}" -d "$${POSTGRES_DB:-nutrifood}"

migrate: init
	$(DOCKER_COMPOSE) run --rm migrations up

migrate-status: init
	$(DOCKER_COMPOSE) run --rm migrations status

migration: init
	@test -n "$(name)" || (printf "Usage: make migration name=create_users\n" && exit 1)
	$(DOCKER_COMPOSE) run --rm migrations create "$(name)" sql

seed-admin: init
	$(DOCKER_COMPOSE) run --rm api python scripts/seed_admin.py

seed-catalog: init
	$(DOCKER_COMPOSE) run --rm api python scripts/seed_catalog.py

seed: seed-admin seed-catalog

lint:
	poetry run ruff check backend tests scripts
	poetry run mypy backend

format:
	poetry run ruff format backend tests scripts
	poetry run ruff check --fix backend tests scripts

test:
	poetry run pytest
