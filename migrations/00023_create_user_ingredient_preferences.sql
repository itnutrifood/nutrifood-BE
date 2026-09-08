-- +goose Up
CREATE TYPE ingredient_preference AS ENUM ('whitelisted', 'blacklisted');

CREATE TABLE user_ingredient_preferences (
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ingredient_id uuid NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE,
    preference ingredient_preference NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, ingredient_id)
);

CREATE INDEX user_ingredient_preferences_ingredient_idx
ON user_ingredient_preferences(ingredient_id, user_id);

CREATE TRIGGER user_ingredient_preferences_set_updated_at
BEFORE UPDATE ON user_ingredient_preferences
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- +goose Down
DROP TRIGGER IF EXISTS user_ingredient_preferences_set_updated_at
ON user_ingredient_preferences;
DROP TABLE IF EXISTS user_ingredient_preferences;
DROP TYPE IF EXISTS ingredient_preference;
