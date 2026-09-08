from collections.abc import Mapping, Sequence
from typing import cast
from uuid import UUID

import asyncpg

from backend.apps.common.enums import IngredientPreference
from backend.apps.users.ingredient_preferences.exceptions import (
    PreferenceIngredientNotFoundError,
)
from backend.apps.users.ingredient_preferences.schemas import IngredientPreferences


async def get_ingredient_preferences(
    pool: asyncpg.Pool,
    user_id: UUID,
) -> IngredientPreferences:
    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            """
            SELECT ingredient_id, preference
            FROM user_ingredient_preferences
            WHERE user_id = $1
            ORDER BY preference, ingredient_id
            """,
            user_id,
        ),
    )
    whitelisted_ids: list[UUID] = []
    blacklisted_ids: list[UUID] = []
    for row in rows:
        ingredient_id = cast(UUID, row["ingredient_id"])
        preference = IngredientPreference(cast(str, row["preference"]))
        if preference is IngredientPreference.WHITELISTED:
            whitelisted_ids.append(ingredient_id)
        else:
            blacklisted_ids.append(ingredient_id)

    return IngredientPreferences(
        whitelisted_ingredient_ids=whitelisted_ids,
        blacklisted_ingredient_ids=blacklisted_ids,
    )


async def replace_ingredient_preferences(
    pool: asyncpg.Pool,
    user_id: UUID,
    preferences: IngredientPreferences,
) -> None:
    requested_ids = sorted(
        {
            *preferences.whitelisted_ingredient_ids,
            *preferences.blacklisted_ingredient_ids,
        }
    )

    async with pool.acquire() as connection, connection.transaction():
        # Serialize replacements for the same user so concurrent PUT requests cannot interleave.
        await connection.fetchval(
            "SELECT id FROM users WHERE id = $1 FOR UPDATE",
            user_id,
        )

        ingredient_rows = cast(
            Sequence[Mapping[str, object]],
            await connection.fetch(
                """
                SELECT id
                FROM ingredients
                WHERE id = ANY($1::uuid[])
                ORDER BY id
                FOR KEY SHARE
                """,
                requested_ids,
            ),
        )
        existing_ids = {cast(UUID, row["id"]) for row in ingredient_rows}
        missing_ids = sorted(set(requested_ids) - existing_ids)
        if missing_ids:
            raise PreferenceIngredientNotFoundError(missing_ids)

        await connection.execute(
            """
            DELETE FROM user_ingredient_preferences
            WHERE user_id = $1
              AND NOT (ingredient_id = ANY($2::uuid[]))
            """,
            user_id,
            requested_ids,
        )
        await connection.execute(
            """
            INSERT INTO user_ingredient_preferences (user_id, ingredient_id, preference)
            SELECT $1, requested.ingredient_id, requested.preference::ingredient_preference
            FROM (
                SELECT ingredient_id, 'whitelisted' AS preference
                FROM unnest($2::uuid[]) AS ingredient_id
                UNION ALL
                SELECT ingredient_id, 'blacklisted' AS preference
                FROM unnest($3::uuid[]) AS ingredient_id
            ) AS requested
            ON CONFLICT (user_id, ingredient_id) DO UPDATE
            SET preference = EXCLUDED.preference
            WHERE user_ingredient_preferences.preference IS DISTINCT FROM EXCLUDED.preference
            """,
            user_id,
            preferences.whitelisted_ingredient_ids,
            preferences.blacklisted_ingredient_ids,
        )
