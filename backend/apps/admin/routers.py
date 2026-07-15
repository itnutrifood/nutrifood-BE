from fastapi import APIRouter, Depends

from backend.apps.admin.auth import admin_auth
from backend.apps.admin.auth import router as auth_router
from backend.apps.admin.categories import router as categories_router
from backend.apps.admin.faqs import router as faqs_router
from backend.apps.admin.products import router as products_router
from backend.apps.admin.subscriptions import router as subscriptions_router

router = APIRouter()
protected_router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(admin_auth)],
)


@protected_router.get("")
async def read_admin_status() -> dict[str, str]:
    return {"module": "admin", "status": "ready"}


protected_router.include_router(categories_router)
protected_router.include_router(faqs_router)
protected_router.include_router(products_router)
protected_router.include_router(subscriptions_router)

router.include_router(auth_router, prefix="/admin")
router.include_router(protected_router)
