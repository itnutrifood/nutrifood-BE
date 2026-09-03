-- +goose Up
ALTER TABLE user_addresses
ADD COLUMN apartment varchar(50),
ADD COLUMN label varchar(32),
ADD COLUMN latitude numeric(9, 6),
ADD COLUMN longitude numeric(10, 6),
ADD COLUMN formatted_address varchar(500),
ADD COLUMN location_source varchar(20) NOT NULL DEFAULT 'manual',
ADD COLUMN provider_uri varchar(512),
ADD COLUMN geocode_kind varchar(32),
ADD COLUMN geocode_precision varchar(32),
ADD CONSTRAINT user_addresses_apartment_not_blank CHECK (
    apartment IS NULL OR btrim(apartment) <> ''
),
ADD CONSTRAINT user_addresses_latitude_valid CHECK (
    latitude IS NULL OR latitude BETWEEN -90 AND 90
),
ADD CONSTRAINT user_addresses_longitude_valid CHECK (
    longitude IS NULL OR longitude BETWEEN -180 AND 180
),
ADD CONSTRAINT user_addresses_location_pair CHECK (
    (latitude IS NULL) = (longitude IS NULL)
),
ADD CONSTRAINT user_addresses_formatted_address_not_blank CHECK (
    formatted_address IS NULL OR btrim(formatted_address) <> ''
),
ADD CONSTRAINT user_addresses_location_source_valid CHECK (
    location_source IN ('manual', 'yandex')
),
ADD CONSTRAINT user_addresses_provider_uri_not_blank CHECK (
    provider_uri IS NULL OR btrim(provider_uri) <> ''
),
ADD CONSTRAINT user_addresses_geocode_kind_not_blank CHECK (
    geocode_kind IS NULL OR btrim(geocode_kind) <> ''
),
ADD CONSTRAINT user_addresses_geocode_precision_not_blank CHECK (
    geocode_precision IS NULL OR btrim(geocode_precision) <> ''
),
ADD CONSTRAINT user_addresses_yandex_location_complete CHECK (
    location_source <> 'yandex'
    OR (
        latitude IS NOT NULL
        AND longitude IS NOT NULL
        AND formatted_address IS NOT NULL
        AND geocode_kind IS NOT NULL
    )
);

ALTER TABLE orders
ADD COLUMN delivery_apartment varchar(50),
ADD COLUMN delivery_latitude numeric(9, 6),
ADD COLUMN delivery_longitude numeric(10, 6),
ADD COLUMN delivery_formatted_address varchar(500),
ADD COLUMN delivery_location_source varchar(20) NOT NULL DEFAULT 'manual',
ADD CONSTRAINT orders_delivery_apartment_not_blank CHECK (
    delivery_apartment IS NULL OR btrim(delivery_apartment) <> ''
),
ADD CONSTRAINT orders_delivery_latitude_valid CHECK (
    delivery_latitude IS NULL OR delivery_latitude BETWEEN -90 AND 90
),
ADD CONSTRAINT orders_delivery_longitude_valid CHECK (
    delivery_longitude IS NULL OR delivery_longitude BETWEEN -180 AND 180
),
ADD CONSTRAINT orders_delivery_location_pair CHECK (
    (delivery_latitude IS NULL) = (delivery_longitude IS NULL)
),
ADD CONSTRAINT orders_delivery_formatted_address_not_blank CHECK (
    delivery_formatted_address IS NULL OR btrim(delivery_formatted_address) <> ''
),
ADD CONSTRAINT orders_delivery_location_source_valid CHECK (
    delivery_location_source IN ('manual', 'yandex')
),
ADD CONSTRAINT orders_yandex_delivery_location_complete CHECK (
    delivery_location_source <> 'yandex'
    OR (
        delivery_latitude IS NOT NULL
        AND delivery_longitude IS NOT NULL
        AND delivery_formatted_address IS NOT NULL
    )
);

-- Existing addresses and orders remain marked as manual with nullable coordinates.
-- Existing address labels remain null.
-- New map-picked addresses are required by the application to contain complete Yandex data.

-- +goose Down
ALTER TABLE orders
DROP COLUMN IF EXISTS delivery_location_source,
DROP COLUMN IF EXISTS delivery_formatted_address,
DROP COLUMN IF EXISTS delivery_longitude,
DROP COLUMN IF EXISTS delivery_latitude,
DROP COLUMN IF EXISTS delivery_apartment;

ALTER TABLE user_addresses
DROP COLUMN IF EXISTS geocode_precision,
DROP COLUMN IF EXISTS geocode_kind,
DROP COLUMN IF EXISTS provider_uri,
DROP COLUMN IF EXISTS location_source,
DROP COLUMN IF EXISTS formatted_address,
DROP COLUMN IF EXISTS longitude,
DROP COLUMN IF EXISTS latitude,
DROP COLUMN IF EXISTS label,
DROP COLUMN IF EXISTS apartment;
