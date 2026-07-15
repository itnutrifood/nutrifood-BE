-- +goose Up
CREATE TYPE faq_status AS ENUM ('active', 'inactive');

CREATE TABLE faqs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug text NOT NULL UNIQUE,
    question jsonb NOT NULL,
    answer jsonb NOT NULL,
    status faq_status NOT NULL DEFAULT 'active',
    sort_order integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT faqs_slug_not_blank CHECK (btrim(slug) <> ''),
    CONSTRAINT faqs_sort_order_non_negative CHECK (sort_order >= 0),
    CONSTRAINT faqs_question_is_object CHECK (jsonb_typeof(question) = 'object'),
    CONSTRAINT faqs_question_has_supported_keys CHECK (
        question ? 'HY-AM'
        AND question ? 'EN-US'
        AND question ? 'RU-RU'
        AND question - 'HY-AM' - 'EN-US' - 'RU-RU' = '{}'::jsonb
    ),
    CONSTRAINT faqs_question_values_not_blank CHECK (
        jsonb_typeof(question -> 'HY-AM') = 'string'
        AND btrim(question ->> 'HY-AM') <> ''
        AND jsonb_typeof(question -> 'EN-US') = 'string'
        AND btrim(question ->> 'EN-US') <> ''
        AND jsonb_typeof(question -> 'RU-RU') = 'string'
        AND btrim(question ->> 'RU-RU') <> ''
    ),
    CONSTRAINT faqs_answer_is_object CHECK (jsonb_typeof(answer) = 'object'),
    CONSTRAINT faqs_answer_has_supported_keys CHECK (
        answer ? 'HY-AM'
        AND answer ? 'EN-US'
        AND answer ? 'RU-RU'
        AND answer - 'HY-AM' - 'EN-US' - 'RU-RU' = '{}'::jsonb
    ),
    CONSTRAINT faqs_answer_values_not_blank CHECK (
        jsonb_typeof(answer -> 'HY-AM') = 'string'
        AND btrim(answer ->> 'HY-AM') <> ''
        AND jsonb_typeof(answer -> 'EN-US') = 'string'
        AND btrim(answer ->> 'EN-US') <> ''
        AND jsonb_typeof(answer -> 'RU-RU') = 'string'
        AND btrim(answer ->> 'RU-RU') <> ''
    )
);

CREATE INDEX faqs_public_order_idx ON faqs(status, sort_order, slug, id);

CREATE TRIGGER faqs_set_updated_at
BEFORE UPDATE ON faqs
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- +goose Down
DROP TRIGGER IF EXISTS faqs_set_updated_at ON faqs;
DROP TABLE IF EXISTS faqs;
DROP TYPE IF EXISTS faq_status;
