-- +goose Up
-- +goose StatementBegin
CREATE FUNCTION generate_order_number()
RETURNS varchar(11) AS $$
DECLARE
    alphabet constant text := '23456789ABCDEFGHJKLMNPQRSTUVWXYZ';
    random_bytes bytea := decode(replace(gen_random_uuid()::text, '-', ''), 'hex');
    generated_number text := 'NF';
    byte_index integer;
BEGIN
    FOR byte_index IN 0..8 LOOP
        generated_number := generated_number || substr(
            alphabet,
            (get_byte(random_bytes, byte_index) % 32) + 1,
            1
        );
    END LOOP;

    RETURN generated_number::varchar(11);
END;
$$ LANGUAGE plpgsql VOLATILE;
-- +goose StatementEnd

CREATE TABLE orders (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    order_number varchar(11) NOT NULL UNIQUE DEFAULT generate_order_number(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    status varchar(32) NOT NULL DEFAULT 'pending',
    payment_method varchar(32) NOT NULL,
    payment_status varchar(32) NOT NULL DEFAULT 'unpaid',
    subtotal numeric(14, 2) NOT NULL,
    delivery_fee numeric(14, 2) NOT NULL DEFAULT 0,
    total numeric(14, 2) GENERATED ALWAYS AS (subtotal + delivery_fee) STORED,
    currency varchar(3) NOT NULL DEFAULT 'USD',
    customer_first_name varchar(150),
    customer_last_name varchar(150),
    customer_email varchar(320) NOT NULL,
    contact_phone varchar(16) NOT NULL,
    delivery_address_id uuid REFERENCES user_addresses(id) ON DELETE SET NULL,
    delivery_country varchar(64) NOT NULL,
    delivery_region varchar(64) NOT NULL,
    delivery_city varchar(150) NOT NULL,
    delivery_street varchar(255) NOT NULL,
    delivery_building_number varchar(50) NOT NULL,
    delivery_entrance varchar(50),
    delivery_floor varchar(50),
    delivery_notes varchar(500),
    idempotency_key varchar(255) NOT NULL,
    request_fingerprint char(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT orders_status_valid CHECK (
        status IN (
            'pending',
            'confirmed',
            'preparing',
            'ready_for_delivery',
            'out_for_delivery',
            'delivered',
            'cancelled'
        )
    ),
    CONSTRAINT orders_payment_method_valid CHECK (
        payment_method IN ('cash_on_delivery', 'pos')
    ),
    CONSTRAINT orders_payment_status_valid CHECK (
        payment_status IN ('unpaid', 'paid', 'failed', 'refunded')
    ),
    CONSTRAINT orders_subtotal_non_negative CHECK (subtotal >= 0),
    CONSTRAINT orders_delivery_fee_non_negative CHECK (delivery_fee >= 0),
    CONSTRAINT orders_currency_iso_format CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT orders_order_number_format CHECK (
        order_number ~ '^NF[23456789A-HJ-NP-Z]{9}$'
    ),
    CONSTRAINT orders_customer_email_not_blank CHECK (btrim(customer_email) <> ''),
    CONSTRAINT orders_contact_phone_e164 CHECK (
        contact_phone ~ '^\+[1-9][0-9]{7,14}$'
    ),
    CONSTRAINT orders_delivery_country_not_blank CHECK (btrim(delivery_country) <> ''),
    CONSTRAINT orders_delivery_region_not_blank CHECK (btrim(delivery_region) <> ''),
    CONSTRAINT orders_delivery_city_not_blank CHECK (btrim(delivery_city) <> ''),
    CONSTRAINT orders_delivery_street_not_blank CHECK (btrim(delivery_street) <> ''),
    CONSTRAINT orders_delivery_building_not_blank CHECK (
        btrim(delivery_building_number) <> ''
    ),
    CONSTRAINT orders_delivery_notes_not_blank CHECK (
        delivery_notes IS NULL OR btrim(delivery_notes) <> ''
    ),
    CONSTRAINT orders_idempotency_key_not_blank CHECK (btrim(idempotency_key) <> ''),
    CONSTRAINT orders_request_fingerprint_sha256 CHECK (
        request_fingerprint ~ '^[0-9a-f]{64}$'
    ),
    UNIQUE (user_id, idempotency_key)
);

CREATE TABLE order_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id uuid NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id uuid REFERENCES products(id) ON DELETE SET NULL,
    product_slug text,
    product_title jsonb NOT NULL,
    unit_price numeric(10, 2) NOT NULL,
    quantity integer NOT NULL,
    position integer NOT NULL,
    line_total numeric(14, 2) GENERATED ALWAYS AS (unit_price * quantity) STORED,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT order_items_title_is_object CHECK (jsonb_typeof(product_title) = 'object'),
    CONSTRAINT order_items_title_has_supported_keys CHECK (
        product_title ? 'HY-AM'
        AND product_title ? 'EN-US'
        AND product_title ? 'RU-RU'
        AND product_title - 'HY-AM' - 'EN-US' - 'RU-RU' = '{}'::jsonb
    ),
    CONSTRAINT order_items_title_values_not_blank CHECK (
        jsonb_typeof(product_title -> 'HY-AM') = 'string'
        AND btrim(product_title ->> 'HY-AM') <> ''
        AND jsonb_typeof(product_title -> 'EN-US') = 'string'
        AND btrim(product_title ->> 'EN-US') <> ''
        AND jsonb_typeof(product_title -> 'RU-RU') = 'string'
        AND btrim(product_title ->> 'RU-RU') <> ''
    ),
    CONSTRAINT order_items_unit_price_non_negative CHECK (unit_price >= 0),
    CONSTRAINT order_items_quantity_valid CHECK (quantity BETWEEN 1 AND 99),
    CONSTRAINT order_items_position_positive CHECK (position > 0),
    UNIQUE (order_id, product_id),
    UNIQUE (order_id, position)
);

CREATE INDEX orders_user_created_idx ON orders(user_id, created_at DESC, id DESC);
CREATE INDEX orders_admin_created_idx ON orders(created_at DESC, id DESC);
CREATE INDEX orders_admin_status_created_idx ON orders(status, created_at DESC, id DESC);
CREATE INDEX orders_admin_payment_created_idx
ON orders(payment_method, created_at DESC, id DESC);
CREATE INDEX order_items_order_idx ON order_items(order_id, position);

CREATE TRIGGER orders_set_updated_at
BEFORE UPDATE ON orders
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- +goose Down
DROP TRIGGER IF EXISTS orders_set_updated_at ON orders;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP FUNCTION IF EXISTS generate_order_number();
