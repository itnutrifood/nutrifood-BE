-- +goose Up
CREATE TYPE user_subscription_status AS ENUM ('active', 'cancelled');
CREATE TYPE subscription_activation_source AS ENUM ('test_bypass', 'payment');

CREATE TABLE user_subscriptions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    subscription_plan_id uuid NOT NULL REFERENCES subscription_plans(id) ON DELETE RESTRICT,
    status user_subscription_status NOT NULL DEFAULT 'active',
    activation_source subscription_activation_source NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    cancelled_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT user_subscriptions_status_timestamps_consistent CHECK (
        (status = 'active' AND cancelled_at IS NULL)
        OR (status = 'cancelled' AND cancelled_at IS NOT NULL)
    ),
    CONSTRAINT user_subscriptions_cancellation_after_start CHECK (
        cancelled_at IS NULL OR cancelled_at >= started_at
    )
);

CREATE UNIQUE INDEX user_subscriptions_one_active_per_user_idx
ON user_subscriptions(user_id)
WHERE status = 'active';

CREATE INDEX user_subscriptions_user_history_idx
ON user_subscriptions(user_id, created_at DESC, id DESC);

CREATE INDEX user_subscriptions_active_plan_idx
ON user_subscriptions(subscription_plan_id)
WHERE status = 'active';

CREATE TRIGGER user_subscriptions_set_updated_at
BEFORE UPDATE ON user_subscriptions
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- +goose Down
DROP TRIGGER IF EXISTS user_subscriptions_set_updated_at ON user_subscriptions;
DROP TABLE IF EXISTS user_subscriptions;
DROP TYPE IF EXISTS subscription_activation_source;
DROP TYPE IF EXISTS user_subscription_status;
