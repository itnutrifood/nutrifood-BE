#!/usr/bin/env python3

import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config.settings import get_settings  # noqa: E402


def localized_text(value: str) -> dict[str, str]:
    return {
        "HY-AM": value,
        "EN-US": value,
        "RU-RU": value,
    }


def optional_text(value: str) -> dict[str, str]:
    return {"EN-US": value}


def localized_words(*values: str) -> dict[str, list[str]]:
    return {
        "HY-AM": list(values),
        "EN-US": list(values),
        "RU-RU": list(values),
    }


def jsonb(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


CATEGORIES: list[dict[str, Any]] = [
    {
        "slug": "organic-bowls",
        "name": localized_text("Organic Bowls"),
        "description": optional_text("Balanced organic bowls with whole grains and greens."),
        "sort_order": 10,
    },
    {
        "slug": "high-protein",
        "name": localized_text("High Protein"),
        "description": optional_text("Protein-forward meals for training and recovery."),
        "sort_order": 20,
    },
    {
        "slug": "low-carb",
        "name": localized_text("Low Carb"),
        "description": optional_text("Fresh meals with lighter carbs and extra vegetables."),
        "sort_order": 30,
    },
    {
        "slug": "plant-based",
        "name": localized_text("Plant Based"),
        "description": optional_text(
            "Vegan and vegetarian options built around clean ingredients."
        ),
        "sort_order": 40,
    },
    {
        "slug": "cold-pressed-juices",
        "name": localized_text("Cold-Pressed Juices"),
        "description": optional_text("Organic juices pressed from fruits, roots, and greens."),
        "sort_order": 50,
    },
    {
        "slug": "healthy-snacks",
        "name": localized_text("Healthy Snacks"),
        "description": optional_text("Clean snacks for energy between meals."),
        "sort_order": 60,
    },
    {
        "slug": "fit-breakfast",
        "name": localized_text("Fit Breakfast"),
        "description": optional_text("Light, nutrient-dense breakfast meals."),
        "sort_order": 70,
    },
]

PRODUCTS: list[dict[str, Any]] = [
    {
        "slug": "quinoa-avocado-power-bowl",
        "title": localized_text("Quinoa Avocado Power Bowl"),
        "description": localized_text(
            "Organic quinoa, avocado, roasted chickpeas, greens, and tahini lemon dressing."
        ),
        "images": [
            {
                "url": "https://cdn.nutrifood.local/products/quinoa-avocado-power-bowl.jpg",
                "width": 1200,
                "height": 900,
                "size_bytes": 420000,
            }
        ],
        "category_slugs": ["organic-bowls", "plant-based"],
        "image_tags": localized_words("organic", "vegan", "bowl"),
        "text_tags": localized_words("Organic", "Vegan", "Fiber Rich"),
        "serving_size": optional_text("420g"),
        "readiness_time_minutes": 5,
        "price": Decimal("11.90"),
        "allergens": localized_words("Sesame"),
        "allergen_information": optional_text("Contains sesame tahini dressing."),
        "storage_delivery": optional_text("Keep chilled. Best consumed within 24 hours."),
    },
    {
        "slug": "grilled-chicken-protein-box",
        "title": localized_text("Grilled Chicken Protein Box"),
        "description": localized_text(
            "Lean grilled chicken breast with brown rice, broccoli, edamame, and herb yogurt."
        ),
        "images": [
            {
                "url": "https://cdn.nutrifood.local/products/grilled-chicken-protein-box.jpg",
                "width": 1200,
                "height": 900,
                "size_bytes": 430000,
            }
        ],
        "category_slugs": ["high-protein", "organic-bowls"],
        "image_tags": localized_words("protein", "chicken", "meal prep"),
        "text_tags": localized_words("High Protein", "Lean", "Post Workout"),
        "serving_size": optional_text("450g"),
        "readiness_time_minutes": 4,
        "price": Decimal("13.50"),
        "allergens": localized_words("Milk", "Soy"),
        "allergen_information": optional_text("Contains yogurt sauce and edamame."),
        "storage_delivery": optional_text("Keep chilled. Reheat before serving."),
    },
    {
        "slug": "salmon-omega-fit-plate",
        "title": localized_text("Salmon Omega Fit Plate"),
        "description": localized_text(
            "Baked salmon with sweet potato, asparagus, greens, and citrus herb sauce."
        ),
        "images": [
            {
                "url": "https://cdn.nutrifood.local/products/salmon-omega-fit-plate.jpg",
                "width": 1200,
                "height": 900,
                "size_bytes": 460000,
            }
        ],
        "category_slugs": ["high-protein", "low-carb"],
        "image_tags": localized_words("salmon", "omega", "low carb"),
        "text_tags": localized_words("Omega 3", "High Protein", "Gluten Free"),
        "serving_size": optional_text("430g"),
        "readiness_time_minutes": 5,
        "price": Decimal("16.90"),
        "allergens": localized_words("Fish"),
        "allergen_information": optional_text("Contains salmon."),
        "storage_delivery": optional_text("Keep chilled. Reheat gently before serving."),
    },
    {
        "slug": "vegan-lentil-fit-bowl",
        "title": localized_text("Vegan Lentil Fit Bowl"),
        "description": localized_text(
            "Green lentils, roasted seasonal vegetables, spinach, herbs, and pumpkin seeds."
        ),
        "images": [
            {
                "url": "https://cdn.nutrifood.local/products/vegan-lentil-fit-bowl.jpg",
                "width": 1200,
                "height": 900,
                "size_bytes": 410000,
            }
        ],
        "category_slugs": ["plant-based", "organic-bowls"],
        "image_tags": localized_words("vegan", "lentils", "organic"),
        "text_tags": localized_words("Vegan", "Plant Protein", "Fiber Rich"),
        "serving_size": optional_text("440g"),
        "readiness_time_minutes": 4,
        "price": Decimal("10.80"),
        "allergens": localized_words("Pumpkin Seeds"),
        "allergen_information": optional_text("Contains pumpkin seeds."),
        "storage_delivery": optional_text("Keep chilled. Reheat or enjoy cold."),
    },
    {
        "slug": "chia-berry-protein-pudding",
        "title": localized_text("Chia Berry Protein Pudding"),
        "description": localized_text(
            "Chia pudding with almond milk, mixed berries, plant protein, and cacao nibs."
        ),
        "images": [
            {
                "url": "https://cdn.nutrifood.local/products/chia-berry-protein-pudding.jpg",
                "width": 1200,
                "height": 900,
                "size_bytes": 360000,
            }
        ],
        "category_slugs": ["fit-breakfast", "plant-based"],
        "image_tags": localized_words("breakfast", "chia", "berries"),
        "text_tags": localized_words("Breakfast", "Plant Protein", "No Added Sugar"),
        "serving_size": optional_text("280g"),
        "readiness_time_minutes": 2,
        "price": Decimal("7.90"),
        "allergens": localized_words("Tree Nuts"),
        "allergen_information": optional_text("Contains almond milk."),
        "storage_delivery": optional_text("Keep chilled. Ready to eat."),
    },
    {
        "slug": "green-detox-cold-press",
        "title": localized_text("Green Detox Cold Press"),
        "description": localized_text(
            "Cold-pressed kale, cucumber, green apple, lemon, and ginger."
        ),
        "images": [
            {
                "url": "https://cdn.nutrifood.local/products/green-detox-cold-press.jpg",
                "width": 1200,
                "height": 900,
                "size_bytes": 300000,
            }
        ],
        "category_slugs": ["cold-pressed-juices"],
        "image_tags": localized_words("juice", "greens", "detox"),
        "text_tags": localized_words("Cold Pressed", "Organic", "No Added Sugar"),
        "serving_size": optional_text("330ml"),
        "readiness_time_minutes": 1,
        "price": Decimal("5.90"),
        "allergens": {},
        "allergen_information": {},
        "storage_delivery": optional_text("Keep chilled. Shake before drinking."),
    },
    {
        "slug": "almond-date-protein-bites",
        "title": localized_text("Almond Date Protein Bites"),
        "description": localized_text(
            "Clean energy bites made with almonds, dates, oats, pea protein, and cacao."
        ),
        "images": [
            {
                "url": "https://cdn.nutrifood.local/products/almond-date-protein-bites.jpg",
                "width": 1200,
                "height": 900,
                "size_bytes": 320000,
            }
        ],
        "category_slugs": ["healthy-snacks", "high-protein"],
        "image_tags": localized_words("snack", "protein", "almond"),
        "text_tags": localized_words("Healthy Snack", "Protein", "Clean Energy"),
        "serving_size": optional_text("6 bites"),
        "readiness_time_minutes": 1,
        "price": Decimal("6.50"),
        "allergens": localized_words("Tree Nuts", "Oats"),
        "allergen_information": optional_text("Contains almonds and oats."),
        "storage_delivery": optional_text("Store chilled or in a cool dry place."),
    },
    {
        "slug": "egg-white-spinach-breakfast-wrap",
        "title": localized_text("Egg White Spinach Breakfast Wrap"),
        "description": localized_text(
            "Egg whites, spinach, mushrooms, cottage cheese, and whole-grain tortilla."
        ),
        "images": [
            {
                "url": "https://cdn.nutrifood.local/products/egg-white-spinach-breakfast-wrap.jpg",
                "width": 1200,
                "height": 900,
                "size_bytes": 390000,
            }
        ],
        "category_slugs": ["fit-breakfast", "high-protein"],
        "image_tags": localized_words("breakfast", "eggs", "protein"),
        "text_tags": localized_words("High Protein", "Breakfast", "Balanced"),
        "serving_size": optional_text("320g"),
        "readiness_time_minutes": 3,
        "price": Decimal("8.90"),
        "allergens": localized_words("Eggs", "Milk", "Wheat"),
        "allergen_information": optional_text("Contains eggs, cottage cheese, and wheat tortilla."),
        "storage_delivery": optional_text("Keep chilled. Reheat before serving."),
    },
]

SUBSCRIPTION_PLANS: list[dict[str, Any]] = [
    {
        "slug": "clean-start",
        "name": localized_text("Clean Start"),
        "description": optional_text("A light weekly plan for healthier daily habits."),
        "price": Decimal("69.00"),
        "billing_interval": localized_text("week"),
        "meal_count_label": optional_text("5 meals"),
        "is_popular": False,
        "sort_order": 10,
        "additional_info": localized_words(
            "5 chef-prepared meals",
            "Organic ingredients",
            "Balanced calories",
        ),
    },
    {
        "slug": "active-balance",
        "name": localized_text("Active Balance"),
        "description": optional_text("A balanced plan for active workdays and fitness routines."),
        "price": Decimal("119.00"),
        "billing_interval": localized_text("week"),
        "meal_count_label": optional_text("10 meals"),
        "is_popular": True,
        "sort_order": 20,
        "additional_info": localized_words(
            "10 meals per week",
            "High-protein options",
            "Fresh delivery twice weekly",
        ),
    },
    {
        "slug": "performance-pro",
        "name": localized_text("Performance Pro"),
        "description": optional_text("Protein-focused meal prep for training and recovery."),
        "price": Decimal("169.00"),
        "billing_interval": localized_text("week"),
        "meal_count_label": optional_text("15 meals"),
        "is_popular": False,
        "sort_order": 30,
        "additional_info": localized_words(
            "15 meals per week",
            "Macro-conscious recipes",
            "Post-workout friendly",
        ),
    },
    {
        "slug": "family-fit",
        "name": localized_text("Family Fit"),
        "description": optional_text("Clean organic meals for busy families."),
        "price": Decimal("229.00"),
        "billing_interval": localized_text("week"),
        "meal_count_label": optional_text("24 meals"),
        "is_popular": False,
        "sort_order": 40,
        "additional_info": localized_words(
            "24 family-size meals",
            "Kid-friendly healthy recipes",
            "Flexible weekly menu",
        ),
    },
]


async def seed_categories(connection: asyncpg.Connection) -> dict[str, UUID]:
    category_ids: dict[str, UUID] = {}
    for category in CATEGORIES:
        category_id = await connection.fetchval(
            """
            INSERT INTO categories (
                slug,
                name,
                description,
                status,
                sort_order
            )
            VALUES ($1, $2::jsonb, $3::jsonb, 'active', $4)
            ON CONFLICT (slug) DO UPDATE
            SET name = EXCLUDED.name,
                description = EXCLUDED.description,
                status = EXCLUDED.status,
                sort_order = EXCLUDED.sort_order,
                updated_at = now()
            RETURNING id
            """,
            category["slug"],
            jsonb(category["name"]),
            jsonb(category["description"]),
            category["sort_order"],
        )
        category_ids[str(category["slug"])] = category_id

    return category_ids


async def seed_products(connection: asyncpg.Connection, category_ids: dict[str, UUID]) -> None:
    for product in PRODUCTS:
        product_id = await connection.fetchval(
            """
            INSERT INTO products (
                slug,
                title,
                description,
                images,
                image_tags,
                text_tags,
                serving_size,
                readiness_time_minutes,
                price,
                allergens,
                allergen_information,
                storage_delivery
            )
            VALUES (
                $1,
                $2::jsonb,
                $3::jsonb,
                $4::jsonb,
                $5::jsonb,
                $6::jsonb,
                $7::jsonb,
                $8,
                $9,
                $10::jsonb,
                $11::jsonb,
                $12::jsonb
            )
            ON CONFLICT (slug) DO UPDATE
            SET title = EXCLUDED.title,
                description = EXCLUDED.description,
                images = EXCLUDED.images,
                image_tags = EXCLUDED.image_tags,
                text_tags = EXCLUDED.text_tags,
                serving_size = EXCLUDED.serving_size,
                readiness_time_minutes = EXCLUDED.readiness_time_minutes,
                price = EXCLUDED.price,
                allergens = EXCLUDED.allergens,
                allergen_information = EXCLUDED.allergen_information,
                storage_delivery = EXCLUDED.storage_delivery,
                updated_at = now()
            RETURNING id
            """,
            product["slug"],
            jsonb(product["title"]),
            jsonb(product["description"]),
            jsonb(product["images"]),
            jsonb(product["image_tags"]),
            jsonb(product["text_tags"]),
            jsonb(product["serving_size"]),
            product["readiness_time_minutes"],
            product["price"],
            jsonb(product["allergens"]),
            jsonb(product["allergen_information"]),
            jsonb(product["storage_delivery"]),
        )

        await connection.execute(
            "DELETE FROM product_categories WHERE product_id = $1",
            product_id,
        )
        await connection.executemany(
            """
            INSERT INTO product_categories (product_id, category_id)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING
            """,
            [
                (product_id, category_ids[str(category_slug)])
                for category_slug in product["category_slugs"]
            ],
        )


async def seed_subscription_plans(connection: asyncpg.Connection) -> None:
    for plan in SUBSCRIPTION_PLANS:
        await connection.execute(
            """
            INSERT INTO subscription_plans (
                slug,
                name,
                description,
                price,
                billing_interval,
                meal_count_label,
                is_popular,
                status,
                sort_order,
                additional_info
            )
            VALUES (
                $1,
                $2::jsonb,
                $3::jsonb,
                $4,
                $5::jsonb,
                $6::jsonb,
                $7,
                'active',
                $8,
                $9::jsonb
            )
            ON CONFLICT (slug) DO UPDATE
            SET name = EXCLUDED.name,
                description = EXCLUDED.description,
                price = EXCLUDED.price,
                billing_interval = EXCLUDED.billing_interval,
                meal_count_label = EXCLUDED.meal_count_label,
                is_popular = EXCLUDED.is_popular,
                status = EXCLUDED.status,
                sort_order = EXCLUDED.sort_order,
                additional_info = EXCLUDED.additional_info,
                updated_at = now()
            """,
            plan["slug"],
            jsonb(plan["name"]),
            jsonb(plan["description"]),
            plan["price"],
            jsonb(plan["billing_interval"]),
            jsonb(plan["meal_count_label"]),
            plan["is_popular"],
            plan["sort_order"],
            jsonb(plan["additional_info"]),
        )


async def seed_catalog() -> None:
    load_dotenv()
    get_settings.cache_clear()
    settings = get_settings()
    pool = await asyncpg.create_pool(dsn=settings.database_url, min_size=1, max_size=1)

    try:
        async with pool.acquire() as connection:
            async with connection.transaction():
                category_ids = await seed_categories(connection)
                await seed_products(connection, category_ids)
                await seed_subscription_plans(connection)
    finally:
        await pool.close()

    print(
        "Seeded catalog: "
        f"{len(CATEGORIES)} categories, "
        f"{len(PRODUCTS)} products, "
        f"{len(SUBSCRIPTION_PLANS)} subscription plans"
    )


if __name__ == "__main__":
    asyncio.run(seed_catalog())
