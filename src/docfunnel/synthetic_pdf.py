"""Seeded multi-page invoices and contracts rendered to PDF, with page-level ground truth.

The short receipts in :mod:`docfunnel.synthetic` test the LLM step; these documents
test everything before it (text layer, OCR decision, OCR, reading order) and later
retrieval over long documents. For every document the generator knows:

* the exact text printed on each page (reference for CER/WER);
* which pages are scanned images and how noisy they are (label for the OCR decision);
* each field's value, the page it is printed on, the quote as printed and its
  character span in that page's reference text (gold evidence for citations).

Rendering is pure Python: ReportLab (BSD) draws the digital PDF; the "scanned"
variant rasterises pages with pypdfium2, adds deterministic rotation, blur, low
contrast, sensor noise, speckle and JPEG artefacts (NumPy + Pillow), and rebuilds an
image-only page. Everything is seeded, so the same ``(n, seed)`` gives the same
ground truth.

Needs the ``synthetic`` extra (reportlab, pypdfium2, pillow, numpy).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import random
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from docfunnel.normalize import CENT
from docfunnel.schema import LineItem, ReceiptData
from docfunnel.synthetic import LOCALES, Locale, format_amount

if TYPE_CHECKING:
    from PIL.Image import Image
    from reportlab.pdfgen.canvas import Canvas

D = Decimal
Align = Literal["left", "right"]

DEFAULT_PDF_DIR = Path("data/synthetic/pdf")
MANIFEST_NAME = "manifest.jsonl"

MARGIN = 54.0
LEADING = 1.38
FONT_FAMILIES = (("Helvetica", "Helvetica-Bold"), ("Times-Roman", "Times-Bold"))


# ---- scan simulation ----------------------------------------------------------------


@dataclass(frozen=True)
class ScanNoise:
    dpi: int
    max_angle: float  # degrees, uniform in [-max, max]
    blur: float  # Gaussian blur radius in pixels
    contrast: float  # 1.0 = black ink stays black
    sigma: float  # Gaussian sensor noise (grey levels)
    speckle: float  # share of pixels flipped to black or white
    jpeg_quality: int


NOISE_LEVELS: dict[str, ScanNoise] = {
    "light": ScanNoise(
        dpi=200, max_angle=0.8, blur=0.5, contrast=0.92, sigma=8, speckle=0, jpeg_quality=70
    ),
    "heavy": ScanNoise(
        dpi=150, max_angle=2.0, blur=0.9, contrast=0.72, sigma=22, speckle=0.004, jpeg_quality=35
    ),
}


def simulate_scan(page: Any, noise: ScanNoise, seed: int) -> bytes:
    """Rasterise a PDF page and degrade it like a cheap office scan; returns JPEG bytes."""
    import numpy as np
    from PIL import Image, ImageFilter

    rng = np.random.default_rng(seed)
    image = page.render(scale=noise.dpi / 72, grayscale=True).to_pil().convert("L")
    angle = float(rng.uniform(-noise.max_angle, noise.max_angle))
    image = image.rotate(angle, resample=Image.Resampling.BICUBIC, fillcolor=255)
    if noise.blur:
        image = image.filter(ImageFilter.GaussianBlur(noise.blur))
    pixels = np.asarray(image, dtype=np.float32)
    pixels = 245 - (245 - pixels) * noise.contrast  # grey ink on slightly grey paper
    pixels += rng.normal(0.0, noise.sigma, pixels.shape)
    if noise.speckle:
        mask = rng.random(pixels.shape) < noise.speckle
        pixels[mask] = rng.choice(np.array([0.0, 255.0], dtype=np.float32), size=int(mask.sum()))
    out = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8), mode="L")
    buffer = io.BytesIO()
    out.save(buffer, format="JPEG", quality=noise.jpeg_quality)
    return buffer.getvalue()


# ---- layout primitives -----------------------------------------------------------------


@dataclass(frozen=True)
class _Seg:
    x: float
    text: str
    align: Align = "left"
    bold: bool = False


@dataclass(frozen=True)
class _Line:
    segs: tuple[_Seg, ...]
    size: float
    space_before: float = 0.0

    def height(self) -> float:
        return self.space_before + self.size * LEADING


@dataclass
class _Field:
    name: str
    value: Any
    quote: str


@dataclass
class _Group:
    """Lines laid out together; groups that carry fields never split across pages."""

    lines: list[_Line]
    fields: list[_Field] = field(default_factory=list)
    keep_together: bool = True


@dataclass
class _Placed:
    line: _Line
    y: float  # baseline, PDF coordinates (origin bottom-left)


@dataclass
class _PageLayout:
    lines: list[_Placed] = field(default_factory=list)
    background: bool = False


@dataclass(frozen=True)
class FieldTruth:
    name: str
    value: Any
    page: int
    quote: str
    char_span: tuple[int, int]


@dataclass(frozen=True)
class PageTruth:
    number: int
    scanned: bool
    noise: str | None
    stray_text: str | None
    background: bool
    text: str


@dataclass(frozen=True)
class DocTruth:
    id: str
    doc_type: str
    locale: str
    variant: str
    page_size: tuple[float, float]
    pages: list[PageTruth]
    fields: list[FieldTruth]
    label: dict[str, Any]

    @property
    def file(self) -> str:
        return f"{self.id}.pdf"

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "file": self.file,
            "doc_type": self.doc_type,
            "locale": self.locale,
            "variant": self.variant,
            "page_size": list(self.page_size),
            "pages": [
                {
                    "number": p.number,
                    "scanned": p.scanned,
                    "noise": p.noise,
                    "stray_text": p.stray_text,
                    "background": p.background,
                    "text": p.text,
                }
                for p in self.pages
            ],
            "fields": [
                {
                    "name": f.name,
                    "value": f.value,
                    "page": f.page,
                    "quote": f.quote,
                    "char_span": list(f.char_span),
                }
                for f in self.fields
            ],
            "label": self.label,
        }

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> DocTruth:
        return cls(
            id=raw["id"],
            doc_type=raw["doc_type"],
            locale=raw["locale"],
            variant=raw["variant"],
            page_size=(float(raw["page_size"][0]), float(raw["page_size"][1])),
            pages=[PageTruth(**p) for p in raw["pages"]],
            fields=[
                FieldTruth(
                    name=f["name"],
                    value=f["value"],
                    page=f["page"],
                    quote=f["quote"],
                    char_span=(f["char_span"][0], f["char_span"][1]),
                )
                for f in raw["fields"]
            ],
            label=raw["label"],
        )


def _line_text(line: _Line, fonts: tuple[str, str]) -> str:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    def left_edge(seg: _Seg) -> float:
        if seg.align == "left":
            return seg.x
        font = fonts[1] if seg.bold else fonts[0]
        return seg.x - stringWidth(seg.text, font, line.size)

    return " ".join(seg.text for seg in sorted(line.segs, key=left_edge) if seg.text)


class _Composer:
    """Flows groups of lines onto pages, repeating a header (e.g. a table head) if set."""

    def __init__(self, size: tuple[float, float], footer_space: float) -> None:
        self.width, self.height = size
        self.top = self.height - MARGIN
        self.bottom = MARGIN + footer_space
        self.pages: list[_PageLayout] = []
        self.repeat: list[_Line] = []
        self.placements: list[tuple[_Group, int, int, int]] = []  # group, page, first, last
        self._new_page()

    def _new_page(self) -> None:
        self.pages.append(_PageLayout())
        self.y = self.top
        for line in self.repeat:
            self._place(line)

    def _place(self, line: _Line) -> None:
        self.y -= line.height()
        self.pages[-1].lines.append(_Placed(line, self.y))

    def _fits(self, height: float) -> bool:
        return self.y - height >= self.bottom

    def add(self, group: _Group) -> None:
        total = sum(line.height() for line in group.lines)
        page_has_body = len(self.pages[-1].lines) > len(self.repeat)
        if group.keep_together and not self._fits(total) and page_has_body:
            self._new_page()
        first_page = len(self.pages) - 1
        first_index = len(self.pages[-1].lines)
        for line in group.lines:
            if not self._fits(line.height()):
                self._new_page()
            self._place(line)
        if group.fields:
            if len(self.pages) - 1 != first_page:  # pragma: no cover - keep_together guards it
                raise RuntimeError("a group with fields was split across pages")
            self.placements.append((group, first_page, first_index, len(self.pages[-1].lines)))


@dataclass
class _DocSpec:
    truth: DocTruth
    layouts: list[_PageLayout]
    fonts: tuple[str, str]
    footer_left: str
    seed: int


# What a document builder returns: laid-out pages, the label, and the footer text.
_Built = tuple[_Composer, dict[str, Any], str]


def _wrap(text: str, font: str, size: float, width: float) -> list[str]:
    from reportlab.lib.utils import simpleSplit

    lines: list[str] = simpleSplit(text, font, size, width)  # the stub leaves it unannotated
    return lines


def _paragraph(
    text: str, fonts: tuple[str, str], size: float, width: float, space_before: float = 0.0
) -> list[_Line]:
    lines = []
    for i, chunk in enumerate(_wrap(text, fonts[0], size, width)):
        lines.append(_Line((_Seg(MARGIN, chunk),), size, space_before if i == 0 else 0.0))
    return lines


def _single(text: str, size: float, *, bold: bool = False, space_before: float = 0.0) -> _Line:
    return _Line((_Seg(MARGIN, text, bold=bold),), size, space_before)


def _random_date(rng: random.Random) -> dt.date:
    return dt.date(2023, 1, 1) + dt.timedelta(days=rng.randint(0, 1000))


def _digits(rng: random.Random, n: int) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(n))


# ---- invoice ---------------------------------------------------------------------------

_TERMS = (
    "Payment is due within {days} days of the invoice date unless agreed otherwise in writing.",
    "Late payments may incur interest at the statutory rate from the due date until payment.",
    "Please quote the invoice number on all payments and correspondence.",
    "Goods remain the property of the supplier until the invoice has been paid in full.",
    "Any discrepancy must be reported within 14 days of receipt of this invoice.",
    "Services are provided under the framework agreement in force between the parties.",
    "Bank charges for international transfers are borne by the payer.",
    "This invoice was issued electronically and is valid without a signature.",
)


def _invoice(
    rng: random.Random, locale: Locale, fonts: tuple[str, str], size: tuple[float, float]
) -> _Built:
    width, _ = size
    body = rng.choice((9.0, 9.5, 10.0))
    labels = locale.labels
    vendor = rng.choice(locale.vendors)
    customer = rng.choice(locale.customers)
    tax_id = locale.tax_id(rng)
    when = _random_date(rng)
    date_text = when.strftime(rng.choice(locale.date_formats))
    number = f"{rng.choice(['INV', 'F', 'NF'])}-{when.year}-{_digits(rng, 5)}"
    catalog = list(locale.invoice_items + locale.pos_items)
    items: list[LineItem] = []
    for _ in range(rng.randint(12, 170)):
        base, unit = rng.choice(catalog)
        qty = D(rng.randint(1, 12))
        description = f"{base} #{rng.choice('ABCDEFGHJKLMNPRSTUVWXYZ')}{_digits(rng, 3)}"
        items.append(
            LineItem(
                description=description,
                quantity=qty,
                unit_price=unit,
                total=(qty * unit).quantize(CENT),
            )
        )
    subtotal = sum((item.total for item in items), D("0"))
    rate = rng.choice(locale.tax_rates)
    tax = (subtotal * rate).quantize(CENT)
    total = subtotal + tax
    payment_text, payment = rng.choice(locale.payments)
    payment_text = payment_text.format(d4=_digits(rng, 4))

    composer = _Composer(size, footer_space=24)
    add = composer.add
    right = width - MARGIN
    add(_Group([_single(labels["invoice"], body + 6, bold=True)]))
    add(
        _Group(
            [_single(vendor, body + 1, bold=True, space_before=6)],
            [_Field("vendor_name", vendor, vendor)],
        )
    )
    add(_Group([_single(rng.choice(locale.addresses), body)]))
    add(
        _Group(
            [_single(f"{labels['tax_id']} {tax_id}", body)],
            [_Field("vendor_tax_id", tax_id, tax_id)],
        )
    )
    add(
        _Group(
            [_single(f"{labels['invoice_no']} {number}", body, space_before=10)],
            [_Field("document_number", number, number)],
        )
    )
    add(
        _Group(
            [_single(f"{labels['invoice_date']} {date_text}", body)],
            [_Field("date", when.isoformat(), date_text)],
        )
    )
    add(
        _Group(
            [_single(f"{labels['bill_to']} {customer}", body)],
            [_Field("customer_name", customer, customer)],
        )
    )
    head_cells = [cell.strip() for cell in labels["header"].split("|")]
    columns = (right - 230, right - 110, right)
    header = _Line(
        (
            _Seg(MARGIN, head_cells[0], bold=True),
            *(_Seg(x, c, "right", bold=True) for x, c in zip(columns, head_cells[1:], strict=True)),
        ),
        body,
        space_before=10,
    )
    add(_Group([header]))
    composer.repeat = [header]
    for item in items:
        cells = (
            f"{(item.quantity or D(1)).normalize():f}",
            format_amount(item.unit_price or D(0), locale, symbol=False),
            format_amount(item.total, locale, symbol=False),
        )
        add(
            _Group(
                [
                    _Line(
                        (
                            _Seg(MARGIN, item.description),
                            *(_Seg(x, c, "right") for x, c in zip(columns, cells, strict=True)),
                        ),
                        body,
                    )
                ]
            )
        )
    composer.repeat = []

    def total_line(
        label: str, amount: str, name: str, value: Decimal, bold: bool = False
    ) -> _Group:
        line = _Line(
            (_Seg(right - 230, label, "right", bold), _Seg(right, amount, "right", bold)), body
        )
        return _Group([line], [_Field(name, str(value), amount)])

    totals = [
        total_line(labels["subtotal"], format_amount(subtotal, locale), "subtotal", subtotal),
        total_line(
            labels["tax"].format(rate=f"{(rate * 100).normalize():f}"),
            format_amount(tax, locale),
            "tax",
            tax,
        ),
        total_line(labels["invoice_total"], format_amount(total, locale), "total", total, True),
    ]
    totals[0].lines[0] = _Line(totals[0].lines[0].segs, body, space_before=8)
    # Keep the totals block together: merge into one group with three fields.
    add(
        _Group(
            [g.lines[0] for g in totals],
            [f for g in totals for f in g.fields],
        )
    )
    add(
        _Group(
            [_single(f"{labels['payment']} {payment_text}", body, space_before=8)],
            [_Field("payment_method", payment.value, payment_text)],
        )
    )
    if rng.random() < 0.5:
        add(_Group([_single("Terms and conditions", body, bold=True, space_before=14)]))
        days = rng.choice((14, 30, 45, 60))
        sentences = [s.format(days=days) for s in rng.sample(_TERMS, k=rng.randint(4, len(_TERMS)))]
        add(
            _Group(
                _paragraph(" ".join(sentences), fonts, body, width - 2 * MARGIN),
                keep_together=False,
            )
        )

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
    ).model_dump(mode="json")
    label["customer_name"] = customer
    return composer, label, f"{vendor} - {number}"


# ---- contract --------------------------------------------------------------------------

_LAWS = {
    "us": ("the State of Oregon", "the State of Texas", "the State of New York"),
    "uk": ("England and Wales",),
    "de": ("the Federal Republic of Germany",),
    "br": ("the Federative Republic of Brazil",),
}

_FILLER: dict[str, tuple[str, ...]] = {
    "Definitions": (
        'In this Agreement, "Confidential Information" means any information disclosed by one '
        "party to the other that is marked as confidential or would reasonably be understood to be "
        "confidential.",
        '"Deliverables" means all documents, software and materials provided by Provider in the '
        "course of the Services.",
        '"Business Day" means a day other than a Saturday, Sunday or public holiday.',
        "Headings are for convenience only and do not affect the interpretation of this Agreement.",
    ),
    "Services": (
        "Provider shall perform the services described in Schedule A (the Services) with "
        "reasonable skill, care and diligence.",
        "Provider shall assign suitably qualified personnel and may replace them with persons of "
        "equivalent experience.",
        "Client shall provide timely access to information, systems and staff reasonably required "
        "for the Services.",
        "Any change to the scope of the Services shall be agreed in writing through a change "
        "request signed by both parties.",
    ),
    "Confidentiality": (
        "Each party shall keep the Confidential Information of the other party secret and shall "
        "not disclose it to any third party.",
        "The obligations in this clause do not apply to information that is or becomes public "
        "other than through a breach of this Agreement.",
        "Confidential Information may be disclosed where required by law, provided that the other "
        "party is notified promptly.",
        "The obligations of confidentiality survive termination of this Agreement for five years.",
    ),
    "Intellectual Property": (
        "All intellectual property rights in the Deliverables shall vest in Client upon full "
        "payment of the fees.",
        "Provider retains ownership of its pre-existing materials and grants Client a "
        "non-exclusive licence to use them as part of the Deliverables.",
        "Neither party acquires any right in the trade marks of the other party.",
    ),
    "Data Protection": (
        "Each party shall comply with applicable data protection legislation in connection with "
        "this Agreement.",
        "Where Provider processes personal data on behalf of Client, it shall do so only on "
        "documented instructions from Client.",
        "Provider shall implement appropriate technical and organisational measures to protect "
        "personal data.",
    ),
    "Warranties": (
        "Each party warrants that it has full power and authority to enter into this Agreement.",
        "Provider warrants that the Services will be performed in a professional manner consistent "
        "with industry standards.",
        "Except as expressly stated, all other warranties are excluded to the extent permitted by "
        "law.",
    ),
    "Force Majeure": (
        "Neither party shall be liable for any delay caused by events beyond its reasonable "
        "control.",
        "The affected party shall notify the other party without delay and use reasonable efforts "
        "to mitigate the effects.",
        "If the event continues for more than sixty days, either party may terminate this "
        "Agreement in writing.",
    ),
    "Assignment": (
        "Neither party may assign or transfer this Agreement without the prior written consent of "
        "the other party.",
        "Provider may subcontract parts of the Services but remains responsible for the acts of "
        "its subcontractors.",
    ),
    "Notices": (
        "Notices under this Agreement shall be in writing and delivered by hand, courier or "
        "registered mail.",
        "Notices sent by email are valid only if confirmed by one of the methods above.",
    ),
    "Entire Agreement": (
        "This Agreement constitutes the entire agreement between the parties and supersedes all "
        "prior arrangements.",
        "No amendment to this Agreement is effective unless it is in writing and signed by both "
        "parties.",
    ),
    "Severability": (
        "If any provision of this Agreement is held invalid, the remaining provisions remain in "
        "full force and effect.",
        "The parties shall replace the invalid provision with a valid one that comes closest to "
        "its economic purpose.",
    ),
}

_SCHEDULE_TOPICS = (
    "data pipeline monitoring",
    "monthly cost report",
    "incident response",
    "access review",
    "backup verification",
    "dashboard maintenance",
    "model retraining",
    "data quality checks",
    "security patching",
    "capacity planning",
    "user support (business hours)",
    "release coordination",
)
_SCHEDULE_FREQUENCY = ("daily", "weekly", "monthly", "quarterly", "on request")

_FIELD_CLAUSES = ("Term", "Fees and Payment", "Termination", "Limitation of Liability")


def _contract(
    rng: random.Random, locale: Locale, fonts: tuple[str, str], size: tuple[float, float]
) -> _Built:
    width, _ = size
    text_width = width - 2 * MARGIN
    body = rng.choice((9.5, 10.0, 10.5))
    title = rng.choice(("SERVICES AGREEMENT", "MASTER SERVICES AGREEMENT", "CONSULTING AGREEMENT"))
    party_a = rng.choice(locale.vendors)
    party_b = rng.choice(locale.customers)
    when = _random_date(rng)
    date_text = when.strftime(rng.choice(locale.date_formats))
    term = rng.choice((6, 12, 18, 24, 36))
    fee = D(rng.randint(15, 400) * 50)
    fee_text = format_amount(fee, locale)
    notice = rng.choice((15, 30, 60, 90))
    cap = fee * rng.choice((3, 6, 12))
    cap_text = format_amount(cap, locale)
    law = rng.choice(_LAWS[locale.code])

    field_sentences = {
        "Term": (
            f"This Agreement commences on the Effective Date and shall remain in force for "
            f"{term} months unless terminated earlier in accordance with its terms.",
            _Field("term_months", term, f"{term} months"),
        ),
        "Fees and Payment": (
            f"Client shall pay Provider a monthly fee of {fee_text}, invoiced in arrears and "
            f"payable by bank transfer.",
            _Field("monthly_fee", str(fee), fee_text),
        ),
        "Termination": (
            f"Either party may terminate this Agreement for convenience by giving {notice} days' "
            f"written notice to the other party.",
            _Field("notice_days", notice, f"{notice} days' written notice"),
        ),
        "Limitation of Liability": (
            f"The total liability of either party under this Agreement shall not exceed "
            f"{cap_text} in aggregate.",
            _Field("liability_cap", str(cap), cap_text),
        ),
    }
    extra = {
        "Term": (
            "The parties may renew this Agreement for further periods by written agreement.",
            "Renewal terms are subject to the fees in force at the time of renewal.",
        ),
        "Fees and Payment": (
            "Invoices are payable within thirty days of receipt.",
            "Fees are exclusive of applicable taxes, which Client shall pay in addition.",
            "Provider may suspend the Services if undisputed invoices remain unpaid.",
        ),
        "Termination": (
            "Either party may terminate immediately if the other party commits a material breach "
            "that is not remedied within thirty days.",
            "On termination Client shall pay for all Services performed up to the termination "
            "date.",
        ),
        "Limitation of Liability": (
            "Neither party shall be liable for indirect or consequential loss, including loss of "
            "profit.",
            "Nothing in this Agreement limits liability for death or personal injury caused by "
            "negligence.",
        ),
    }
    fillers = rng.sample(sorted(_FILLER), k=rng.randint(5, len(_FILLER)))
    clause_names = [*fillers, *_FIELD_CLAUSES]
    rng.shuffle(clause_names)
    clause_names.append("Governing Law")

    composer = _Composer(size, footer_space=24)
    add = composer.add
    add(_Group([_single(title, body + 5, bold=True)]))
    intro = (
        f"This {title.title()} (the Agreement) is made on {date_text} (the Effective Date) "
        f"between {party_a}, {rng.choice(locale.addresses)} (Provider), and {party_b} (Client)."
    )
    add(
        _Group(
            _paragraph(intro, fonts, body, text_width, space_before=10),
            [
                _Field("effective_date", when.isoformat(), date_text),
                _Field("party_a", party_a, party_a),
                _Field("party_b", party_b, party_b),
            ],
        )
    )
    for number, name in enumerate(clause_names, start=1):
        add(_Group([_single(f"{number}. {name}", body, bold=True, space_before=10)]))
        if name == "Governing Law":
            sentences = [
                f"This Agreement shall be governed by and construed in accordance with the laws "
                f"of {law}.",
                "The parties submit to the exclusive jurisdiction of the competent courts.",
            ]
            fields = [_Field("governing_law", law, law)]
        elif name in field_sentences:
            sentence, fld = field_sentences[name]
            sentences = list(extra[name])
            rng.shuffle(sentences)
            sentences.insert(rng.randint(0, len(sentences)), sentence)
            fields = [fld]
        else:
            pool = _FILLER[name]
            sentences = rng.sample(pool, k=rng.randint(2, len(pool)))
            fields = []
        add(
            _Group(
                _paragraph(" ".join(sentences), fonts, body, text_width),
                fields,
                keep_together=bool(fields),
            )
        )
    add(_Group([_single("Schedule A - Services", body + 1, bold=True, space_before=16)]))
    for number in range(1, rng.randint(8, 70)):
        topic = rng.choice(_SCHEDULE_TOPICS)
        frequency = rng.choice(_SCHEDULE_FREQUENCY)
        add(_Group([_single(f"A.{number} {topic.capitalize()} - {frequency}", body)]))
    signature = [
        _single("Signed by the authorised representatives of the parties.", body, space_before=14),
        _Line(
            (_Seg(MARGIN, f"For {party_a}"), _Seg(MARGIN + text_width / 2, f"For {party_b}")),
            body,
            space_before=20,
        ),
        _Line(
            (_Seg(MARGIN, "Name and title"), _Seg(MARGIN + text_width / 2, "Name and title")),
            body,
            space_before=18,
        ),
    ]
    add(_Group(signature))
    label = {
        "party_a": party_a,
        "party_b": party_b,
        "effective_date": when.isoformat(),
        "term_months": term,
        "monthly_fee": str(fee),
        "currency": locale.currency,
        "notice_days": notice,
        "liability_cap": str(cap),
        "governing_law": law,
    }
    return composer, label, f"{title.title()} - {party_a} / {party_b}"


# ---- document assembly -------------------------------------------------------------------

_VARIANTS = ("digital", "scanned_light", "scanned_heavy", "mixed")
_VARIANT_WEIGHTS = (0.4, 0.2, 0.2, 0.2)


def _stray_text(rng: random.Random, page: int) -> str | None:
    roll = rng.random()
    if roll < 0.35:
        stamp = f"{_random_date(rng).isoformat()} {rng.randint(7, 19):02d}:{rng.randint(0, 59):02d}"
        return f"Scanned by OfficeScan 4000 on {stamp} - batch {_digits(rng, 4)} - page {page}"
    if roll < 0.55:
        return f"SCAN {_digits(rng, 4)}"
    return None


def _quote_span(text: str, quote: str, start: int, end: int) -> tuple[int, int]:
    pattern = r"\s+".join(re.escape(part) for part in quote.split())
    match = re.compile(pattern).search(text, start, end)
    if match is None:  # pragma: no cover - guarded by tests
        raise RuntimeError(f"quote {quote!r} not found on its page")
    return match.start(), match.end()


def _build_spec(index: int, doc_seed: int) -> _DocSpec:
    rng = random.Random(doc_seed)
    locale = LOCALES[rng.choice(sorted(LOCALES))]
    doc_type = rng.choices(("invoice", "contract"), weights=(0.6, 0.4))[0]
    variant = rng.choices(_VARIANTS, weights=_VARIANT_WEIGHTS)[0]
    fonts = rng.choice(FONT_FAMILIES)
    size = (612.0, 792.0) if locale.code == "us" else (595.2756, 841.8898)
    builder = _invoice if doc_type == "invoice" else _contract
    composer, label, footer_left = builder(rng, locale, fonts, size)
    layouts = composer.pages
    n_pages = len(layouts)

    background = variant in {"digital", "mixed"} and rng.random() < 0.25
    scanned: dict[int, str] = {}
    if variant.startswith("scanned_"):
        level = variant.removeprefix("scanned_")
        scanned = dict.fromkeys(range(n_pages), level)
    elif variant == "mixed":
        scanned = {rng.randrange(n_pages): rng.choice(("light", "heavy"))}
    stray = {i: _stray_text(rng, i + 1) for i in sorted(scanned)}

    page_texts = []
    line_offsets: list[list[int]] = []
    for number, layout in enumerate(layouts, start=1):
        layout.background = background
        texts = [_line_text(p.line, fonts) for p in layout.lines]
        texts.append(f"{footer_left} Page {number} of {n_pages}")
        if stray.get(number - 1):
            texts.append(stray[number - 1] or "")
        offsets, position = [], 0
        for text in texts:
            offsets.append(position)
            position += len(text) + 1
        offsets.append(position)
        page_texts.append("\n".join(texts))
        line_offsets.append(offsets)

    fields: list[FieldTruth] = []
    for group, page_index, first, last in composer.placements:
        text = page_texts[page_index]
        start, end = line_offsets[page_index][first], line_offsets[page_index][last]
        for fld in group.fields:
            span = _quote_span(text, fld.quote, start, end)
            fields.append(FieldTruth(fld.name, fld.value, page_index + 1, fld.quote, span))

    truth = DocTruth(
        id=f"pdf-{index:03d}",
        doc_type=doc_type,
        locale=locale.code,
        variant=variant,
        page_size=size,
        pages=[
            PageTruth(
                number=i + 1,
                scanned=i in scanned,
                noise=scanned.get(i),
                stray_text=stray.get(i),
                background=background,
                text=page_texts[i],
            )
            for i in range(n_pages)
        ],
        fields=fields,
        label=label,
    )
    return _DocSpec(truth, layouts, fonts, footer_left, doc_seed)


def generate_specs(n: int = 50, seed: int = 11) -> Iterator[_DocSpec]:
    master = random.Random(seed)
    for index in range(1, n + 1):
        yield _build_spec(index, master.randrange(2**32))


def generate_truths(n: int = 50, seed: int = 11) -> list[DocTruth]:
    return [spec.truth for spec in generate_specs(n, seed)]


# ---- rendering ---------------------------------------------------------------------------


def _background_image(width: float, height: float) -> Image:
    """A light letterhead band and watermark box, drawn as one full-page image."""
    from PIL import Image, ImageDraw

    w, h = round(width / 2), round(height / 2)
    image = Image.new("L", (w, h), 252)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, w, 18), fill=228)
    draw.rectangle((w // 4, h // 3, 3 * w // 4, 2 * h // 3), outline=238, width=6)
    return image


def _draw_page(canvas: Canvas, spec: _DocSpec, index: int) -> None:
    from reportlab.lib.utils import ImageReader

    width, height = spec.truth.page_size
    layout = spec.layouts[index]
    if layout.background:
        canvas.drawImage(ImageReader(_background_image(width, height)), 0, 0, width, height)
    regular, bold = spec.fonts
    for placed in layout.lines:
        for seg in placed.line.segs:
            canvas.setFont(bold if seg.bold else regular, placed.line.size)
            if seg.align == "right":
                canvas.drawRightString(seg.x, placed.y, seg.text)
            else:
                canvas.drawString(seg.x, placed.y, seg.text)
    footer = spec.truth.pages[index].text.split("\n")[len(layout.lines)]
    page_label = footer.removeprefix(spec.footer_left).strip()
    canvas.setFont(regular, 8)
    canvas.drawString(MARGIN, MARGIN - 8, spec.footer_left)
    canvas.drawRightString(width - MARGIN, MARGIN - 8, page_label)


def _canvas(buffer: io.BytesIO, spec: _DocSpec) -> Canvas:
    from reportlab.pdfgen.canvas import Canvas

    canvas = Canvas(buffer, pagesize=spec.truth.page_size, invariant=1, pageCompression=1)
    canvas.setTitle(spec.truth.id)
    canvas.setCreator("docfunnel synthetic generator")
    return canvas


def render_pdf(spec: _DocSpec) -> bytes:
    """Draw the digital PDF, then replace the scanned pages by noisy page images."""
    import pypdfium2 as pdfium
    from reportlab.lib.utils import ImageReader

    buffer = io.BytesIO()
    canvas = _canvas(buffer, spec)
    for index in range(len(spec.layouts)):
        _draw_page(canvas, spec, index)
        canvas.showPage()
    canvas.save()
    digital = buffer.getvalue()
    if not any(page.scanned for page in spec.truth.pages):
        return digital

    width, height = spec.truth.page_size
    source = pdfium.PdfDocument(digital)
    try:
        out = io.BytesIO()
        canvas = _canvas(out, spec)
        for index, page_truth in enumerate(spec.truth.pages):
            if page_truth.scanned and page_truth.noise:
                jpeg = simulate_scan(
                    source[index], NOISE_LEVELS[page_truth.noise], seed=spec.seed + index
                )
                canvas.drawImage(ImageReader(io.BytesIO(jpeg)), 0, 0, width, height)
                if page_truth.stray_text:
                    canvas.setFont("Helvetica", 6)
                    canvas.drawString(MARGIN, 14, page_truth.stray_text)
            else:
                _draw_page(canvas, spec, index)
            canvas.showPage()
        canvas.save()
        return out.getvalue()
    finally:
        source.close()


def write_pdf_dataset(out_dir: Path, n: int = 50, seed: int = 11) -> list[DocTruth]:
    """Write ``{id}.pdf`` files and ``manifest.jsonl`` (ground truth) into ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    truths = []
    with (out_dir / MANIFEST_NAME).open("w", encoding="utf-8") as manifest:
        for spec in generate_specs(n, seed):
            (out_dir / spec.truth.file).write_bytes(render_pdf(spec))
            manifest.write(json.dumps(spec.truth.to_json(), ensure_ascii=False) + "\n")
            truths.append(spec.truth)
    return truths


def load_manifest(directory: Path) -> list[DocTruth]:
    path = directory / MANIFEST_NAME
    with path.open(encoding="utf-8") as handle:
        return [DocTruth.from_json(json.loads(line)) for line in handle if line.strip()]


def manifest_sha256(directory: Path) -> str:
    return hashlib.sha256((directory / MANIFEST_NAME).read_bytes()).hexdigest()
