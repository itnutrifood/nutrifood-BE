from fastapi import APIRouter

from backend.apps.accounts.routers import router as accounts_router
from backend.apps.admin.routers import router as admin_router
from backend.apps.cart.routers import router as cart_router
from backend.apps.categories.routers import router as categories_router
from backend.apps.checkout.routers import router as checkout_router
from backend.apps.cms.routers import router as cms_router
from backend.apps.contacts.routers import router as contacts_router
from backend.apps.delivery.routers import router as delivery_router
from backend.apps.faqs.routers import router as faqs_router
from backend.apps.favorites.routers import router as favorites_router
from backend.apps.notifications.routers import router as notifications_router
from backend.apps.open_positions.routers import router as open_positions_router
from backend.apps.orders.routers import router as orders_router
from backend.apps.payments.routers import router as payments_router
from backend.apps.products.routers import router as products_router
from backend.apps.quiz.routers import router as quiz_router
from backend.apps.subscriptions.routers import router as subscriptions_router
from backend.apps.support.routers import router as support_router

router = APIRouter()
localized_router = APIRouter(prefix="/{locale}")

router.include_router(accounts_router)
router.include_router(admin_router)
router.include_router(cart_router)
router.include_router(checkout_router)
router.include_router(contacts_router)
router.include_router(cms_router)
router.include_router(delivery_router)
router.include_router(notifications_router)
router.include_router(orders_router)
router.include_router(payments_router)
router.include_router(quiz_router)
router.include_router(support_router)

localized_router.include_router(categories_router)
localized_router.include_router(faqs_router)
localized_router.include_router(favorites_router)
localized_router.include_router(open_positions_router)
localized_router.include_router(products_router)
localized_router.include_router(subscriptions_router)
router.include_router(localized_router)


@router.get("/status", tags=["system"])
async def status() -> dict[str, str]:
    return {"status": "ok", "version": "v1"}
