-- +goose Up
ALTER TABLE orders
ADD COLUMN email_language varchar(5) NOT NULL DEFAULT 'EN-US'
CONSTRAINT orders_email_language_valid CHECK (email_language IN ('HY-AM', 'EN-US', 'RU-RU'));

-- +goose Down
ALTER TABLE orders
DROP COLUMN IF EXISTS email_language;
