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

Products can be searched in the requested locale with the optional `search`
parameter:

```text
GET /api/v1/en-us/products?search=protein+bowl
GET /api/v1/hy-am/products?category_id=<category-uuid>&search=աղցան
```

Search covers localized title and description word prefixes, so a query such as
`protei` matches `protein`. Exact title matches rank first, followed by other
title matches and description-only matches. Search results use the response's
`next_cursor` value for subsequent pages, and that cursor must be reused with
the same locale, search text, and category filter.

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

## Celery and periodic tasks

The Compose stack builds one `nutrifood-backend` image and uses it for the API,
one Celery worker, and one Celery Beat scheduler. Redis provides queue storage.
Redis database 0 is the task broker, database 1 is the result backend, and database 2
stores public statistics. Redis is not published to the host, persists its data to the
`redis-data` volume with AOF, and rejects writes instead of evicting queued messages
when its configured memory limit is reached.

Periodic schedules are defined in `backend/config/celery_schedule.py`. Beat keeps
its last-run metadata in the `celery-beat-data` volume. Run exactly one Beat
instance; workers can be scaled independently. Successful task results are ignored,
failures are retained, and stored results expire after seven days. PostgreSQL remains
the durable source of truth for business state and task idempotency.

The initial periodic task removes FCM registrations that have not been seen for 30
days. It runs daily at 03:00 UTC. A second task refreshes the public statistics cache
daily at 00:00 UTC. Configure the cache and Celery runtime with:

```sh
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
STATISTICS_CACHE_URL=redis://redis:6379/2
CELERY_TIMEZONE=UTC
CELERY_RESULT_EXPIRES_SECONDS=604800
CELERY_WORKER_CONCURRENCY=2
FCM_REGISTRATION_STALE_DAYS=30
```

`GET /api/v1/statistics` returns `happy_customers` (order count), `healty_meals`
(product count), and `customer_rating` (the active-testimonial average, rounded to one
decimal place). If any cache key is absent or invalid, the API recomputes all three
values from PostgreSQL, repopulates Redis, and returns the fresh values. A Redis outage
does not prevent the database-backed response.

Task entry points live in the owning feature's `tasks.py` module and call the
domain service rather than containing SQL. A worker does not use FastAPI's lifespan
state, so each task that needs PostgreSQL creates and closes its own `asyncpg` pool.

Inspect the Celery services with:

```sh
make celery-logs
make celery-status
```

## Application logs

The API, Celery worker, and Celery Beat write to both the container console and
daily files. Compose persists the files in the `application-logs` volume at
`/var/log/nutrifood` and keeps separate `api.log`, `celery-worker.log`, and
`celery-beat.log` streams. Files rotate at UTC midnight by default, completed
days are gzip-compressed, and the oldest archives are deleted after the configured
retention count.

Configure logging in `.env` for native runs:

```sh
LOG_DIRECTORY=logs
LOG_COMPONENT=api
LOG_LEVEL=INFO
LOG_RETENTION_DAYS=30
LOG_ROTATION_UTC=true
```

Compose sets the directory and component per service. Read the persisted files
through any running application container:

```sh
docker compose exec api ls -lah /var/log/nutrifood
docker compose exec api tail -f /var/log/nutrifood/api.log
```

`docker compose down` preserves the log volume. `docker compose down -v` removes
it together with the other named volumes. Do not log credentials, authorization
headers, request bodies, or presigned asset URLs.

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

## Asset uploads with Cloudflare R2

Assets use global direct browser-to-R2 upload endpoints. Each request includes a `purpose`
that selects a server-owned policy for allowed media types, size, validation, and object
prefixes. The first policy is `product_image`: the API creates a short-lived,
content-type-bound presigned `PUT` URL, verifies the uploaded bytes and dimensions, then
moves the object from `pending/products/images/` to the public, immutable
`products/images/` prefix. Supported formats are JPEG, PNG, and WebP; images are limited
to 5 MiB and 4096 pixels per dimension.

Configure a bucket-scoped R2 Object Read & Write token and a public custom domain:

```sh
R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=<access-key-id>
R2_SECRET_ACCESS_KEY=<secret-access-key>
R2_BUCKET_NAME=nutrifood-assets
R2_PUBLIC_BASE_URL=https://assets.example.com
R2_UPLOAD_URL_EXPIRE_SECONDS=900
```

The S3 API endpoint signs uploads; the custom domain serves completed images. For
production, use a custom domain rather than an `r2.dev` development URL. Add this R2
CORS policy with the real admin frontend origin:

```json
[
  {
    "AllowedOrigins": ["http://localhost:3000", "https://admin.example.com"],
    "AllowedMethods": ["PUT"],
    "AllowedHeaders": ["Content-Type"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3600
  }
]
```

If the custom domain exposes the bucket directly, add a WAF rule that blocks requests
whose path starts with `/pending/`. Pending keys contain random UUIDs, but blocking the
prefix ensures incomplete uploads cannot be served from the public domain.

Configure an R2 lifecycle rule to expire objects under `pending/products/images/` after
one day. Successful completions remove their pending object immediately; the rule cleans
up uploads that clients abandon.

The admin client upload flow is:

1. `POST /api/v1/admin/assets/uploads` with the browser file's purpose, exact
   `content_type`, and `size_bytes`:

   ```json
   {"purpose": "product_image", "content_type": "image/png", "size_bytes": 204800}
   ```

2. `PUT` the raw file to `upload_url`, sending every header returned in `headers`.
3. `POST /api/v1/admin/assets/uploads/{upload_id}/complete` with the same `purpose`,
   `content_type`, and `size_bytes`.
4. For a product image, map the completed asset to the product contract:

   ```js
   const productImage = {
     url: asset.url,
     width: asset.metadata.width,
     height: asset.metadata.height,
     size_bytes: asset.size_bytes,
   }
   ```

Product image URLs are owned by one product and must not be reused. When an admin replaces a
product's `images` array, managed R2 objects missing from the new array are deleted. Deleting
a product also deletes all of its managed `products/images/` objects. Cleanup ignores URLs
outside the configured R2 public origin, product image prefix, and generated UUID filename
format.

Presigned URLs are bearer credentials until they expire. Do not log or persist them.
See [ASSET_UPLOAD_PLAN.md](ASSET_UPLOAD_PLAN.md) for the design rationale and expansion
roadmap.

Authenticated users can manage their favorite products with locale-scoped endpoints:

- `GET /api/v1/{locale}/favorites`
- `PUT /api/v1/{locale}/favorites` with `{"product_ids": ["<product-uuid>"]}`
- `PUT /api/v1/{locale}/favorites/{product_id}`
- `DELETE /api/v1/{locale}/favorites/{product_id}`

## Notification preferences

Each user has email notification preferences for order confirmations, delivery updates,
subscription reminders, the weekly newsletter, promotional offers, and new menu items.
Read the current settings with:

```http
GET /api/v1/notifications/preferences
Authorization: Bearer <firebase-id-token>
```

Update one or more settings without replacing the others:

```http
PATCH /api/v1/notifications/preferences
Authorization: Bearer <firebase-id-token>
Content-Type: application/json

{"weekly_newsletter": false, "promotional_offers": true}
```

Order confirmations, delivery updates, subscription reminders, the weekly newsletter,
and new menu items default to enabled. Promotional offers default to disabled.

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

## Checkout and orders

Authenticated users place every current cart item in one request. The checkout uses the
saved delivery address owned by the user and supports cash or a portable card terminal at
delivery:

```http
POST /api/v1/checkout/orders
Authorization: Bearer <firebase-id-token>
Idempotency-Key: <new-uuid-v4>
Content-Type: application/json

{
  "address_id": "<address-uuid>",
  "payment_method": "cash_on_delivery",
  "contact_phone": "+37499123456",
  "delivery_notes": "Call on arrival"
}
```

Use `pos` for card-at-delivery. Online payment is intentionally not accepted until a
merchant integration is available. `Idempotency-Key` is required so a client can safely
retry after a timeout; reusing it with changed checkout fields returns `409`.
Successful orders receive a customer-facing number such as `NFUX6Q8N6LD`; UUIDs remain
the internal API identifiers used in resource URLs.

The server calculates prices from the catalog, creates order and line-item snapshots, and
clears the purchased cart rows in one database transaction. Address edits, product edits,
and later product deletion therefore do not rewrite order history. Configure the catalog
and order currency with `CATALOG_CURRENCY` (an uppercase ISO 4217 code, default `USD`). The
current product model has no inventory field, so this flow does not claim or decrement
stock.

Users can read their own order history and details:

- `GET /api/v1/orders`
- `GET /api/v1/orders/{order_id}`

Admins can see orders across all users, optionally filtered by `status` and
`payment_method`:

- `GET /api/v1/admin/orders`
- `GET /api/v1/admin/orders/{order_id}`

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
