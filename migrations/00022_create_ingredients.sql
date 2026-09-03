-- +goose Up
CREATE TABLE ingredients (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ingredients_name_is_object CHECK (jsonb_typeof(name) = 'object'),
    CONSTRAINT ingredients_name_has_supported_keys CHECK (
        name ? 'HY-AM'
        AND name ? 'EN-US'
        AND name ? 'RU-RU'
        AND name - 'HY-AM' - 'EN-US' - 'RU-RU' = '{}'::jsonb
    ),
    CONSTRAINT ingredients_name_values_are_valid CHECK (
        jsonb_typeof(name -> 'HY-AM') = 'string'
        AND btrim(name ->> 'HY-AM') <> ''
        AND length(name ->> 'HY-AM') <= 255
        AND jsonb_typeof(name -> 'EN-US') = 'string'
        AND btrim(name ->> 'EN-US') <> ''
        AND length(name ->> 'EN-US') <= 255
        AND jsonb_typeof(name -> 'RU-RU') = 'string'
        AND btrim(name ->> 'RU-RU') <> ''
        AND length(name ->> 'RU-RU') <= 255
    )
);

CREATE UNIQUE INDEX ingredients_localized_name_unique_idx ON ingredients (
    lower(btrim(name ->> 'HY-AM')),
    lower(btrim(name ->> 'EN-US')),
    lower(btrim(name ->> 'RU-RU'))
);
CREATE INDEX ingredients_en_us_name_idx ON ingredients (lower(name ->> 'EN-US'));

CREATE TRIGGER ingredients_set_updated_at
BEFORE UPDATE ON ingredients
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- +goose Down
DROP TRIGGER IF EXISTS ingredients_set_updated_at ON ingredients;
DROP TABLE IF EXISTS ingredients;
