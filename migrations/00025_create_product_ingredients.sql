-- +goose Up
CREATE TABLE product_ingredients (
    product_id uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    ingredient_id uuid NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (product_id, ingredient_id)
);

CREATE INDEX product_ingredients_ingredient_id_idx ON product_ingredients(ingredient_id);

-- +goose Down
DROP TABLE IF EXISTS product_ingredients;
