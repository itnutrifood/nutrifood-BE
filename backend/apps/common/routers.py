from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter


def create_placeholder_router(
    prefix: str,
    tag: str,
    dependencies: Sequence[Any] | None = None,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[tag], dependencies=list(dependencies or ()))

    @router.get("")
    async def list_placeholder() -> dict[str, str]:
        return {"module": tag, "status": "ready"}

    return router
