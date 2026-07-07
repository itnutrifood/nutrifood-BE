from collections.abc import Mapping, Sequence
from typing import Annotated

from fastapi import Depends, HTTPException, Path
from fastapi import status as http_status

from backend.apps.common.enums import LanguageCode


def get_locale_from_path(
    locale: Annotated[str, Path(min_length=2, max_length=5)],
) -> LanguageCode:
    try:
        return LanguageCode(locale.upper())
    except ValueError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Unsupported locale",
        ) from exc


LocaleFromPath = Annotated[LanguageCode, Depends(get_locale_from_path)]


def localized_text(
    values: Mapping[str, str],
    language: LanguageCode,
) -> str | None:
    return values.get(language.value)


def required_localized_text(
    values: Mapping[str, str],
    language: LanguageCode,
) -> str:
    value = localized_text(values, language)
    if value is None:
        raise ValueError("Expected at least one localized value")
    return value


def localized_items(
    values: Mapping[str, Sequence[str]],
    language: LanguageCode,
) -> list[str]:
    return list(values.get(language.value, ()))
