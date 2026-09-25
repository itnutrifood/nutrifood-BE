"""Render order confirmations from a shared layout and language-specific copy."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from html import escape
from pathlib import Path
from string import Template
from typing import cast
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo

from backend.apps.common.enums import LanguageCode, PaymentMethod, PaymentStatus
from backend.apps.orders.schemas import OrderRead

ARMENIA_TIME = ZoneInfo("Asia/Yerevan")
LANGUAGE_TAG = {
    LanguageCode.HY_AM: "hy",
    LanguageCode.EN_US: "en",
    LanguageCode.RU_RU: "ru",
}


@dataclass(frozen=True)
class OrderEmail:
    subject: str
    plain_text: str
    html: str


@lru_cache
def _translation(language: LanguageCode) -> dict[str, object]:
    path = Path(__file__).parent / "locales" / f"{LANGUAGE_TAG[language]}.json"
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


@lru_cache
def _html_template() -> Template:
    return Template(Path(__file__).with_name("order_confirmation.html").read_text(encoding="utf-8"))


def _text(copy: dict[str, object], key: str) -> str:
    value = copy[key]
    if not isinstance(value, str):
        raise ValueError(f"Invalid order email translation: {key}")
    return value


def _money(amount: Decimal, currency: str) -> str:
    return f"{amount:,.2f} {currency}"


def _email_image_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme.lower() == "https"
            and parsed.hostname
            and not parsed.username
            and not parsed.password
        ):
            return url
    except ValueError:
        pass
    return None


def _date(value: datetime, copy: dict[str, object]) -> str:
    local = value.astimezone(ARMENIA_TIME)
    months = copy["months"]
    if (
        not isinstance(months, list)
        or len(months) != 12
        or not all(isinstance(month, str) for month in months)
    ):
        raise ValueError("Invalid order email month translations")
    return (
        f"{local.day:02d} {months[local.month - 1]} {local.year}, "
        f"{local:%H:%M} ({_text(copy, 'time_zone')})"
    )


def _address(order: OrderRead, copy: dict[str, object]) -> str:
    address = order.delivery_address
    parts = [
        address.street,
        address.building_number,
        *(
            f"{_text(copy, key)} {value}"
            for key, value in (
                ("entrance", address.entrance),
                ("floor", address.floor),
                ("apartment", address.apartment),
            )
            if value
        ),
        address.city,
        _text(copy, "armenia"),
    ]
    return ", ".join(parts)


def _payment(order: OrderRead, copy: dict[str, object]) -> str:
    method_key = {
        PaymentMethod.CASH_ON_DELIVERY: "cash_on_delivery",
        PaymentMethod.POS: "card_on_delivery",
    }[order.payment_method]
    status_key = {
        PaymentStatus.PAID: "paid",
        PaymentStatus.UNPAID: "payment_due",
        PaymentStatus.FAILED: "payment_failed",
        PaymentStatus.REFUNDED: "refunded",
    }[order.payment_status]
    return f"{_text(copy, method_key)} · {_text(copy, status_key)}"


def render_order_confirmation(
    order: OrderRead,
    language: LanguageCode = LanguageCode.EN_US,
    item_images: Mapping[UUID, str] | None = None,
) -> OrderEmail:
    """Build localized HTML and plain-text receipts from the saved order snapshot."""
    copy = _translation(language)

    def t(key: str) -> str:
        return _text(copy, key)

    subject = t("subject").format(number=order.order_number)
    greeting = (
        t("greeting_named").format(name=order.customer_first_name)
        if order.customer_first_name
        else t("greeting_generic")
    )
    address = _address(order, copy)
    payment = _payment(order, copy)
    placed_at = _date(order.created_at, copy)
    delivery_at = _date(order.requested_delivery_at, copy) if order.requested_delivery_at else None
    item_rows: list[str] = []
    item_lines: list[str] = []
    image_urls = item_images or {}
    for item in order.items:
        title = item.product_title.to_db()[language.value]
        unit_price = _money(item.unit_price, order.currency)
        line_total = _money(item.line_total, order.currency)
        item_lines.append(f"- {title} — {item.quantity} × {unit_price} = {line_total}")
        image_url = _email_image_url(image_urls.get(item.id))
        image_cell = (
            '<td width="76" style="padding:16px 12px 16px 0;'
            'border-bottom:1px solid #e5e7eb;vertical-align:top">'
            f'<img src="{escape(image_url)}" alt="{escape(title)}" '
            'width="64" height="64" style="display:block;width:64px;height:64px;'
            'border-radius:8px;object-fit:cover;background:#f0f7ed"></td>'
            if image_url
            else ""
        )
        item_rows.append(
            "<tr>"
            f"{image_cell}"
            '<td style="padding:16px 0;border-bottom:1px solid #e5e7eb;vertical-align:top">'
            f'<strong style="color:#0a0a0a;font-size:15px">{escape(title)}</strong>'
            f'<br><span style="color:#6a7282;font-size:13px">{item.quantity} × '
            f"{escape(unit_price)}</span></td>"
            '<td align="right" style="padding:16px 0;border-bottom:1px solid #e5e7eb;'
            'vertical-align:top;white-space:nowrap;color:#0a0a0a;font-weight:600">'
            f"{escape(line_total)}</td></tr>"
        )
    items_text = "\n".join(item_lines)
    delivery_text = f"{t('requested_delivery')}: {delivery_at}\n" if delivery_at else ""
    notes_text = f"{t('delivery_notes')}: {order.delivery_notes}\n" if order.delivery_notes else ""
    plain_text = (
        f"{greeting}\n\n{t('heading')}\n{t('intro')}\n\n"
        f"{t('order_number')}: #{order.order_number}\n"
        f"{t('placed')}: {placed_at}\n\n"
        f"{t('items')}\n{items_text}\n\n"
        f"{t('subtotal')}: {_money(order.subtotal, order.currency)}\n"
        f"{t('delivery')}: {_money(order.delivery_fee, order.currency)}\n"
        f"{t('total')}: {_money(order.total, order.currency)}\n\n"
        f"{t('deliver_to')}: {address}\n"
        f"{t('contact_phone')}: {order.contact_phone}\n"
        f"{delivery_text}{notes_text}"
        f"{t('payment')}: {payment}\n\n"
        f"{t('contact_help')} info@nutrifood.am.\n\n"
        f"NutriFood — {t('tagline')}"
    )
    delivery_html = (
        f'<tr><td style="padding:5px 0;color:#4a5565">'
        f"{escape(t('requested_delivery'))}</td>"
        f'<td align="right" style="padding:5px 0;color:#0a0a0a">'
        f"{escape(delivery_at)}</td></tr>"
        if delivery_at
        else ""
    )
    notes_html = (
        f'<p style="margin:16px 0 0;color:#4a5565;font-size:14px;line-height:22px">'
        f"<strong>{escape(t('delivery_notes'))}:</strong> "
        f"{escape(order.delivery_notes)}</p>"
        if order.delivery_notes
        else ""
    )
    label_keys = (
        "order_number",
        "placed",
        "items",
        "subtotal",
        "delivery",
        "total",
        "delivery_payment",
        "deliver_to",
        "contact_phone",
        "payment",
    )
    labels = {f"{key}_label": escape(t(key)) for key in label_keys}
    html = _html_template().substitute(
        language=LANGUAGE_TAG[language],
        subject=escape(subject),
        preheader=escape(
            t("preheader").format(
                number=order.order_number,
                total=_money(order.total, order.currency),
            )
        ),
        badge=escape(t("badge")),
        heading=escape(t("heading")),
        greeting=escape(greeting),
        intro=escape(t("intro")),
        number=escape(order.order_number),
        placed_at=escape(placed_at),
        rows="".join(item_rows),
        subtotal=escape(_money(order.subtotal, order.currency)),
        delivery_fee=escape(_money(order.delivery_fee, order.currency)),
        total=escape(_money(order.total, order.currency)),
        address=escape(address),
        phone=escape(order.contact_phone),
        delivery_html=delivery_html,
        payment=escape(payment),
        notes_html=notes_html,
        contact_help=escape(t("contact_help")),
        tagline=escape(t("tagline")),
        **labels,
    )
    return OrderEmail(
        subject=subject,
        plain_text=plain_text,
        html=html,
    )
