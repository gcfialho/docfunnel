"""CPU OCR engines behind one small interface.

* ``rapidocr`` (extra ``ocr``): PP-OCR detection + recognition models run by ONNX
  Runtime. No torch; the models ship inside the wheel. Default engine.
* ``tesseract`` (extra ``tesseract`` plus the ``tesseract`` binary): the classic
  baseline.

Engines return text lines with pixel boxes. :func:`lines_to_blocks` turns them into
reading-order rows (deskewed, so the cells of one table row stay on one line) and
then into :class:`~docfunnel.parse.model.Block` objects in PDF points.
"""

from __future__ import annotations

import importlib.util
import math
import shutil
import statistics
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from docfunnel.parse.model import Block


@dataclass(frozen=True)
class OcrLine:
    text: str
    box: tuple[float, float, float, float]  # axis-aligned, pixels, top-left origin
    height: float  # text height in pixels, measured perpendicular to the baseline
    confidence: float | None = None
    angle: float | None = None  # baseline skew in radians, when the engine can tell


class OcrEngine(Protocol):
    name: str
    version: str

    def recognize(self, image: Any) -> list[OcrLine]: ...


class OcrUnavailableError(RuntimeError):
    """The requested OCR engine is not installed."""


def _package_version(name: str) -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(name)
    except PackageNotFoundError:  # pragma: no cover
        return "unknown"


class RapidOcrEngine:
    name = "rapidocr"

    def __init__(self, threads: int | None = None) -> None:
        try:
            from rapidocr import RapidOCR
        except ImportError as exc:
            raise OcrUnavailableError("RapidOCR requires the 'ocr' extra") from exc
        params: dict[str, Any] = {"Global.log_level": "error"}
        if threads:
            params["EngineConfig.onnxruntime.intra_op_num_threads"] = threads
            params["EngineConfig.onnxruntime.inter_op_num_threads"] = 1
        self._engine = RapidOCR(params=params)
        self.version = _package_version("rapidocr")

    def recognize(self, image: Any) -> list[OcrLine]:
        import numpy as np
        from rapidocr.utils.output import RapidOCROutput

        result = self._engine(np.asarray(image.convert("RGB")))
        # Only a full det+rec run yields RapidOCROutput; when recognition fails RapidOCR
        # returns the bare detection output (boxes, no texts), which has nothing to read.
        if (
            not isinstance(result, RapidOCROutput)
            or result.boxes is None
            or result.txts is None
            or result.scores is None
        ):
            return []
        lines = []
        for quad, text, score in zip(result.boxes, result.txts, result.scores, strict=True):
            (x0, y0), (x1, y1), _, (x3, y3) = (tuple(map(float, p)) for p in quad)
            xs = [float(p[0]) for p in quad]
            ys = [float(p[1]) for p in quad]
            lines.append(
                OcrLine(
                    text=str(text),
                    box=(min(xs), min(ys), max(xs), max(ys)),
                    height=math.hypot(x3 - x0, y3 - y0),
                    confidence=round(float(score), 4),
                    angle=math.atan2(y1 - y0, x1 - x0),
                )
            )
        return lines


class TesseractEngine:
    name = "tesseract"

    def __init__(self, lang: str = "eng") -> None:
        try:
            import pytesseract
        except ImportError as exc:
            raise OcrUnavailableError("Tesseract requires the 'tesseract' extra") from exc
        try:
            self.version = str(pytesseract.get_tesseract_version())
        except pytesseract.TesseractNotFoundError as exc:
            raise OcrUnavailableError("the tesseract binary is not installed") from exc
        self._pytesseract = pytesseract
        self.lang = lang

    def recognize(self, image: Any) -> list[OcrLine]:
        data = self._pytesseract.image_to_data(
            image, lang=self.lang, output_type=self._pytesseract.Output.DICT
        )
        words: dict[tuple[int, int, int], list[tuple[str, float, float, float, float, float]]] = {}
        for i, text in enumerate(data["text"]):
            conf = float(data["conf"][i])
            if not text.strip() or conf < 0:
                continue
            left, top = float(data["left"][i]), float(data["top"][i])
            width, height = float(data["width"][i]), float(data["height"][i])
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            words.setdefault(key, []).append((text, left, top, left + width, top + height, conf))
        lines = []
        for group in words.values():
            group.sort(key=lambda w: w[1])
            first, last = group[0], group[-1]
            angle = None
            if len(group) > 1:
                angle = math.atan2(
                    (last[2] + last[4]) / 2 - (first[2] + first[4]) / 2,
                    (last[1] + last[3]) / 2 - (first[1] + first[3]) / 2,
                )
            lines.append(
                OcrLine(
                    text=" ".join(w[0] for w in group),
                    box=(
                        min(w[1] for w in group),
                        min(w[2] for w in group),
                        max(w[3] for w in group),
                        max(w[4] for w in group),
                    ),
                    height=statistics.median(w[4] - w[2] for w in group),
                    confidence=round(statistics.fmean(w[5] for w in group) / 100, 4),
                    angle=angle,
                )
            )
        return lines


def _rapidocr_available() -> bool:
    return importlib.util.find_spec("rapidocr") is not None


def _tesseract_available() -> bool:
    return importlib.util.find_spec("pytesseract") is not None and bool(shutil.which("tesseract"))


ENGINES: dict[str, tuple[Callable[..., OcrEngine], Callable[[], bool]]] = {
    "rapidocr": (lambda threads=None, **_: RapidOcrEngine(threads=threads), _rapidocr_available),
    "tesseract": (lambda lang="eng", **_: TesseractEngine(lang=lang), _tesseract_available),
}


def available_engines() -> list[str]:
    return [name for name, (_, available) in ENGINES.items() if available()]


def resolve_engine_name(name: str) -> str | None:
    """``auto`` -> first installed engine (RapidOCR first); ``none`` -> no OCR."""
    if name == "none":
        return None
    if name == "auto":
        installed = available_engines()
        return installed[0] if installed else None
    if name not in ENGINES:
        raise ValueError(
            f"unknown OCR engine {name!r}; choose from auto, none, {', '.join(ENGINES)}"
        )
    return name


def create_engine(name: str, *, threads: int | None = None, lang: str = "eng") -> OcrEngine:
    factory, _ = ENGINES[name]
    return factory(threads=threads, lang=lang)


def assemble_rows(lines: list[OcrLine]) -> list[list[OcrLine]]:
    """Group OCR lines into reading-order rows.

    Engines return a table row as several boxes (one per cell) and, on a skewed
    scan, those boxes drift vertically across the page. The median baseline angle
    is used to deskew box centres before grouping, then each row is sorted left to
    right.
    """
    if not lines:
        return []
    angles = [
        line.angle
        for line in lines
        if line.angle is not None and line.box[2] - line.box[0] > 3 * line.height
    ]
    tilt = math.tan(statistics.median(angles)) if angles else 0.0

    def deskewed_y(line: OcrLine) -> float:
        cx = (line.box[0] + line.box[2]) / 2
        cy = (line.box[1] + line.box[3]) / 2
        return cy - cx * tilt

    tolerance = 0.5 * statistics.median(line.height for line in lines)
    rows: list[list[OcrLine]] = []
    anchors: list[float] = []
    for line in sorted(lines, key=deskewed_y):
        y = deskewed_y(line)
        if rows and abs(y - anchors[-1]) <= tolerance:
            rows[-1].append(line)
            anchors[-1] = statistics.fmean(deskewed_y(item) for item in rows[-1])
        else:
            rows.append([line])
            anchors.append(y)
    return [sorted(row, key=lambda item: item.box[0]) for row in rows]


def lines_to_blocks(
    lines: list[OcrLine], *, doc_id: str, page_number: int, scale: float
) -> tuple[str, list[Block]]:
    """Page text and one block per row. ``scale`` converts pixels to PDF points."""
    texts: list[str] = []
    blocks: list[Block] = []
    offset = 0
    for row in assemble_rows(lines):
        text = " ".join(item.text.strip() for item in row if item.text.strip())
        if not text:
            continue
        confidences = [item.confidence for item in row if item.confidence is not None]
        blocks.append(
            Block(
                id=f"{doc_id}:p{page_number}:b{len(blocks)}",
                page=page_number,
                text=text,
                bbox=(
                    round(min(item.box[0] for item in row) / scale, 2),
                    round(min(item.box[1] for item in row) / scale, 2),
                    round(max(item.box[2] for item in row) / scale, 2),
                    round(max(item.box[3] for item in row) / scale, 2),
                ),
                char_span=(offset, offset + len(text)),
                source="ocr",
                ocr_confidence=round(statistics.fmean(confidences), 4) if confidences else None,
            )
        )
        texts.append(text)
        offset += len(text) + 1
    return "\n".join(texts), blocks
