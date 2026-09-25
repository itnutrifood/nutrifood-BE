from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi import status as http_status

from backend.apps.accounts.dependencies import RequireAuth
from backend.apps.checkout.service import place_order
from backend.apps.common.localization import resolve_email_language
from backend.apps.orders.schemas import OrderRead, PlaceOrderRequest
from backend.config.database import DbPool
from backend.config.settings import Settings, get_settings

router = APIRouter(prefix="/checkout", tags=["checkout"])


@router.post("/orders", response_model=OrderRead, status_code=http_status.HTTP_201_CREATED)
async def place_cart_order(
    payload: PlaceOrderRequest,
    current_user: RequireAuth,
    pool: DbPool,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=255,
            pattern=r"^[\x21-\x7e]+$",
        ),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
    selected_locale: Annotated[
        str | None,
        Header(alias="X-Locale", description="Selected site language: hy, en, or ru"),
    ] = None,
    accept_language: Annotated[str | None, Header(alias="Accept-Language")] = None,
) -> OrderRead:
    return await place_order(
        pool,
        current_user.id,
        payload,
        idempotency_key,
        settings.catalog_currency,
        resolve_email_language(selected_locale, accept_language),
    )
