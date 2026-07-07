FROM python:3.14-slim

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

COPY pyproject.toml README.md ./
RUN poetry install --only main --no-root --no-ansi

COPY backend ./backend

EXPOSE 8000

CMD ["uvicorn", "backend.config.asgi:app", "--host", "0.0.0.0", "--port", "8000"]
