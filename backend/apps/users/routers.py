from fastapi import APIRouter

from backend.apps.users.addresses.routers import router as addresses_router

router = APIRouter(prefix="/users", tags=["users"])

router.include_router(addresses_router)
