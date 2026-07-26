-- +goose Up
CREATE TABLE user_notification_preferences (
    user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    order_confirmations boolean NOT NULL DEFAULT true,
    delivery_updates boolean NOT NULL DEFAULT true,
    subscription_reminders boolean NOT NULL DEFAULT true,
    weekly_newsletter boolean NOT NULL DEFAULT true,
    promotional_offers boolean NOT NULL DEFAULT false,
    new_menu_items boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TRIGGER user_notification_preferences_set_updated_at
BEFORE UPDATE ON user_notification_preferences
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- +goose StatementBegin
CREATE FUNCTION create_default_user_notification_preferences()
RETURNS trigger AS $$
BEGIN
    INSERT INTO user_notification_preferences (user_id)
    VALUES (NEW.id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
-- +goose StatementEnd

CREATE TRIGGER users_create_default_notification_preferences
AFTER INSERT ON users
FOR EACH ROW
EXECUTE FUNCTION create_default_user_notification_preferences();

INSERT INTO user_notification_preferences (user_id)
SELECT id
FROM users
ON CONFLICT (user_id) DO NOTHING;

-- +goose Down
DROP TRIGGER IF EXISTS users_create_default_notification_preferences ON users;
DROP FUNCTION IF EXISTS create_default_user_notification_preferences();
DROP TRIGGER IF EXISTS user_notification_preferences_set_updated_at
ON user_notification_preferences;
DROP TABLE IF EXISTS user_notification_preferences;
