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


def _email_language_tag(tag: str) -> LanguageCode | None:
    base = tag.strip().lower().replace("_", "-").split("-", 1)[0]
    return {
        "hy": LanguageCode.HY_AM,
        "en": LanguageCode.EN_US,
        "ru": LanguageCode.RU_RU,
    }.get(base)


def resolve_email_language(
    selected_locale: str | None,
    accept_language: str | None,
) -> LanguageCode:
    """Use the selected site locale, then the best supported Accept-Language value."""
    if selected_locale is not None:
        selected = _email_language_tag(selected_locale)
        if selected is None:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Unsupported email locale",
            )
        return selected

    best_language = LanguageCode.EN_US
    best_quality = 0.0
    for preference in (accept_language or "").split(","):
        tag, *parameters = preference.split(";")
        language = _email_language_tag(tag)
        if language is None:
            continue
        quality = 1.0
        for parameter in parameters:
            if parameter.strip().lower().startswith("q="):
                try:
                    quality = float(parameter.strip()[2:])
                except ValueError:
                    quality = 0.0
        if 0 < quality <= 1 and quality > best_quality:
            best_language = language
            best_quality = quality
    return best_language


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
