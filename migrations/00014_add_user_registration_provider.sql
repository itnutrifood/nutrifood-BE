-- +goose Up
ALTER TABLE users
ADD COLUMN registration_provider varchar(50);

UPDATE users
SET registration_provider = CASE
    WHEN password_hash IS NOT NULL THEN 'password'
    ELSE 'unknown'
END;

ALTER TABLE users
ALTER COLUMN registration_provider SET NOT NULL;

ALTER TABLE users
ADD CONSTRAINT users_registration_provider_not_blank
CHECK (btrim(registration_provider) <> '');

-- +goose Down
ALTER TABLE users
DROP CONSTRAINT IF EXISTS users_registration_provider_not_blank;

ALTER TABLE users
DROP COLUMN IF EXISTS registration_provider;
