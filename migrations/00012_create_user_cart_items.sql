-- +goose Up
CREATE TABLE user_cart_items (
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    product_id uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    quantity integer NOT NULL CHECK (quantity BETWEEN 1 AND 99),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, product_id)
);

CREATE INDEX user_cart_items_user_order_idx
ON user_cart_items(user_id, created_at DESC, product_id DESC);

CREATE TRIGGER user_cart_items_set_updated_at
BEFORE UPDATE ON user_cart_items
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- +goose Down
DROP TRIGGER IF EXISTS user_cart_items_set_updated_at ON user_cart_items;
DROP TABLE IF EXISTS user_cart_items;
