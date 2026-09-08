from typing import Annotated

from fastapi import Depends, HTTPException, status

from backend.config.settings import Settings, get_settings


def require_non_production_environment(
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    if settings.is_production:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
