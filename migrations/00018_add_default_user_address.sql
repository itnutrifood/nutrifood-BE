-- +goose Up
ALTER TABLE user_addresses
ADD COLUMN is_default boolean NOT NULL DEFAULT FALSE;

CREATE UNIQUE INDEX user_addresses_one_default_per_user_idx
ON user_addresses(user_id)
WHERE is_default;

-- +goose Down
DROP INDEX IF EXISTS user_addresses_one_default_per_user_idx;

ALTER TABLE user_addresses
DROP COLUMN IF EXISTS is_default;
