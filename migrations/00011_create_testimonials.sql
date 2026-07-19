-- +goose Up
CREATE TYPE testimonial_status AS ENUM ('active', 'inactive');

CREATE TABLE testimonials (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    first_name varchar(150) NOT NULL,
    last_name varchar(150) NOT NULL,
    author_title varchar(255) NOT NULL,
    photo_url text,
    review text NOT NULL,
    rating smallint NOT NULL,
    status testimonial_status NOT NULL DEFAULT 'active',
    sort_order integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT testimonials_first_name_not_blank CHECK (btrim(first_name) <> ''),
    CONSTRAINT testimonials_last_name_not_blank CHECK (btrim(last_name) <> ''),
    CONSTRAINT testimonials_author_title_not_blank CHECK (btrim(author_title) <> ''),
    CONSTRAINT testimonials_photo_url_valid CHECK (
        photo_url IS NULL OR (btrim(photo_url) <> '' AND char_length(photo_url) <= 2048)
    ),
    CONSTRAINT testimonials_review_valid CHECK (
        btrim(review) <> '' AND char_length(review) <= 5000
    ),
    CONSTRAINT testimonials_rating_valid CHECK (rating BETWEEN 1 AND 5),
    CONSTRAINT testimonials_sort_order_non_negative CHECK (sort_order >= 0)
);

CREATE INDEX testimonials_public_order_idx
ON testimonials(status, sort_order, created_at DESC, id DESC);

CREATE TRIGGER testimonials_set_updated_at
BEFORE UPDATE ON testimonials
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- +goose Down
DROP TRIGGER IF EXISTS testimonials_set_updated_at ON testimonials;
DROP TABLE IF EXISTS testimonials;
DROP TYPE IF EXISTS testimonial_status;
