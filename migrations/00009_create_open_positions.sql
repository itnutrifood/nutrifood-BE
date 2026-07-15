-- +goose Up
CREATE TYPE employment_type AS ENUM ('full_time', 'part_time');
CREATE TYPE open_position_status AS ENUM ('active', 'inactive');

CREATE TABLE open_positions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title jsonb NOT NULL,
    employment_type employment_type NOT NULL,
    description jsonb NOT NULL,
    position jsonb NOT NULL,
    city jsonb NOT NULL,
    status open_position_status NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT open_positions_title_valid CHECK (
        jsonb_typeof(title) = 'object'
        AND title ?& ARRAY['HY-AM', 'EN-US', 'RU-RU']
        AND title - 'HY-AM' - 'EN-US' - 'RU-RU' = '{}'::jsonb
        AND jsonb_typeof(title -> 'HY-AM') = 'string'
        AND btrim(title ->> 'HY-AM') <> ''
        AND char_length(title ->> 'HY-AM') <= 255
        AND jsonb_typeof(title -> 'EN-US') = 'string'
        AND btrim(title ->> 'EN-US') <> ''
        AND char_length(title ->> 'EN-US') <= 255
        AND jsonb_typeof(title -> 'RU-RU') = 'string'
        AND btrim(title ->> 'RU-RU') <> ''
        AND char_length(title ->> 'RU-RU') <= 255
    ),
    CONSTRAINT open_positions_description_valid CHECK (
        jsonb_typeof(description) = 'object'
        AND description ?& ARRAY['HY-AM', 'EN-US', 'RU-RU']
        AND description - 'HY-AM' - 'EN-US' - 'RU-RU' = '{}'::jsonb
        AND jsonb_typeof(description -> 'HY-AM') = 'string'
        AND btrim(description ->> 'HY-AM') <> ''
        AND char_length(description ->> 'HY-AM') <= 10000
        AND jsonb_typeof(description -> 'EN-US') = 'string'
        AND btrim(description ->> 'EN-US') <> ''
        AND char_length(description ->> 'EN-US') <= 10000
        AND jsonb_typeof(description -> 'RU-RU') = 'string'
        AND btrim(description ->> 'RU-RU') <> ''
        AND char_length(description ->> 'RU-RU') <= 10000
    ),
    CONSTRAINT open_positions_position_valid CHECK (
        jsonb_typeof(position) = 'object'
        AND position ?& ARRAY['HY-AM', 'EN-US', 'RU-RU']
        AND position - 'HY-AM' - 'EN-US' - 'RU-RU' = '{}'::jsonb
        AND jsonb_typeof(position -> 'HY-AM') = 'string'
        AND btrim(position ->> 'HY-AM') <> ''
        AND char_length(position ->> 'HY-AM') <= 255
        AND jsonb_typeof(position -> 'EN-US') = 'string'
        AND btrim(position ->> 'EN-US') <> ''
        AND char_length(position ->> 'EN-US') <= 255
        AND jsonb_typeof(position -> 'RU-RU') = 'string'
        AND btrim(position ->> 'RU-RU') <> ''
        AND char_length(position ->> 'RU-RU') <= 255
    ),
    CONSTRAINT open_positions_city_valid CHECK (
        jsonb_typeof(city) = 'object'
        AND city ?& ARRAY['HY-AM', 'EN-US', 'RU-RU']
        AND city - 'HY-AM' - 'EN-US' - 'RU-RU' = '{}'::jsonb
        AND jsonb_typeof(city -> 'HY-AM') = 'string'
        AND btrim(city ->> 'HY-AM') <> ''
        AND char_length(city ->> 'HY-AM') <= 255
        AND jsonb_typeof(city -> 'EN-US') = 'string'
        AND btrim(city ->> 'EN-US') <> ''
        AND char_length(city ->> 'EN-US') <= 255
        AND jsonb_typeof(city -> 'RU-RU') = 'string'
        AND btrim(city ->> 'RU-RU') <> ''
        AND char_length(city ->> 'RU-RU') <= 255
    )
);

CREATE INDEX open_positions_public_order_idx
ON open_positions(status, created_at DESC, id DESC);
CREATE INDEX open_positions_employment_type_idx
ON open_positions(status, employment_type, created_at DESC, id DESC);

CREATE TRIGGER open_positions_set_updated_at
BEFORE UPDATE ON open_positions
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- +goose Down
DROP TRIGGER IF EXISTS open_positions_set_updated_at ON open_positions;
DROP TABLE IF EXISTS open_positions;
DROP TYPE IF EXISTS open_position_status;
DROP TYPE IF EXISTS employment_type;
