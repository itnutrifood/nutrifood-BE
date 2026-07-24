import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID

import asyncpg

from backend.apps.common.db import json_object, rows_affected
from backend.apps.common.enums import EmploymentType, OpenPositionStatus
from backend.apps.common.pagination import page_count, page_offset
from backend.apps.open_positions.exceptions import OpenPositionNotFoundError
from backend.apps.open_positions.schemas import (
    LocalizedDescription,
    LocalizedShortText,
    OpenPositionCreate,
    OpenPositionListResponse,
    OpenPositionRead,
    OpenPositionUpdate,
)

OPEN_POSITION_COLUMNS = """
    id,
    title,
    employment_type::text AS employment_type,
    description,
    position,
    city,
    status::text AS status,
    created_at,
    updated_at
"""


def open_position_from_record(record: Mapping[str, object]) -> OpenPositionRead:
    return OpenPositionRead(
        id=cast(UUID, record["id"]),
        title=LocalizedShortText.model_validate(json_object(record["title"])),
        employment_type=EmploymentType(cast(str, record["employment_type"])),
        description=LocalizedDescription.model_validate(json_object(record["description"])),
        position=LocalizedShortText.model_validate(json_object(record["position"])),
        city=LocalizedShortText.model_validate(json_object(record["city"])),
        status=OpenPositionStatus(cast(str, record["status"])),
        created_at=cast(datetime, record["created_at"]),
        updated_at=cast(datetime, record["updated_at"]),
    )


async def create_open_position(
    pool: asyncpg.Pool,
    payload: OpenPositionCreate,
) -> OpenPositionRead:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            INSERT INTO open_positions
                (title, employment_type, description, position, city, status)
            VALUES ($1::jsonb, $2::employment_type, $3::jsonb, $4::jsonb, $5::jsonb,
                    $6::open_position_status)
            RETURNING {OPEN_POSITION_COLUMNS}
            """,
            json.dumps(payload.title.to_db()),
            payload.employment_type.value,
            json.dumps(payload.description.to_db()),
            json.dumps(payload.position.to_db()),
            json.dumps(payload.city.to_db()),
            payload.status.value,
        ),
    )
    if row is None:
        raise RuntimeError("Open position insert did not return a row")
    return open_position_from_record(row)


async def get_open_position(pool: asyncpg.Pool, open_position_id: UUID) -> OpenPositionRead:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"SELECT {OPEN_POSITION_COLUMNS} FROM open_positions WHERE id = $1",
            open_position_id,
        ),
    )
    if row is None:
        raise OpenPositionNotFoundError
    return open_position_from_record(row)


async def list_open_positions(
    pool: asyncpg.Pool,
    status_filter: OpenPositionStatus | None,
    employment_type_filter: EmploymentType | None,
    page: int,
    limit: int,
) -> OpenPositionListResponse:
    params: list[object] = []
    conditions: list[str] = []
    if status_filter is not None:
        params.append(status_filter.value)
        conditions.append(f"status = ${len(params)}::open_position_status")
    if employment_type_filter is not None:
        params.append(employment_type_filter.value)
        conditions.append(f"employment_type = ${len(params)}::employment_type")
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    count_row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"SELECT count(*) AS total FROM open_positions {where_clause}", *params
        ),
    )
    total = cast(int, count_row["total"]) if count_row is not None else 0
    params.extend([limit, page_offset(page, limit)])
    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            f"""
            SELECT {OPEN_POSITION_COLUMNS}
            FROM open_positions
            {where_clause}
            ORDER BY created_at DESC, id
            LIMIT ${len(params) - 1} OFFSET ${len(params)}
            """,
            *params,
        ),
    )
    return OpenPositionListResponse(
        items=[open_position_from_record(row) for row in rows],
        total=total,
        page=page,
        limit=limit,
        total_pages=page_count(total, limit),
    )


async def update_open_position(
    pool: asyncpg.Pool,
    open_position_id: UUID,
    payload: OpenPositionUpdate,
) -> OpenPositionRead:
    assignments: list[str] = []
    params: list[Any] = []
    localized_fields: dict[str, LocalizedShortText | LocalizedDescription | None] = {
        "title": payload.title,
        "description": payload.description,
        "position": payload.position,
        "city": payload.city,
    }
    for field_name, value in localized_fields.items():
        if field_name in payload.model_fields_set:
            params.append(
                json.dumps(cast(LocalizedShortText | LocalizedDescription, value).to_db())
            )
            assignments.append(f"{field_name} = ${len(params)}::jsonb")
    if "employment_type" in payload.model_fields_set:
        params.append(cast(EmploymentType, payload.employment_type).value)
        assignments.append(f"employment_type = ${len(params)}::employment_type")
    if "status" in payload.model_fields_set:
        params.append(cast(OpenPositionStatus, payload.status).value)
        assignments.append(f"status = ${len(params)}::open_position_status")
    params.append(open_position_id)
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            UPDATE open_positions SET {", ".join(assignments)}
            WHERE id = ${len(params)} RETURNING {OPEN_POSITION_COLUMNS}
            """,
            *params,
        ),
    )
    if row is None:
        raise OpenPositionNotFoundError
    return open_position_from_record(row)


async def delete_open_position(pool: asyncpg.Pool, open_position_id: UUID) -> None:
    result = cast(
        str, await pool.execute("DELETE FROM open_positions WHERE id = $1", open_position_id)
    )
    if rows_affected(result) == 0:
        raise OpenPositionNotFoundError


async def list_active_open_positions(
    pool: asyncpg.Pool,
    employment_type: EmploymentType | None,
    limit: int,
    cursor: tuple[datetime, UUID] | None,
) -> list[OpenPositionRead]:
    params: list[object] = [OpenPositionStatus.ACTIVE.value]
    conditions = ["status = $1::open_position_status"]
    if employment_type is not None:
        params.append(employment_type.value)
        conditions.append(f"employment_type = ${len(params)}::employment_type")
    if cursor is not None:
        params.extend(cursor)
        conditions.append(f"(created_at, id) < (${len(params) - 1}, ${len(params)})")
    params.append(limit + 1)
    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            f"""
            SELECT {OPEN_POSITION_COLUMNS}
            FROM open_positions
            WHERE {" AND ".join(conditions)}
            ORDER BY created_at DESC, id DESC
            LIMIT ${len(params)}
            """,
            *params,
        ),
    )
    return [open_position_from_record(row) for row in rows]


async def get_active_open_position(
    pool: asyncpg.Pool,
    open_position_id: UUID,
) -> OpenPositionRead:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            SELECT {OPEN_POSITION_COLUMNS}
            FROM open_positions
            WHERE id = $1 AND status = $2::open_position_status
            """,
            open_position_id,
            OpenPositionStatus.ACTIVE.value,
        ),
    )
    if row is None:
        raise OpenPositionNotFoundError
    return open_position_from_record(row)
