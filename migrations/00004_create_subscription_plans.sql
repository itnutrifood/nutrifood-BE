-- +goose Up
CREATE TYPE subscription_plan_status AS ENUM ('active', 'inactive', 'archived');

CREATE TABLE subscription_plans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug text NOT NULL UNIQUE,
    name jsonb NOT NULL,
    description jsonb NOT NULL DEFAULT '{}'::jsonb,
    price numeric(10, 2) NOT NULL,
    billing_interval jsonb NOT NULL,
    meal_count_label jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_popular boolean NOT NULL DEFAULT false,
    status subscription_plan_status NOT NULL DEFAULT 'active',
    sort_order integer NOT NULL DEFAULT 0,
    additional_info jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT subscription_plans_slug_not_blank CHECK (btrim(slug) <> ''),
    CONSTRAINT subscription_plans_name_is_object CHECK (jsonb_typeof(name) = 'object'),
    CONSTRAINT subscription_plans_name_has_supported_keys CHECK (
        name ? 'HY-AM'
        AND name ? 'EN-US'
        AND name ? 'RU-RU'
        AND name - 'HY-AM' - 'EN-US' - 'RU-RU' = '{}'::jsonb
    ),
    CONSTRAINT subscription_plans_name_values_not_blank CHECK (
        jsonb_typeof(name -> 'HY-AM') = 'string'
        AND btrim(name ->> 'HY-AM') <> ''
        AND jsonb_typeof(name -> 'EN-US') = 'string'
        AND btrim(name ->> 'EN-US') <> ''
        AND jsonb_typeof(name -> 'RU-RU') = 'string'
        AND btrim(name ->> 'RU-RU') <> ''
    ),
    CONSTRAINT subscription_plans_description_is_object CHECK (
        jsonb_typeof(description) = 'object'
    ),
    CONSTRAINT subscription_plans_description_has_supported_keys CHECK (
        description - 'HY-AM' - 'EN-US' - 'RU-RU' = '{}'::jsonb
    ),
    CONSTRAINT subscription_plans_description_hy_am_value_is_string CHECK (
        NOT description ? 'HY-AM'
        OR jsonb_typeof(description -> 'HY-AM') = 'string'
    ),
    CONSTRAINT subscription_plans_description_en_us_value_is_string CHECK (
        NOT description ? 'EN-US'
        OR jsonb_typeof(description -> 'EN-US') = 'string'
    ),
    CONSTRAINT subscription_plans_description_ru_ru_value_is_string CHECK (
        NOT description ? 'RU-RU'
        OR jsonb_typeof(description -> 'RU-RU') = 'string'
    ),
    CONSTRAINT subscription_plans_price_non_negative CHECK (price >= 0),
    CONSTRAINT subscription_plans_billing_interval_is_object CHECK (
        jsonb_typeof(billing_interval) = 'object'
    ),
    CONSTRAINT subscription_plans_billing_interval_has_supported_keys CHECK (
        billing_interval ? 'HY-AM'
        AND billing_interval ? 'EN-US'
        AND billing_interval ? 'RU-RU'
        AND billing_interval - 'HY-AM' - 'EN-US' - 'RU-RU' = '{}'::jsonb
    ),
    CONSTRAINT subscription_plans_billing_interval_values_not_blank CHECK (
        jsonb_typeof(billing_interval -> 'HY-AM') = 'string'
        AND btrim(billing_interval ->> 'HY-AM') <> ''
        AND jsonb_typeof(billing_interval -> 'EN-US') = 'string'
        AND btrim(billing_interval ->> 'EN-US') <> ''
        AND jsonb_typeof(billing_interval -> 'RU-RU') = 'string'
        AND btrim(billing_interval ->> 'RU-RU') <> ''
    ),
    CONSTRAINT subscription_plans_meal_count_label_is_object CHECK (
        jsonb_typeof(meal_count_label) = 'object'
    ),
    CONSTRAINT subscription_plans_meal_count_label_has_supported_keys CHECK (
        meal_count_label - 'HY-AM' - 'EN-US' - 'RU-RU' = '{}'::jsonb
    ),
    CONSTRAINT subscription_plans_meal_count_label_hy_am_value_is_string CHECK (
        NOT meal_count_label ? 'HY-AM'
        OR (
            jsonb_typeof(meal_count_label -> 'HY-AM') = 'string'
            AND btrim(meal_count_label ->> 'HY-AM') <> ''
        )
    ),
    CONSTRAINT subscription_plans_meal_count_label_en_us_value_is_string CHECK (
        NOT meal_count_label ? 'EN-US'
        OR (
            jsonb_typeof(meal_count_label -> 'EN-US') = 'string'
            AND btrim(meal_count_label ->> 'EN-US') <> ''
        )
    ),
    CONSTRAINT subscription_plans_meal_count_label_ru_ru_value_is_string CHECK (
        NOT meal_count_label ? 'RU-RU'
        OR (
            jsonb_typeof(meal_count_label -> 'RU-RU') = 'string'
            AND btrim(meal_count_label ->> 'RU-RU') <> ''
        )
    ),
    CONSTRAINT subscription_plans_sort_order_non_negative CHECK (sort_order >= 0),
    CONSTRAINT subscription_plans_additional_info_values_not_blank CHECK (
        localized_text_array_values_not_blank(additional_info)
    )
);

CREATE INDEX subscription_plans_status_sort_order_idx
ON subscription_plans(status, sort_order);

CREATE INDEX subscription_plans_is_popular_idx
ON subscription_plans(is_popular)
WHERE is_popular;

CREATE TRIGGER subscription_plans_set_updated_at
BEFORE UPDATE ON subscription_plans
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- +goose Down
DROP TRIGGER IF EXISTS subscription_plans_set_updated_at ON subscription_plans;
DROP TABLE IF EXISTS subscription_plans;
DROP TYPE IF EXISTS subscription_plan_status;
