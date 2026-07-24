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
- `GET /api/v1/testimonials`
- `GET /docs`

## API versions and locales

Versioned routers are assembled under `backend/config/urls_v1.py` and
`backend/config/urls_v2.py`, then mounted by `backend/config/urls.py` under
`/api/v1` and `/api/v2`. Add new v2 endpoints by importing and including their
routers in `backend/config/urls_v2.py`.

## Application boundaries

Feature modules keep HTTP, application, and persistence concerns separate:

- `schemas.py` contains Pydantic request and response contracts.
- `models.py` contains internal records or dataclasses when a feature needs them.
- `exceptions.py` contains domain and application exceptions.
- `repository.py` contains SQL, `asyncpg` calls, and database-record mapping.
- `service.py` and `admin_service.py` contain business and orchestration logic.
- `routers.py` and `admin_routers.py` contain only FastAPI route declarations,
  dependencies, and service calls.

Admin catalog routes are owned by their feature modules and assembled by
`backend/apps/admin/routers.py`. The small modules under `backend/apps/admin/`
that share feature names are compatibility exports and contain no business or
persistence logic.

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

Seed admin, organic fitness catalog data, and five testimonials:

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

User authentication is managed by Firebase Authentication. Enable these sign-in
providers in the Firebase console:

- Email/Password
- Google

Also enable email-enumeration protection for password authentication and configure
the authorized domains and OAuth consent screen for each deployed frontend.

Client applications sign up or sign in with the Firebase SDK. Passwords and Google
OAuth credentials must not be sent to this API. After authentication, retrieve the
Firebase ID token and send it over HTTPS:

```http
Authorization: Bearer <firebase-id-token>
```

The API verifies the token with the Firebase Admin SDK, including account
revocation/disablement checks. By default it accepts only the `password` and
`google.com` providers and requires `email_verified=true`. A local `users` row is
created on the first authenticated request; existing local accounts with the same
verified email are linked automatically. The local row stores an immutable
`registration_provider` derived from the verified Firebase token. Later sign-ins
through another linked provider do not change the original value.

Configure the Admin SDK in `.env`:

```sh
# Prefer Application Default Credentials when running on Google Cloud. Otherwise,
# mount this service-account JSON file as a secret; never commit it.
FIREBASE_CREDENTIALS_PATH=firebase.json
FIREBASE_PROJECT_ID=nutrifood-dev
FIREBASE_REQUIRE_VERIFIED_EMAIL=true
FIREBASE_ALLOWED_SIGN_IN_PROVIDERS=["password","google.com"]
```

Call `POST /api/v1/accounts/auth/session` after client sign-in to verify the token
and synchronize the local account. `GET /api/v1/accounts/me` and all other
authenticated routes accept the same Bearer token. Firebase client SDKs refresh ID
tokens automatically; this API does not issue access or refresh tokens. Both
`/auth/session` and `/accounts/me` return the stored `registration_provider`.

Use `backend.apps.accounts.dependencies.RequireAuth` on protected route handlers to
require a valid Firebase identity:

```py
@router.get("/me")
async def read_current_user(current_user: RequireAuth) -> dict[str, object]:
    return {"email": current_user.email}
```

Authorization roles come from a Firebase custom claim named `roles`. Set custom
claims only from a privileged server environment, then enforce all required roles:

```py
from typing import Annotated

from fastapi import Depends

from backend.apps.accounts.dependencies import RoleChecker
from backend.apps.accounts.schemas import UserIdentity

Subscriber = Annotated[UserIdentity, Depends(RoleChecker("subscriber"))]
```

Authenticated users can manage their favorite products with locale-scoped endpoints:

- `GET /api/v1/{locale}/favorites`
- `PUT /api/v1/{locale}/favorites` with `{"product_ids": ["<product-uuid>"]}`
- `PUT /api/v1/{locale}/favorites/{product_id}`
- `DELETE /api/v1/{locale}/favorites/{product_id}`

## FCM registrations

Firebase is transitioning from legacy registration tokens to Firebase Installation
IDs (FIDs). New clients should upload their FID on app startup and whenever the FCM
SDK invokes its registration callback:

```http
PUT /api/v1/notifications/fcm-registrations
Authorization: Bearer <firebase-id-token>
Content-Type: application/json

{"fid": "<firebase-installation-id>", "platform": "android"}
```

Supported platforms are `android`, `ios`, and `web`. The operation is idempotent,
reassigns a registration when a device changes accounts, and refreshes a
server-side `last_seen_at` timestamp. Registration identifiers are never returned
by the API or placed in URLs. On sign-out, unregister it with:

```http
DELETE /api/v1/notifications/fcm-registrations
Authorization: Bearer <firebase-id-token>
Content-Type: application/json

{"fid": "<firebase-installation-id>"}
```

Legacy clients can use the deprecated `PUT` and `DELETE`
`/api/v1/notifications/fcm-tokens` endpoints with
`{"token": "<fcm-registration-token>", ...}`.

Notification sending code should remove registrations when FCM reports them as
unregistered and periodically prune stale `last_seen_at` rows. A one-month
staleness threshold is a reasonable default and can be tuned for the product.

In `local`, `development`, `test`, and other non-production environments, an
authenticated user can send a fixed test notification to their freshest registered
installation:

```http
POST /api/v1/notifications/test
Authorization: Bearer <firebase-id-token>
```

The test endpoint returns `404` when `ENVIRONMENT` is `prod` or `production`, and
also returns `404` when the current user has no FCM registration.

## Cart

Guests can keep cart items locally and sync them after authentication, in the same way
as offline favorites. Cart quantities are set rather than incremented, so retrying a
request is safe:

- `GET /api/v1/{locale}/cart`
- `PUT /api/v1/{locale}/cart/{product_id}` with `{"quantity": 2}`
- `PUT /api/v1/{locale}/cart` with
  `{"items": [{"product_id": "<product-uuid>", "quantity": 2}]}`
- `DELETE /api/v1/{locale}/cart/{product_id}`
- `DELETE /api/v1/{locale}/cart`

The bulk `PUT` is intended for syncing a locally stored guest cart after login. It
upserts all supplied quantities atomically and leaves other existing cart items in
place. Server-side cart endpoints require a Firebase ID token.

Testimonials are managed through `/api/v1/admin/testimonials`. Active testimonials are
available publicly from `GET /api/v1/testimonials` and `GET /api/v1/testimonials/{id}`.

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
