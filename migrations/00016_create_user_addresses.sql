-- +goose Up
CREATE TYPE armenia_region AS ENUM (
    'Aragatsotn',
    'Ararat',
    'Armavir',
    'Gegharkunik',
    'Kotayk',
    'Lori',
    'Shirak',
    'Syunik',
    'Tavush',
    'Vayots Dzor',
    'Yerevan'
);

CREATE TABLE user_addresses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    country varchar(64) NOT NULL DEFAULT 'Armenia',
    region armenia_region NOT NULL,
    city varchar(150) NOT NULL,
    street varchar(255) NOT NULL,
    building_number varchar(50) NOT NULL,
    entrance varchar(50),
    floor varchar(50),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT user_addresses_country_armenia CHECK (country = 'Armenia'),
    CONSTRAINT user_addresses_city_not_blank CHECK (btrim(city) <> ''),
    CONSTRAINT user_addresses_street_not_blank CHECK (btrim(street) <> ''),
    CONSTRAINT user_addresses_building_number_not_blank CHECK (btrim(building_number) <> ''),
    CONSTRAINT user_addresses_entrance_not_blank CHECK (
        entrance IS NULL OR btrim(entrance) <> ''
    ),
    CONSTRAINT user_addresses_floor_not_blank CHECK (floor IS NULL OR btrim(floor) <> '')
);

CREATE INDEX user_addresses_user_order_idx
ON user_addresses(user_id, created_at DESC, id DESC);

CREATE TRIGGER user_addresses_set_updated_at
BEFORE UPDATE ON user_addresses
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- +goose Down
DROP TRIGGER IF EXISTS user_addresses_set_updated_at ON user_addresses;
DROP TABLE IF EXISTS user_addresses;
DROP TYPE IF EXISTS armenia_region;
