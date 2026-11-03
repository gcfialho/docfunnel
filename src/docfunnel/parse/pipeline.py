"""Parse files into :class:`ParsedDocument`, page by page, optionally in a process pool.

The unit of work is a **page** ``(path, page_index)``, not a file, so a 200-page
document does not keep one worker busy while the others sit idle. Workers are
processes because PDFium is not thread-safe; each worker opens the PDF itself
(workers receive paths, not images) and returns only text, boxes and timings.
The OCR model is loaded once per worker by the pool initializer, and
``max_tasks_per_child`` recycles workers to contain slow memory growth.

A failure on one page (corrupt object, OCR crash, timeout) becomes ``Page.error``
on that page; the rest of the document is still returned.
"""

from __future__ import annotations

import os
import time
from collections import OrderedDict
from collections.abc import Sequence
from concurrent.futures import Future, ProcessPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from multiprocessing import get_context
from pathlib import Path
from typing import Any

from docfunnel.parse.model import Block, Page, ParsedDocument
from docfunnel.parse.ocr import OcrEngine, create_engine, lines_to_blocks, resolve_engine_name
from docfunnel.parse.pdf import (
    OcrThresholds,
    decide_route,
    page_signals,
    pdfium_version,
    render_page,
    require_pdfium,
    text_layer_blocks,
)

PDF_SUFFIXES = {".pdf"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}
TEXT_SUFFIXES = {".txt", ".md"}


class UnsupportedDocumentError(ValueError):
    """No parser for this file type, or the optional dependency is missing."""


@dataclass(frozen=True)
class ParseOptions:
    ocr_engine: str = "auto"  # auto | none | rapidocr | tesseract
    dpi: int = 200
    force_ocr: bool = False
    thresholds: OcrThresholds = field(default_factory=OcrThresholds)
    with_boxes: bool = True
    ocr_threads: int | None = None  # ONNX Runtime intra-op threads; None = engine default
    tesseract_lang: str = "eng"
    page_timeout_s: float | None = 300.0


# ---- per-process state (one copy in each worker, or in the main process) ------------

_ENGINES: dict[tuple[str, int | None, str], OcrEngine] = {}
_OPEN_PDFS: OrderedDict[str, Any] = OrderedDict()
_MAX_OPEN_PDFS = 4


def _engine_for(options: ParseOptions) -> OcrEngine | None:
    name = resolve_engine_name(options.ocr_engine)
    if name is None:
        return None
    key = (name, options.ocr_threads, options.tesseract_lang)
    if key not in _ENGINES:
        _ENGINES[key] = create_engine(
            name, threads=options.ocr_threads, lang=options.tesseract_lang
        )
    return _ENGINES[key]


def _open_pdf(path: str) -> Any:
    pdf = _OPEN_PDFS.get(path)
    if pdf is None:
        pdf = require_pdfium().PdfDocument(path)
        _OPEN_PDFS[path] = pdf
        if len(_OPEN_PDFS) > _MAX_OPEN_PDFS:
            _, oldest = _OPEN_PDFS.popitem(last=False)
            oldest.close()
    else:
        _OPEN_PDFS.move_to_end(path)
    return pdf


def close_cached_pdfs() -> None:
    while _OPEN_PDFS:
        _, pdf = _OPEN_PDFS.popitem()
        pdf.close()


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 3)


def parse_pdf_page(path: str, index: int, doc_id: str, options: ParseOptions) -> Page:
    """Parse one page: text layer, OCR decision, and OCR when the decision says so."""
    number = index + 1
    timings: dict[str, float] = {}
    started = time.perf_counter()
    try:
        page = _open_pdf(path)[index]
        width, height = page.get_size()
        textpage = page.get_textpage()
        try:
            t0 = time.perf_counter()
            raw = textpage.get_text_range()
            timings["text_layer"] = _ms(t0)
            t0 = time.perf_counter()
            signals = page_signals(raw, page)
            route = decide_route(signals, options.thresholds, force_ocr=options.force_ocr)
            timings["decide"] = _ms(t0)
            engine = _engine_for(options) if route != "text_layer" else None
            if engine is None:
                t0 = time.perf_counter()
                text, blocks = text_layer_blocks(
                    textpage,
                    raw,
                    doc_id=doc_id,
                    page_number=number,
                    page_height=height,
                    with_boxes=options.with_boxes,
                )
                timings["blocks"] = _ms(t0)
                missing = route != "text_layer"
                return Page(
                    number=number,
                    width=width,
                    height=height,
                    text=text,
                    route=route,
                    source="none" if missing and not text.strip() else "text_layer",
                    blocks=blocks,
                    signals=signals,
                    timings_ms={**timings, "total": _ms(started)},
                    error="OCR needed but no OCR engine is installed" if missing else None,
                )
        finally:
            textpage.close()
        t0 = time.perf_counter()
        image = render_page(page, options.dpi)
        timings["render"] = _ms(t0)
        t0 = time.perf_counter()
        lines = engine.recognize(image)
        timings["ocr"] = _ms(t0)
        text, blocks = lines_to_blocks(
            lines, doc_id=doc_id, page_number=number, scale=options.dpi / 72
        )
        return Page(
            number=number,
            width=width,
            height=height,
            text=text,
            route=route,
            source="ocr",
            blocks=blocks,
            signals=signals,
            ocr_engine=f"{engine.name}@{engine.version}",
            dpi=options.dpi,
            timings_ms={**timings, "total": _ms(started)},
        )
    except Exception as exc:  # isolate the failure to this page
        return _error_page(number, f"{type(exc).__name__}: {exc}", _ms(started))


def _error_page(number: int, message: str, total_ms: float = 0.0) -> Page:
    return Page(
        number=number,
        width=0.0,
        height=0.0,
        text="",
        route="text_layer",
        source="none",
        timings_ms={"total": total_ms},
        error=message,
    )


def pdf_page_count(path: Path) -> int:
    pdf = require_pdfium().PdfDocument(str(path))
    try:
        return len(pdf)
    finally:
        pdf.close()


def _parser_name(pages: Sequence[Page], base: str) -> str:
    engines = sorted({p.ocr_engine for p in pages if p.ocr_engine})
    return "+".join([base, *engines])


def _assemble_pdf(path: Path, doc_id: str, pages: list[Page], started: float) -> ParsedDocument:
    return ParsedDocument(
        doc_id=doc_id,
        source_path=str(path),
        parser=_parser_name(pages, f"pypdfium2@{pdfium_version()}"),
        pages=pages,
        timings_ms={"total": _ms(started)},
    )


def parse_image(path: Path, doc_id: str, options: ParseOptions) -> ParsedDocument:
    from PIL import Image

    started = time.perf_counter()
    engine = _engine_for(options)
    if engine is None:
        raise UnsupportedDocumentError(
            "image input needs an OCR engine: install the 'ocr' (RapidOCR) or 'tesseract' extra"
        )
    with Image.open(path) as image:
        dpi = int(image.info.get("dpi", (options.dpi,))[0]) or options.dpi
        t0 = time.perf_counter()
        lines = engine.recognize(image.convert("L"))
        ocr_ms = _ms(t0)
        width, height = image.size
    scale = dpi / 72
    text, blocks = lines_to_blocks(lines, doc_id=doc_id, page_number=1, scale=scale)
    page = Page(
        number=1,
        width=width / scale,
        height=height / scale,
        text=text,
        route="ocr:image",
        source="ocr",
        blocks=blocks,
        ocr_engine=f"{engine.name}@{engine.version}",
        dpi=dpi,
        timings_ms={"ocr": ocr_ms, "total": _ms(started)},
    )
    return ParsedDocument(
        doc_id=doc_id,
        source_path=str(path),
        parser=_parser_name([page], "image"),
        pages=[page],
        timings_ms={"total": _ms(started)},
    )


def parse_text_file(path: Path, doc_id: str) -> ParsedDocument:
    started = time.perf_counter()
    text = path.read_text(encoding="utf-8")
    blocks, offset = [], 0
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped:
            start = offset + len(line) - len(line.lstrip())
            blocks.append(
                Block(
                    id=f"{doc_id}:p1:b{len(blocks)}",
                    page=1,
                    text=stripped,
                    char_span=(start, start + len(stripped)),
                    source="plain_text",
                )
            )
        offset += len(line) + 1
    page = Page(number=1, width=0.0, height=0.0, text=text, route="plain_text", source="plain_text")
    page.blocks = blocks
    return ParsedDocument(
        doc_id=doc_id,
        source_path=str(path),
        parser="plain_text",
        pages=[page],
        timings_ms={"total": _ms(started)},
    )


def _check_suffix(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in PDF_SUFFIXES | IMAGE_SUFFIXES | TEXT_SUFFIXES:
        raise UnsupportedDocumentError(f"unsupported file type {suffix!r} for {path.name}")
    return suffix


def parse_file(
    path: Path, options: ParseOptions | None = None, *, doc_id: str | None = None
) -> ParsedDocument:
    """Parse one file in the current process, page after page."""
    options = options or ParseOptions()
    doc_id = doc_id or path.stem
    suffix = _check_suffix(path)
    if suffix in TEXT_SUFFIXES:
        return parse_text_file(path, doc_id)
    if suffix in IMAGE_SUFFIXES:
        return parse_image(path, doc_id, options)
    started = time.perf_counter()
    try:
        count = pdf_page_count(path)
    except ImportError as exc:
        raise UnsupportedDocumentError(str(exc)) from exc
    pages = [parse_pdf_page(str(path), i, doc_id, options) for i in range(count)]
    close_cached_pdfs()
    return _assemble_pdf(path, doc_id, pages, started)


# ---- process pool ----------------------------------------------------------------


_THREAD_ENV = (
    "OMP_THREAD_LIMIT",  # Tesseract
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)


def _init_worker(options: ParseOptions) -> None:
    # N processes x 1 thread each: libraries that default to "all cores" in every
    # worker would oversubscribe the CPU.
    for name in _THREAD_ENV:
        os.environ.setdefault(name, "1")
    try:
        import cv2  # pulled in by RapidOCR

        cv2.setNumThreads(1)
    except ImportError:
        pass
    _engine_for(options)  # load the OCR model once per worker


def default_workers() -> int:
    return os.cpu_count() or 1


def _warm_up(seconds: float) -> int:
    time.sleep(seconds)
    return os.getpid()


def _parse_whole(path: str, doc_id: str, options: ParseOptions) -> ParsedDocument:
    return parse_file(Path(path), options, doc_id=doc_id)


class PagePool:
    """A warm process pool that parses many documents with pages as the unit of work.

    Use as a context manager. :meth:`start` spawns every worker and loads the OCR
    model, so its duration is the cold start; :meth:`parse` then runs in steady state.
    """

    def __init__(self, options: ParseOptions | None = None, workers: int | None = None) -> None:
        self.options = options or ParseOptions()
        if self.options.ocr_threads is None:
            # N processes x 1 ONNX thread avoids oversubscribing the cores.
            self.options = ParseOptions(**{**self.options.__dict__, "ocr_threads": 1})
        self.workers = workers or default_workers()
        self._executor: ProcessPoolExecutor | None = None
        self.cold_start_s: float | None = None

    def start(self) -> PagePool:
        started = time.perf_counter()
        self._executor = ProcessPoolExecutor(
            max_workers=self.workers,
            mp_context=get_context("spawn"),
            initializer=_init_worker,
            initargs=(self.options,),
            max_tasks_per_child=500,
        )
        pids = [self._executor.submit(_warm_up, 0.2) for _ in range(self.workers)]
        for future in pids:
            future.result()
        self.cold_start_s = round(time.perf_counter() - started, 3)
        return self

    def __enter__(self) -> PagePool:
        return self.start()

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=True)
            self._executor = None

    def parse(
        self, paths: Sequence[Path], doc_ids: Sequence[str] | None = None
    ) -> list[ParsedDocument]:
        if self._executor is None:
            raise RuntimeError("PagePool is not started")
        executor = self._executor
        doc_ids = list(doc_ids) if doc_ids is not None else [p.stem for p in paths]
        started = time.perf_counter()
        plans: list[tuple[Path, str, list[Future[Page]] | Future[ParsedDocument] | str]] = []
        for path, doc_id in zip(paths, doc_ids, strict=True):
            try:
                suffix = _check_suffix(path)
                if suffix in PDF_SUFFIXES:
                    count = pdf_page_count(path)
                    futures = [
                        executor.submit(parse_pdf_page, str(path), i, doc_id, self.options)
                        for i in range(count)
                    ]
                    plans.append((path, doc_id, futures))
                else:
                    plans.append(
                        (
                            path,
                            doc_id,
                            executor.submit(_parse_whole, str(path), doc_id, self.options),
                        )
                    )
            except Exception as exc:  # unreadable file: report it, keep going
                plans.append((path, doc_id, f"{type(exc).__name__}: {exc}"))

        documents = []
        for path, doc_id, plan in plans:
            if isinstance(plan, str):
                documents.append(
                    ParsedDocument(
                        doc_id=doc_id, source_path=str(path), parser="none", pages=[], error=plan
                    )
                )
            elif isinstance(plan, Future):
                documents.append(plan.result())
            else:
                pages = [self._collect(f, i + 1) for i, f in enumerate(plan)]
                documents.append(_assemble_pdf(path, doc_id, pages, started))
        return documents

    def _collect(self, future: Future[Page], number: int) -> Page:
        try:
            return future.result(timeout=self.options.page_timeout_s)
        except FutureTimeout:
            future.cancel()
            return _error_page(number, f"timeout after {self.options.page_timeout_s}s")
        except Exception as exc:  # e.g. a worker died
            return _error_page(number, f"{type(exc).__name__}: {exc}")


def parse_documents(
    paths: Sequence[Path], options: ParseOptions | None = None, *, workers: int = 1
) -> list[ParsedDocument]:
    """Parse many files; ``workers > 1`` uses a page-level process pool."""
    if workers <= 1:
        return [parse_file(path, options) for path in paths]
    with PagePool(options, workers) as pool:
        return pool.parse(paths)
