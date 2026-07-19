-- +goose Up
CREATE TABLE user_favorite_products (
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    product_id uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, product_id)
);

CREATE INDEX user_favorite_products_user_order_idx
ON user_favorite_products(user_id, created_at DESC, product_id DESC);

-- +goose Down
DROP TABLE IF EXISTS user_favorite_products;
