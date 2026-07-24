import json
from collections.abc import Mapping, Sequence
from typing import cast


def json_object(value: object) -> dict[str, object]:
    if isinstance(value, str):
        loaded_value = json.loads(value)
    elif isinstance(value, Mapping):
        loaded_value = dict(value)
    else:
        raise ValueError("Expected a JSON object")

    if not isinstance(loaded_value, dict):
        raise ValueError("Expected a JSON object")

    return cast(dict[str, object], loaded_value)


def json_array(value: object) -> list[object]:
    if isinstance(value, str):
        loaded_value = json.loads(value)
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        loaded_value = list(value)
    else:
        raise ValueError("Expected a JSON array")

    if not isinstance(loaded_value, list):
        raise ValueError("Expected a JSON array")

    return cast(list[object], loaded_value)


def rows_affected(command_status: str) -> int:
    try:
        return int(command_status.rsplit(maxsplit=1)[-1])
    except (IndexError, ValueError):
        return 0
