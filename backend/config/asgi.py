from fastapi import FastAPI

from backend.config.database import lifespan
from backend.config.settings import get_settings
from backend.config.urls import api_router

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
    swagger_ui_parameters={"persistAuthorization": True},
)

app.include_router(api_router, prefix=settings.api_root_prefix)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "healthy"}
