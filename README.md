# NutriFood Backend

FastAPI backend scaffold for NutriFood using Python 3.13, Poetry, PostgreSQL,
asyncpg, Docker Compose, and Goose migrations.

## Quick start

```sh
make init
make up
```

The API runs at `http://localhost:8000`.

Useful endpoints:

- `GET /health`
- `GET /api/v1/status`
- `GET /api/v2/status`
- `GET /api/v1/en-us/categories`
- `GET /api/v1/hy-am/products`
- `GET /api/v1/ru-ru/subscriptions`
- `GET /docs`

## API versions and locales

Versioned routers are assembled under `backend/config/urls_v1.py` and
`backend/config/urls_v2.py`, then mounted by `backend/config/urls.py` under
`/api/v1` and `/api/v2`. Add new v2 endpoints by importing and including their
routers in `backend/config/urls_v2.py`.

Public catalog reads are locale-scoped. Use lowercase locale codes in the URL:
`en-us`, `hy-am`, or `ru-ru`.

## Migrations

Create a migration:

```sh
make migration name=create_users
```

Run migrations:

```sh
make migrate
```

Show migration status:

```sh
make migrate-status
```

Seed admin and organic fitness catalog data:

```sh
make seed
```

Run seeders separately when needed:

```sh
make seed-admin
make seed-catalog
```

## Local development without Docker

```sh
poetry install
poetry run uvicorn backend.config.asgi:app --reload
```

For local non-Docker database access, set `DATABASE_URL` in `.env` to point to
your PostgreSQL host.

## User authentication

Public sign-up and sign-in use local user accounts with JWT access and refresh
tokens. User records are stored in the `users` table. Configure these values in
`.env`:

```sh
USER_TOKEN_SECRET=change-me-to-a-different-long-random-secret
USER_TOKEN_ALGORITHM=HS256
USER_ACCESS_TOKEN_EXPIRE_MINUTES=15
USER_REFRESH_TOKEN_EXPIRE_DAYS=30
```

Use `backend.apps.accounts.auth.RequireAuth` on protected route handlers to
require a valid user access token:

```py
@router.get("/me")
async def read_current_user(current_user: RequireAuth) -> dict[str, object]:
    return {"email": current_user.email}
```

Sign up at `POST /api/v1/accounts/auth/signup`:

```json
{
  "first_name": "Jane",
  "last_name": "Doe",
  "email": "jane@example.com",
  "password": "correct-password",
  "confirm_password": "correct-password"
}
```

Sign in at `POST /api/v1/accounts/auth/login`:

```json
{
  "email": "jane@example.com",
  "password": "correct-password"
}
```

Clients must send the returned access token as `Authorization: Bearer <token>`.
Refresh tokens can be exchanged at `POST /api/v1/accounts/auth/refresh`.

## Admin authentication

Admin endpoints use local username/password authentication with JWT access and
refresh tokens. Admin records are stored in the `admins` table. Configure these
seed values in `.env`:

```sh
ADMIN_USERNAME=admin@mail.com
ADMIN_PASSWORD=123456
ADMIN_TOKEN_SECRET=change-me-to-a-long-random-secret
```

After migrations run, seed or update the admin from `.env`:

```sh
make seed-admin
```

Sign in at `POST /api/v1/admin/auth/login`:

```json
{
  "username": "admin@mail.com",
  "password": "123456"
}
```

Use the returned access token as `Authorization: Bearer <token>` for admin
endpoints. Refresh tokens can be exchanged at `POST /api/v1/admin/auth/refresh`.
