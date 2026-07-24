-- +goose Up
ALTER TABLE users
ADD COLUMN firebase_uid varchar(128);

ALTER TABLE users
ALTER COLUMN first_name DROP NOT NULL,
ALTER COLUMN last_name DROP NOT NULL,
ALTER COLUMN password_hash DROP NOT NULL;

ALTER TABLE users
DROP CONSTRAINT users_first_name_not_blank,
DROP CONSTRAINT users_last_name_not_blank;

CREATE UNIQUE INDEX users_firebase_uid_idx
ON users(firebase_uid)
WHERE firebase_uid IS NOT NULL;

CREATE TABLE user_fcm_registrations (
    registration_hash bytea PRIMARY KEY,
    registration_id text NOT NULL,
    registration_type varchar(5) NOT NULL,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform varchar(10) NOT NULL,
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT user_fcm_registrations_hash_length
        CHECK (octet_length(registration_hash) = 32),
    CONSTRAINT user_fcm_registrations_id_length
        CHECK (length(registration_id) BETWEEN 20 AND 4096),
    CONSTRAINT user_fcm_registrations_type
        CHECK (registration_type IN ('fid', 'token')),
    CONSTRAINT user_fcm_registrations_platform
        CHECK (platform IN ('android', 'ios', 'web'))
);

CREATE INDEX user_fcm_registrations_user_idx
ON user_fcm_registrations(user_id);

CREATE INDEX user_fcm_registrations_last_seen_idx
ON user_fcm_registrations(last_seen_at);

CREATE TRIGGER user_fcm_registrations_set_updated_at
BEFORE UPDATE ON user_fcm_registrations
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- +goose Down
DROP TRIGGER IF EXISTS user_fcm_registrations_set_updated_at ON user_fcm_registrations;
DROP TABLE IF EXISTS user_fcm_registrations;
DROP INDEX IF EXISTS users_firebase_uid_idx;

ALTER TABLE users
ADD CONSTRAINT users_first_name_not_blank CHECK (btrim(first_name) <> ''),
ADD CONSTRAINT users_last_name_not_blank CHECK (btrim(last_name) <> '');

UPDATE users
SET first_name = 'User'
WHERE first_name IS NULL;

UPDATE users
SET last_name = 'User'
WHERE last_name IS NULL;

UPDATE users
SET password_hash = 'firebase-auth-managed'
WHERE password_hash IS NULL;

ALTER TABLE users
ALTER COLUMN first_name SET NOT NULL,
ALTER COLUMN last_name SET NOT NULL,
ALTER COLUMN password_hash SET NOT NULL;

ALTER TABLE users
DROP COLUMN firebase_uid;
