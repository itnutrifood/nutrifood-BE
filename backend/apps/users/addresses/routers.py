from uuid import UUID

from fastapi import APIRouter, Response
from fastapi import status as http_status

from backend.apps.accounts.dependencies import RequireAuth
from backend.apps.users.addresses.schemas import AddressCreate, AddressRead, AddressUpdate
from backend.apps.users.addresses.service import (
    create_address,
    delete_address,
    get_address,
    list_addresses,
    update_address,
)
from backend.config.database import DbPool

router = APIRouter(prefix="/addresses", tags=["addresses"])


@router.post("", response_model=AddressRead, status_code=http_status.HTTP_201_CREATED)
async def create_user_address(
    payload: AddressCreate,
    current_user: RequireAuth,
    pool: DbPool,
) -> AddressRead:
    return await create_address(pool, current_user.id, payload)


@router.get("", response_model=list[AddressRead])
async def list_user_addresses(
    current_user: RequireAuth,
    pool: DbPool,
) -> list[AddressRead]:
    return await list_addresses(pool, current_user.id)


@router.get("/{address_id}", response_model=AddressRead)
async def read_user_address(
    address_id: UUID,
    current_user: RequireAuth,
    pool: DbPool,
) -> AddressRead:
    return await get_address(pool, current_user.id, address_id)


@router.patch("/{address_id}", response_model=AddressRead)
async def update_user_address(
    address_id: UUID,
    payload: AddressUpdate,
    current_user: RequireAuth,
    pool: DbPool,
) -> AddressRead:
    return await update_address(pool, current_user.id, address_id, payload)


@router.delete("/{address_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_user_address(
    address_id: UUID,
    current_user: RequireAuth,
    pool: DbPool,
) -> Response:
    await delete_address(pool, current_user.id, address_id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
