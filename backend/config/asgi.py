from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config.database import lifespan
from backend.config.exception_handlers import register_exception_handlers
from backend.config.settings import get_settings
from backend.config.urls import api_router

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
    swagger_ui_parameters={"persistAuthorization": True},
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_exception_handlers(app)

app.include_router(api_router, prefix=settings.api_root_prefix)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "healthy"}
