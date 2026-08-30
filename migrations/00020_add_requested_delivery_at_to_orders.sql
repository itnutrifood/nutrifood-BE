-- +goose Up
ALTER TABLE orders
ADD COLUMN requested_delivery_at timestamptz;

-- +goose Down
ALTER TABLE orders
DROP COLUMN IF EXISTS requested_delivery_at;
