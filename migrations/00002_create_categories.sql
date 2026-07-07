-- +goose Up
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE language_code AS ENUM ('HY-AM', 'EN-US', 'RU-RU');
CREATE TYPE category_status AS ENUM ('active', 'inactive');

CREATE TABLE categories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id uuid REFERENCES categories(id) ON DELETE RESTRICT,
    slug text NOT NULL UNIQUE,
    name jsonb NOT NULL,
    description jsonb NOT NULL DEFAULT '{}'::jsonb,
    status category_status NOT NULL DEFAULT 'active',
    sort_order integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT categories_parent_not_self CHECK (parent_id IS NULL OR parent_id <> id),
    CONSTRAINT categories_slug_not_blank CHECK (btrim(slug) <> ''),
    CONSTRAINT categories_sort_order_non_negative CHECK (sort_order >= 0),
    CONSTRAINT categories_name_is_object CHECK (jsonb_typeof(name) = 'object'),
    CONSTRAINT categories_name_has_supported_keys CHECK (
        name ? 'HY-AM'
        AND name ? 'EN-US'
        AND name ? 'RU-RU'
        AND name - 'HY-AM' - 'EN-US' - 'RU-RU' = '{}'::jsonb
    ),
    CONSTRAINT categories_name_values_not_blank CHECK (
        jsonb_typeof(name -> 'HY-AM') = 'string'
        AND btrim(name ->> 'HY-AM') <> ''
        AND jsonb_typeof(name -> 'EN-US') = 'string'
        AND btrim(name ->> 'EN-US') <> ''
        AND jsonb_typeof(name -> 'RU-RU') = 'string'
        AND btrim(name ->> 'RU-RU') <> ''
    ),
    CONSTRAINT categories_description_is_object CHECK (jsonb_typeof(description) = 'object'),
    CONSTRAINT categories_description_has_supported_keys CHECK (
        description - 'HY-AM' - 'EN-US' - 'RU-RU' = '{}'::jsonb
    ),
    CONSTRAINT categories_description_values_are_strings CHECK (
        NOT description ? 'HY-AM'
        OR jsonb_typeof(description -> 'HY-AM') = 'string'
    ),
    CONSTRAINT categories_description_en_us_value_is_string CHECK (
        NOT description ? 'EN-US'
        OR jsonb_typeof(description -> 'EN-US') = 'string'
    ),
    CONSTRAINT categories_description_ru_ru_value_is_string CHECK (
        NOT description ? 'RU-RU'
        OR jsonb_typeof(description -> 'RU-RU') = 'string'
    )
);

CREATE INDEX categories_parent_sort_order_idx ON categories(parent_id, sort_order);
CREATE INDEX categories_status_idx ON categories(status);

-- +goose StatementBegin
CREATE FUNCTION set_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
-- +goose StatementEnd

CREATE TRIGGER categories_set_updated_at
BEFORE UPDATE ON categories
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- +goose Down
DROP TRIGGER IF EXISTS categories_set_updated_at ON categories;
DROP FUNCTION IF EXISTS set_updated_at();
DROP TABLE IF EXISTS categories;
DROP TYPE IF EXISTS category_status;
DROP TYPE IF EXISTS language_code;
