"""Synthetic receipt/invoice generator with exact ground-truth labels.

Why synthetic: no licensing questions, no PII, no network downloads, and the labels
are correct by construction. The generator deliberately covers the things that
break real extractors:

* four locales (US, UK, DE, BR) with different currencies, decimal separators,
  date orders and tax vocabularies;
* three layouts (thermal POS receipt, tabular invoice, minimal ticket);
* fields that are legitimately absent (no tax ID, no document number, no tax line),
  which is what makes hallucination measurable;
* distractors (a "Bill to" customer next to the vendor);
* OCR-style noise (``T0TAL``, ``1O,5O``) where the true value is no longer
  fully recoverable from the text;
* misprinted documents whose totals do not add up and therefore *should* be
  routed to a human even when extraction is perfect.

Output is deterministic for a given seed.
"""

from __future__ import annotations

import datetime as dt
import json
import random
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from docfunnel.datasets.locales import LOCALES, Locale, digits, format_amount
from docfunnel.extract.normalize import CENT
from docfunnel.extract.schema import LineItem, PaymentMethod, ReceiptData

D = Decimal


def _format_rate(rate: Decimal, locale: Locale) -> str:
    text = f"{(rate * 100).normalize():f}"
    return text.replace(".", ",") if locale.decimal_comma else text


def _qty(quantity: Decimal | None) -> str:
    return f"{(quantity or D(1)).normalize():f}"


def _row(left: str, right: str, width: int = 40) -> str:
    gap = max(2, width - len(left) - len(right))
    return f"{left}{' ' * gap}{right}"


@dataclass
class _Draft:
    lines: list[str]
    label: ReceiptData


def _random_date(rng: random.Random) -> dt.date:
    start = dt.date(2023, 1, 1)
    return start + dt.timedelta(days=rng.randint(0, 1000))


def _payment(rng: random.Random, locale: Locale) -> tuple[str, PaymentMethod]:
    template, method = rng.choice(locale.payments)
    return template.format(d4=digits(rng, 4)), method


def _items(
    rng: random.Random, catalog: tuple[tuple[str, Decimal], ...], max_qty: int, count: int
) -> list[LineItem]:
    chosen = rng.sample(catalog, k=min(count, len(catalog)))
    items = []
    for description, unit in chosen:
        qty = D(rng.randint(1, max_qty))
        items.append(
            LineItem(
                description=description,
                quantity=qty,
                unit_price=unit,
                total=(qty * unit).quantize(CENT),
            )
        )
    return items


def _pos_receipt(rng: random.Random, locale: Locale) -> _Draft:
    labels = locale.labels
    vendor = rng.choice(locale.vendors)
    items = _items(rng, locale.pos_items, max_qty=3, count=rng.randint(1, 5))
    subtotal = sum((i.total for i in items), D("0"))
    has_tax = rng.random() < locale.pos_tax_probability
    rate = rng.choice(locale.tax_rates)
    tax = (subtotal * rate).quantize(CENT) if has_tax else None
    total = subtotal + (tax or D("0"))
    when = _random_date(rng)
    show_tax_id = rng.random() < (0.4 if locale.code == "us" else 0.8)
    tax_id = locale.tax_id(rng) if show_tax_id else None
    number = digits(rng, 6) if rng.random() < 0.7 else None
    payment_text, payment = _payment(rng, locale) if rng.random() < 0.8 else (None, None)
    show_subtotal = has_tax or rng.random() < 0.5

    lines = [vendor.upper().center(40).rstrip(), rng.choice(locale.addresses).center(40).rstrip()]
    if tax_id:
        lines.append(f"{labels['tax_id']} {tax_id}")
    if number:
        lines.append(f"{labels['receipt_no']} {number}")
    lines.append(
        f"{labels['date']} {when.strftime(rng.choice(locale.date_formats))} "
        f"{rng.randint(7, 21):02d}:{rng.randint(0, 59):02d}"
    )
    lines.append("-" * 40)
    for item in items:
        qty = item.quantity or D(1)
        left = f"{_qty(qty)} x {item.description}" if qty > 1 else item.description
        lines.append(_row(left, format_amount(item.total, locale)))
    lines.append("-" * 40)
    if show_subtotal:
        lines.append(_row(labels["subtotal"], format_amount(subtotal, locale)))
    if tax is not None:
        lines.append(
            _row(labels["tax"].format(rate=_format_rate(rate, locale)), format_amount(tax, locale))
        )
    lines.append(_row(labels["total"], format_amount(total, locale)))
    if payment_text:
        lines.append(f"{labels['payment']} {payment_text}")
    lines.append("")
    lines.append(labels["thanks"].center(40).rstrip())

    label = ReceiptData(
        vendor_name=vendor,
        vendor_tax_id=tax_id,
        document_number=number,
        date=when,
        currency=locale.currency,
        subtotal=subtotal if show_subtotal else None,
        tax=tax,
        total=total,
        payment_method=payment,
        line_items=items,
    )
    return _Draft(lines, label)


def _invoice(rng: random.Random, locale: Locale) -> _Draft:
    labels = locale.labels
    vendor = rng.choice(locale.vendors)
    items = _items(rng, locale.invoice_items, max_qty=12, count=rng.randint(1, 3))
    subtotal = sum((i.total for i in items), D("0"))
    rate = rng.choice(locale.tax_rates)
    tax = (subtotal * rate).quantize(CENT)
    total = subtotal + tax
    when = _random_date(rng)
    tax_id = locale.tax_id(rng)
    number = f"{rng.choice(['INV', 'F', 'NF'])}-{when.year}-{digits(rng, 4)}"
    payment_text, payment = _payment(rng, locale) if rng.random() < 0.6 else (None, None)

    lines = [
        labels["invoice"],
        "",
        vendor,
        rng.choice(locale.addresses),
        f"{labels['tax_id']} {tax_id}",
        "",
        f"{labels['invoice_no']} {number}",
        f"{labels['invoice_date']} {when.strftime(rng.choice(locale.date_formats))}",
        f"{labels['bill_to']} {rng.choice(locale.customers)}",
        "",
        labels["header"],
    ]
    for item in items:
        lines.append(
            " | ".join(
                [
                    item.description,
                    _qty(item.quantity),
                    format_amount(item.unit_price or D(0), locale, symbol=False),
                    format_amount(item.total, locale, symbol=False),
                ]
            )
        )
    lines += [
        "",
        f"{labels['subtotal']}: {format_amount(subtotal, locale)}",
        f"{labels['tax'].format(rate=_format_rate(rate, locale))}: {format_amount(tax, locale)}",
        f"{labels['invoice_total']}: {format_amount(total, locale, symbol=False)}",
    ]
    if payment_text:
        lines.append(f"{labels['payment']} {payment_text}")

    label = ReceiptData(
        vendor_name=vendor,
        vendor_tax_id=tax_id,
        document_number=number,
        date=when,
        currency=locale.currency,
        subtotal=subtotal,
        tax=tax,
        total=total,
        payment_method=payment,
        line_items=items,
    )
    return _Draft(lines, label)


def _minimal(rng: random.Random, locale: Locale) -> _Draft:
    vendor = rng.choice(locale.vendors)
    when = _random_date(rng)
    total = D(rng.randint(150, 6000)) / 100
    lines = [
        vendor,
        when.strftime(rng.choice(locale.date_formats)),
        _row(locale.labels["total"], format_amount(total, locale), width=28),
        locale.labels["thanks"],
    ]
    label = ReceiptData(vendor_name=vendor, date=when, currency=locale.currency, total=total)
    return _Draft(lines, label)


_OCR_LETTERS = {"O": "0", "o": "0", "l": "1", "I": "1", "S": "5", "B": "8", "e": "c", "a": "o"}
_OCR_DIGITS = {"0": "O", "1": "l", "5": "S", "8": "B"}


def ocr_noise(text: str, rng: random.Random, rate: float = 0.05) -> str:
    """Corrupt text the way cheap OCR does: look-alike characters and lost column gaps."""
    out_lines = []
    for line in text.splitlines():
        chars = []
        for ch in line:
            if ch in _OCR_LETTERS and rng.random() < rate:
                chars.append(_OCR_LETTERS[ch])
            elif ch in _OCR_DIGITS and rng.random() < rate / 3:
                chars.append(_OCR_DIGITS[ch])
            else:
                chars.append(ch)
        noisy = "".join(chars)
        if rng.random() < 0.15:
            noisy = " ".join(noisy.split())  # column alignment lost
        out_lines.append(noisy)
    return "\n".join(out_lines)


def _misprint_total(draft: _Draft, rng: random.Random, locale: Locale) -> None:
    """Make the printed total disagree with subtotal + tax (a real-world misprint)."""
    label = draft.label
    assert label.total is not None
    delta = D(rng.choice([-1, 1]) * rng.randint(100, 900)) / 100
    wrong = label.total + delta
    old = format_amount(label.total, locale)
    new = format_amount(wrong, locale)
    for i in range(len(draft.lines) - 1, -1, -1):
        if draft.lines[i].endswith(old):
            draft.lines[i] = _row(draft.lines[i][: -len(old)].rstrip(), new)
            break
    draft.label = label.model_copy(update={"total": wrong})


@dataclass(frozen=True)
class Sample:
    id: str
    layout: str
    locale: str
    variant: str
    text: str
    label: ReceiptData
    expected_review: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "layout": self.layout,
            "locale": self.locale,
            "variant": self.variant,
            "expected_review": self.expected_review,
            "text": self.text,
            "label": self.label.model_dump(mode="json"),
        }


_LAYOUTS = {"pos": _pos_receipt, "invoice": _invoice, "minimal": _minimal}


def generate(n: int = 60, seed: int = 7) -> Iterator[Sample]:
    rng = random.Random(seed)
    for index in range(1, n + 1):
        locale = LOCALES[rng.choice(sorted(LOCALES))]
        layout = rng.choices(["pos", "invoice", "minimal"], weights=[0.55, 0.3, 0.15])[0]
        draft = _LAYOUTS[layout](rng, locale)
        variant = "clean"
        roll = rng.random()
        if layout == "pos" and roll < 0.12:
            _misprint_total(draft, rng, locale)
            variant = "misprinted"
        text = "\n".join(draft.lines)
        if layout != "minimal" and variant == "clean" and roll > 0.8:
            text = ocr_noise(text, rng)
            variant = "ocr_noise"
        yield Sample(
            id=f"doc-{index:03d}",
            layout=layout,
            locale=locale.code,
            variant=variant,
            text=text,
            label=draft.label,
            expected_review=variant == "misprinted",
        )


def write_dataset(path: Path, n: int = 60, seed: int = 7) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for sample in generate(n=n, seed=seed):
            handle.write(json.dumps(sample.to_json(), ensure_ascii=False) + "\n")
            count += 1
    return count
