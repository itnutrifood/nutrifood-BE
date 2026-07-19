from typing import Any, cast

from scripts.seed_catalog import TESTIMONIALS, seed_testimonials


class SeedConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def execute(self, query: str, *args: object) -> str:
        self.calls.append((query, args))
        return "INSERT 0 1"


async def test_seeds_five_testimonials_idempotently() -> None:
    connection = SeedConnection()

    await seed_testimonials(cast(Any, connection))

    assert len(TESTIMONIALS) == 5
    assert len(connection.calls) == 5
    assert len({testimonial["id"] for testimonial in TESTIMONIALS}) == 5

    for query, args in connection.calls:
        assert "ON CONFLICT (id) DO UPDATE" in query
        assert "status,\n                sort_order" in query
        assert len(args) == 8
        assert args[6] in range(1, 6)
