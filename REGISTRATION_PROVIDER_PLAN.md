# Registration Provider Implementation Plan

## Goal

Persist how a user originally registered with NutriFood while keeping that value
separate from the provider used for later sign-ins.

`registration_provider` will be immutable account metadata. The existing
request-scoped `sign_in_provider` will continue to describe the provider used for
the current Firebase authentication event.

## Data Contract

- Add `registration_provider` to the PostgreSQL `users` table.
- Store the verified Firebase `firebase.sign_in_provider` claim when a new local
  user is provisioned.
- Never accept the registration provider from a client request body or header.
- Never overwrite it during later sign-ins, profile synchronization, or account
  linking.
- Return `registration_provider` in user responses from:
  - `POST /api/v1/accounts/auth/session`
  - `GET /api/v1/accounts/me`
- Keep the existing request-scoped `sign_in_provider` behavior unchanged.

Initially expected provider values are:

- `password`
- `google.com`
- `unknown` only for historical rows whose original provider cannot be determined

The database column should remain a non-blank string rather than a PostgreSQL enum,
so provider-domain changes do not require replacing a database enum type.

## Database Migration

Create `00014_add_user_registration_provider.sql`:

1. Add a nullable `registration_provider varchar(50)` column.
2. Backfill existing users:
   - Rows with a non-null `password_hash` become `password`, because they originated
     from the previous local email/password registration system.
   - Rows with a null `password_hash` become `unknown`, because the original
     Firebase provider was not persisted and must not be guessed.
3. Add a non-blank check constraint.
4. Change the column to `NOT NULL`.
5. Do not leave a database default; all newly provisioned users must explicitly
   supply the provider from a verified Firebase identity.
6. The down migration removes the constraint and column.

The migration must not contact Firebase or infer a historical provider from the
user's most recent login.

## Accounts Domain Changes

### Schemas

Update `backend/apps/accounts/schemas.py`:

- Add `registration_provider: str` to `UserRead`.
- Allow `UserRecord` and `UserIdentity` to inherit the field through `UserRead`.
- This automatically adds the field to `/auth/session` and `/accounts/me`
  responses without duplicating response-building logic.

### Repository

Update `backend/apps/accounts/repository.py`:

- Add `registration_provider` to `USER_COLUMNS`.
- Map it in `user_from_record`.
- Add it to the `INSERT INTO users` statement in `create_user`.
- Pass `identity.sign_in_provider` only when inserting a new local user.
- Do not include it in `sync_user_profile`.
- Do not overwrite it in `link_legacy_user`.

Keeping all SQL in the repository preserves the current router/service/repository
architecture.

### Service

Update `backend/apps/accounts/service.py`:

- Continue deriving `sign_in_provider` only from verified Firebase claims.
- Use that verified value as the registration provider only on the new-user
  provisioning path.
- Include the stored `user.registration_provider` when constructing
  `UserIdentity`.
- Do not replace the stored value when the current sign-in provider differs.

Example:

```json
{
  "registration_provider": "password"
}
```

If that user later authenticates through another linked provider,
`registration_provider` remains `password`.

## API and Security Behavior

- No new public endpoint is required.
- `/auth/session` remains the single Firebase authentication handshake.
- Clients cannot select or modify `registration_provider`.
- Provider allowlisting remains enforced before local user provisioning.
- Disabled users and conflicting Firebase/email links retain their existing
  behavior.
- Adding the response field is backward-compatible for JSON consumers that ignore
  unknown fields.

## Test Plan

Update account fixtures and fake database records to include
`registration_provider`, then add coverage for:

1. A new password-authenticated Firebase user is stored with `password`.
2. A new Google-authenticated Firebase user is stored with `google.com`.
3. A user originally registered with password keeps `password` after a later
   Google sign-in.
4. Profile synchronization never updates `registration_provider`.
5. Legacy account linking preserves the migration-backfilled provider.
6. `/auth/session` returns `registration_provider`.
7. `/accounts/me` returns `registration_provider`.
8. Missing or disallowed Firebase provider claims remain rejected before user
   creation.
9. Concurrent first-session provisioning still returns the persisted provider from
   the winning database row.
10. Ruff, strict mypy, the complete pytest suite, and `git diff --check` pass.
11. Goose migration up and down both succeed against an isolated PostgreSQL
    database.

## Rollout Plan

1. Apply migration `00014` before starting application code that selects the new
   column. The existing Compose startup order already runs migrations before the
   API.
2. Deploy the application changes.
3. Verify new password and Google registrations in a non-production environment.
4. Check the distribution of `registration_provider`, especially the count of
   `unknown` historical rows.
5. Do not manually rewrite `unknown` values unless a trustworthy historical source
   exists.

## Acceptance Criteria

- Every newly provisioned local user has a non-blank, verified
  `registration_provider`.
- Registration provider cannot be supplied or changed by the client.
- Later sign-ins do not alter the original registration provider.
- Existing users migrate without fabricating unavailable provider history.
- Session and current-user responses expose the stored registration provider.
- SQL remains confined to the accounts repository.

## Out of Scope

- Login-event history or authentication audit tables.
- Returning every provider linked to a Firebase account.
- Allowing users or administrators to edit the registration provider.
- Changes to the current provider allowlist.
