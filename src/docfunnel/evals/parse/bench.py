"""Single-process text-layer throughput: pypdfium2 against the pypdf baseline."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from pathlib import Path

from docfunnel.evals.parse.models import (
    TextLayerBench,
)
from docfunnel.parse.pipeline import (
    ParseOptions,
    close_cached_pdfs,
    parse_pdf_page,
)


def _best_of(repeats: int, run: Callable[[], None]) -> float:
    best = float("inf")
    for _ in range(repeats):
        started = time.perf_counter()
        run()
        best = min(best, time.perf_counter() - started)
    return best


def bench_text_layer(pages: Sequence[tuple[Path, int]], repeats: int = 3) -> TextLayerBench:
    """Single-process text extraction over the same digital pages, best of ``repeats``."""
    import pypdfium2 as pdfium

    by_file: dict[Path, list[int]] = {}
    for path, index in pages:
        by_file.setdefault(path, []).append(index)
    options = ParseOptions(ocr_engine="none")

    def full() -> None:
        for path, indexes in by_file.items():
            for index in indexes:
                parse_pdf_page(str(path), index, path.stem, options)
            close_cached_pdfs()

    def text_only() -> None:
        for path, indexes in by_file.items():
            pdf = pdfium.PdfDocument(str(path))
            for index in indexes:
                textpage = pdf[index].get_textpage()
                textpage.get_text_range()
                textpage.close()
            pdf.close()

    pypdf_rate = None
    try:
        from pypdf import PdfReader

        def with_pypdf() -> None:
            for path, indexes in by_file.items():
                reader = PdfReader(path)
                for index in indexes:
                    reader.pages[index].extract_text()

        pypdf_rate = len(pages) / _best_of(repeats, with_pypdf)
    except ImportError:
        pass
    full()  # warm-up: imports, PDFium initialisation
    full_rate = len(pages) / _best_of(repeats, full)
    text_rate = len(pages) / _best_of(repeats, text_only)
    return TextLayerBench(
        pages=len(pages),
        pypdfium2_pages_per_s=round(full_rate, 1),
        pypdfium2_text_only_pages_per_s=round(text_rate, 1),
        pypdf_pages_per_s=round(pypdf_rate, 1) if pypdf_rate else None,
        speedup_vs_pypdf=round(text_rate / pypdf_rate, 1) if pypdf_rate else None,
    )
