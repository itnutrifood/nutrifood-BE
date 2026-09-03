import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

import asyncpg

from backend.apps.common.db import json_object, rows_affected
from backend.apps.common.pagination import page_count, page_offset
from backend.apps.ingredients.exceptions import (
    DuplicateIngredientNameError,
    IngredientNotFoundError,
)
from backend.apps.ingredients.schemas import (
    IngredientCreate,
    IngredientListResponse,
    IngredientRead,
    IngredientUpdate,
    LocalizedIngredientName,
)

INGREDIENT_COLUMNS = """
    id,
    name,
    created_at,
    updated_at
"""


def ingredient_from_record(record: Mapping[str, object]) -> IngredientRead:
    return IngredientRead(
        id=cast(UUID, record["id"]),
        name=LocalizedIngredientName.model_validate(json_object(record["name"])),
        created_at=cast(datetime, record["created_at"]),
        updated_at=cast(datetime, record["updated_at"]),
    )


async def create_ingredient(pool: asyncpg.Pool, payload: IngredientCreate) -> IngredientRead:
    try:
        row = cast(
            Mapping[str, object] | None,
            await pool.fetchrow(
                f"""
                INSERT INTO ingredients (name)
                VALUES ($1::jsonb)
                RETURNING {INGREDIENT_COLUMNS}
                """,
                json.dumps(payload.name.to_db()),
            ),
        )
    except asyncpg.UniqueViolationError as exc:
        raise DuplicateIngredientNameError from exc

    if row is None:
        raise RuntimeError("Ingredient insert did not return a row")
    return ingredient_from_record(row)


async def get_ingredient(pool: asyncpg.Pool, ingredient_id: UUID) -> IngredientRead:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"SELECT {INGREDIENT_COLUMNS} FROM ingredients WHERE id = $1",
            ingredient_id,
        ),
    )
    if row is None:
        raise IngredientNotFoundError
    return ingredient_from_record(row)


async def list_ingredients(
    pool: asyncpg.Pool,
    page: int,
    limit: int,
) -> IngredientListResponse:
    count_row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow("SELECT count(*) AS total FROM ingredients"),
    )
    total = cast(int, count_row["total"]) if count_row is not None else 0

    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            f"""
            SELECT {INGREDIENT_COLUMNS}
            FROM ingredients
            ORDER BY lower(name ->> 'EN-US'), id
            LIMIT $1
            OFFSET $2
            """,
            limit,
            page_offset(page, limit),
        ),
    )
    return IngredientListResponse(
        items=[ingredient_from_record(row) for row in rows],
        total=total,
        page=page,
        limit=limit,
        total_pages=page_count(total, limit),
    )


async def update_ingredient(
    pool: asyncpg.Pool,
    ingredient_id: UUID,
    payload: IngredientUpdate,
) -> IngredientRead:
    name = cast(LocalizedIngredientName, payload.name)
    try:
        row = cast(
            Mapping[str, object] | None,
            await pool.fetchrow(
                f"""
                UPDATE ingredients
                SET name = $1::jsonb
                WHERE id = $2
                RETURNING {INGREDIENT_COLUMNS}
                """,
                json.dumps(name.to_db()),
                ingredient_id,
            ),
        )
    except asyncpg.UniqueViolationError as exc:
        raise DuplicateIngredientNameError from exc

    if row is None:
        raise IngredientNotFoundError
    return ingredient_from_record(row)


async def delete_ingredient(pool: asyncpg.Pool, ingredient_id: UUID) -> None:
    command_status = cast(
        str,
        await pool.execute("DELETE FROM ingredients WHERE id = $1", ingredient_id),
    )
    if rows_affected(command_status) == 0:
        raise IngredientNotFoundError
