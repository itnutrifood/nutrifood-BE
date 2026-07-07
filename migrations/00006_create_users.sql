-- +goose Up
CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    first_name varchar(150) NOT NULL,
    last_name varchar(150) NOT NULL,
    email varchar(320) NOT NULL UNIQUE,
    password_hash text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    token_version integer NOT NULL DEFAULT 1 CHECK (token_version > 0),
    last_login_at timestamptz,
    last_refresh_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT users_first_name_not_blank CHECK (btrim(first_name) <> ''),
    CONSTRAINT users_last_name_not_blank CHECK (btrim(last_name) <> ''),
    CONSTRAINT users_email_not_blank CHECK (btrim(email) <> ''),
    CONSTRAINT users_email_lowercase CHECK (email = lower(email))
);

CREATE INDEX users_active_email_idx ON users(email) WHERE is_active;

CREATE TRIGGER users_set_updated_at
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- +goose Down
DROP TRIGGER IF EXISTS users_set_updated_at ON users;
DROP INDEX IF EXISTS users_active_email_idx;
DROP TABLE IF EXISTS users;
