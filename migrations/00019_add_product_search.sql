-- +goose Up
ALTER TABLE products
ADD COLUMN search_vector_hy_am tsvector GENERATED ALWAYS AS (
    setweight(
        to_tsvector(
            'pg_catalog.armenian'::regconfig,
            COALESCE(title ->> 'HY-AM', '')
        ),
        'A'
    )
    || setweight(
        to_tsvector(
            'pg_catalog.armenian'::regconfig,
            COALESCE(description ->> 'HY-AM', '')
        ),
        'B'
    )
) STORED,
ADD COLUMN search_vector_en_us tsvector GENERATED ALWAYS AS (
    setweight(
        to_tsvector(
            'pg_catalog.english'::regconfig,
            COALESCE(title ->> 'EN-US', '')
        ),
        'A'
    )
    || setweight(
        to_tsvector(
            'pg_catalog.english'::regconfig,
            COALESCE(description ->> 'EN-US', '')
        ),
        'B'
    )
) STORED,
ADD COLUMN search_vector_ru_ru tsvector GENERATED ALWAYS AS (
    setweight(
        to_tsvector(
            'pg_catalog.russian'::regconfig,
            COALESCE(title ->> 'RU-RU', '')
        ),
        'A'
    )
    || setweight(
        to_tsvector(
            'pg_catalog.russian'::regconfig,
            COALESCE(description ->> 'RU-RU', '')
        ),
        'B'
    )
) STORED;

CREATE INDEX products_search_vector_hy_am_idx
ON products USING GIN(search_vector_hy_am);

CREATE INDEX products_search_vector_en_us_idx
ON products USING GIN(search_vector_en_us);

CREATE INDEX products_search_vector_ru_ru_idx
ON products USING GIN(search_vector_ru_ru);

-- +goose Down
DROP INDEX IF EXISTS products_search_vector_ru_ru_idx;
DROP INDEX IF EXISTS products_search_vector_en_us_idx;
DROP INDEX IF EXISTS products_search_vector_hy_am_idx;

ALTER TABLE products
DROP COLUMN IF EXISTS search_vector_ru_ru,
DROP COLUMN IF EXISTS search_vector_en_us,
DROP COLUMN IF EXISTS search_vector_hy_am;
