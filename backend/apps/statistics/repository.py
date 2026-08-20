from collections.abc import Mapping
from typing import cast

import asyncpg

from backend.apps.statistics.schemas import PublicStatistics


async def get_public_statistics(pool: asyncpg.Pool) -> PublicStatistics:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            """
            SELECT
                (SELECT count(*) FROM orders) AS happy_customers,
                (SELECT count(*) FROM products) AS healty_meals,
                COALESCE(
                    (
                        SELECT round(avg(rating), 1)
                        FROM testimonials
                        WHERE status = 'active'::testimonial_status
                    ),
                    0
                )::double precision AS customer_rating
            """
        ),
    )
    if row is None:
        raise RuntimeError("Statistics query did not return a row")

    return PublicStatistics(
        happy_customers=cast(int, row["happy_customers"]),
        healty_meals=cast(int, row["healty_meals"]),
        customer_rating=cast(float, row["customer_rating"]),
    )
