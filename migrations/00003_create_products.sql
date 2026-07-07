-- +goose Up
-- +goose StatementBegin
CREATE FUNCTION product_images_are_valid(images jsonb)
RETURNS boolean AS $$
    SELECT images IS NOT NULL
        AND jsonb_typeof(images) = 'array'
        AND jsonb_array_length(images) BETWEEN 1 AND 8
        AND NOT EXISTS (
            SELECT 1
            FROM jsonb_array_elements(images) AS image(item)
            WHERE jsonb_typeof(item) <> 'object'
                OR NOT item ? 'url'
                OR jsonb_typeof(item -> 'url') <> 'string'
                OR btrim(item ->> 'url') = ''
                OR length(item ->> 'url') > 2048
                OR item - 'url' - 'width' - 'height' - 'size_bytes' <> '{}'::jsonb
                OR (
                    item ? 'width'
                    AND (
                        jsonb_typeof(item -> 'width') <> 'number'
                        OR NOT item ->> 'width' ~ '^[0-9]+$'
                        OR (item ->> 'width')::numeric NOT BETWEEN 1 AND 4096
                    )
                )
                OR (
                    item ? 'height'
                    AND (
                        jsonb_typeof(item -> 'height') <> 'number'
                        OR NOT item ->> 'height' ~ '^[0-9]+$'
                        OR (item ->> 'height')::numeric NOT BETWEEN 1 AND 4096
                    )
                )
                OR (
                    item ? 'size_bytes'
                    AND (
                        jsonb_typeof(item -> 'size_bytes') <> 'number'
                        OR NOT item ->> 'size_bytes' ~ '^[0-9]+$'
                        OR (item ->> 'size_bytes')::numeric NOT BETWEEN 1 AND 5242880
                    )
                )
        );
$$ LANGUAGE sql IMMUTABLE;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION localized_text_array_values_not_blank(items jsonb)
RETURNS boolean AS $$
    SELECT items IS NOT NULL
        AND jsonb_typeof(items) = 'object'
        AND items - 'HY-AM' - 'EN-US' - 'RU-RU' = '{}'::jsonb
        AND NOT EXISTS (
            SELECT 1
            FROM jsonb_each(items) AS localized_item(language, values)
            WHERE jsonb_typeof(values) <> 'array'
                OR CASE
                    WHEN jsonb_typeof(values) = 'array' THEN
                        jsonb_array_length(values) = 0
                        OR EXISTS (
                            SELECT 1
                            FROM jsonb_array_elements(values) AS value(item)
                            WHERE jsonb_typeof(item) <> 'string'
                                OR btrim(item #>> '{}') = ''
                        )
                    ELSE false
                END
        );
$$ LANGUAGE sql IMMUTABLE;
-- +goose StatementEnd

CREATE TABLE products (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug text UNIQUE,
    title jsonb NOT NULL,
    description jsonb NOT NULL,
    images jsonb NOT NULL,
    image_tags jsonb NOT NULL DEFAULT '{}'::jsonb,
    text_tags jsonb NOT NULL DEFAULT '{}'::jsonb,
    serving_size jsonb NOT NULL DEFAULT '{}'::jsonb,
    readiness_time_minutes integer,
    price numeric(10, 2) NOT NULL,
    allergens jsonb NOT NULL DEFAULT '{}'::jsonb,
    allergen_information jsonb NOT NULL DEFAULT '{}'::jsonb,
    storage_delivery jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT products_slug_not_blank CHECK (slug IS NULL OR btrim(slug) <> ''),
    CONSTRAINT products_title_is_object CHECK (jsonb_typeof(title) = 'object'),
    CONSTRAINT products_title_has_supported_keys CHECK (
        title ? 'HY-AM'
        AND title ? 'EN-US'
        AND title ? 'RU-RU'
        AND title - 'HY-AM' - 'EN-US' - 'RU-RU' = '{}'::jsonb
    ),
    CONSTRAINT products_title_values_not_blank CHECK (
        jsonb_typeof(title -> 'HY-AM') = 'string'
        AND btrim(title ->> 'HY-AM') <> ''
        AND jsonb_typeof(title -> 'EN-US') = 'string'
        AND btrim(title ->> 'EN-US') <> ''
        AND jsonb_typeof(title -> 'RU-RU') = 'string'
        AND btrim(title ->> 'RU-RU') <> ''
    ),
    CONSTRAINT products_description_is_object CHECK (jsonb_typeof(description) = 'object'),
    CONSTRAINT products_description_has_supported_keys CHECK (
        description ? 'HY-AM'
        AND description ? 'EN-US'
        AND description ? 'RU-RU'
        AND description - 'HY-AM' - 'EN-US' - 'RU-RU' = '{}'::jsonb
    ),
    CONSTRAINT products_description_values_not_blank CHECK (
        jsonb_typeof(description -> 'HY-AM') = 'string'
        AND btrim(description ->> 'HY-AM') <> ''
        AND jsonb_typeof(description -> 'EN-US') = 'string'
        AND btrim(description ->> 'EN-US') <> ''
        AND jsonb_typeof(description -> 'RU-RU') = 'string'
        AND btrim(description ->> 'RU-RU') <> ''
    ),
    CONSTRAINT products_images_are_valid CHECK (product_images_are_valid(images)),
    CONSTRAINT products_image_tags_values_not_blank CHECK (
        localized_text_array_values_not_blank(image_tags)
    ),
    CONSTRAINT products_text_tags_values_not_blank CHECK (
        localized_text_array_values_not_blank(text_tags)
    ),
    CONSTRAINT products_serving_size_is_object CHECK (jsonb_typeof(serving_size) = 'object'),
    CONSTRAINT products_serving_size_has_supported_keys CHECK (
        serving_size - 'HY-AM' - 'EN-US' - 'RU-RU' = '{}'::jsonb
    ),
    CONSTRAINT products_serving_size_hy_am_value_is_string CHECK (
        NOT serving_size ? 'HY-AM'
        OR (
            jsonb_typeof(serving_size -> 'HY-AM') = 'string'
            AND btrim(serving_size ->> 'HY-AM') <> ''
        )
    ),
    CONSTRAINT products_serving_size_en_us_value_is_string CHECK (
        NOT serving_size ? 'EN-US'
        OR (
            jsonb_typeof(serving_size -> 'EN-US') = 'string'
            AND btrim(serving_size ->> 'EN-US') <> ''
        )
    ),
    CONSTRAINT products_serving_size_ru_ru_value_is_string CHECK (
        NOT serving_size ? 'RU-RU'
        OR (
            jsonb_typeof(serving_size -> 'RU-RU') = 'string'
            AND btrim(serving_size ->> 'RU-RU') <> ''
        )
    ),
    CONSTRAINT products_readiness_time_minutes_positive CHECK (
        readiness_time_minutes IS NULL OR readiness_time_minutes > 0
    ),
    CONSTRAINT products_price_non_negative CHECK (price >= 0),
    CONSTRAINT products_allergens_values_not_blank CHECK (
        localized_text_array_values_not_blank(allergens)
    ),
    CONSTRAINT products_allergen_information_is_object CHECK (
        jsonb_typeof(allergen_information) = 'object'
    ),
    CONSTRAINT products_allergen_information_has_supported_keys CHECK (
        allergen_information - 'HY-AM' - 'EN-US' - 'RU-RU' = '{}'::jsonb
    ),
    CONSTRAINT products_allergen_information_hy_am_value_is_string CHECK (
        NOT allergen_information ? 'HY-AM'
        OR (
            jsonb_typeof(allergen_information -> 'HY-AM') = 'string'
            AND btrim(allergen_information ->> 'HY-AM') <> ''
        )
    ),
    CONSTRAINT products_allergen_information_en_us_value_is_string CHECK (
        NOT allergen_information ? 'EN-US'
        OR (
            jsonb_typeof(allergen_information -> 'EN-US') = 'string'
            AND btrim(allergen_information ->> 'EN-US') <> ''
        )
    ),
    CONSTRAINT products_allergen_information_ru_ru_value_is_string CHECK (
        NOT allergen_information ? 'RU-RU'
        OR (
            jsonb_typeof(allergen_information -> 'RU-RU') = 'string'
            AND btrim(allergen_information ->> 'RU-RU') <> ''
        )
    ),
    CONSTRAINT products_storage_delivery_is_object CHECK (
        jsonb_typeof(storage_delivery) = 'object'
    ),
    CONSTRAINT products_storage_delivery_has_supported_keys CHECK (
        storage_delivery - 'HY-AM' - 'EN-US' - 'RU-RU' = '{}'::jsonb
    ),
    CONSTRAINT products_storage_delivery_hy_am_value_is_string CHECK (
        NOT storage_delivery ? 'HY-AM'
        OR (
            jsonb_typeof(storage_delivery -> 'HY-AM') = 'string'
            AND btrim(storage_delivery ->> 'HY-AM') <> ''
        )
    ),
    CONSTRAINT products_storage_delivery_en_us_value_is_string CHECK (
        NOT storage_delivery ? 'EN-US'
        OR (
            jsonb_typeof(storage_delivery -> 'EN-US') = 'string'
            AND btrim(storage_delivery ->> 'EN-US') <> ''
        )
    ),
    CONSTRAINT products_storage_delivery_ru_ru_value_is_string CHECK (
        NOT storage_delivery ? 'RU-RU'
        OR (
            jsonb_typeof(storage_delivery -> 'RU-RU') = 'string'
            AND btrim(storage_delivery ->> 'RU-RU') <> ''
        )
    )
);

CREATE TABLE product_categories (
    product_id uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    category_id uuid NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (product_id, category_id)
);

CREATE INDEX products_price_idx ON products(price);
CREATE INDEX product_categories_category_id_idx ON product_categories(category_id);

CREATE TRIGGER products_set_updated_at
BEFORE UPDATE ON products
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- +goose Down
DROP TRIGGER IF EXISTS products_set_updated_at ON products;
DROP TABLE IF EXISTS product_categories;
DROP TABLE IF EXISTS products;
DROP FUNCTION IF EXISTS localized_text_array_values_not_blank(jsonb);
DROP FUNCTION IF EXISTS product_images_are_valid(jsonb);
