FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential libpq-dev curl \
    && pip install --no-cache-dir poetry \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml poetry.lock README.md ./
RUN poetry install --only main --no-root --no-ansi

RUN groupadd --gid 10001 app \
    && useradd --no-create-home --uid 10001 --gid app app \
    && install -d --owner=app --group=app /var/lib/celery /var/log/nutrifood

COPY --chown=app:app backend ./backend

USER app

EXPOSE 8000

CMD ["uvicorn", "backend.config.asgi:app", "--host", "0.0.0.0", "--port", "8000"]
