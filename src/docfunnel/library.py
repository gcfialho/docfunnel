"""docfunnel as a library: parse or extract one document from a path, a URL or bytes.

>>> import docfunnel
>>> doc = docfunnel.parse_document("examples/invoice_mixed_scan.pdf")
>>> [page.route for page in doc.pages]
['text_layer', 'ocr:scan_with_stray_text']
>>> result = docfunnel.extract_document("https://example.com/receipt.pdf")  # doctest: +SKIP

Both functions block; :func:`aparse_document` and :func:`aextract_document` run them in a
worker thread for async code (agent frameworks, web handlers). The lower-level pieces
stay available: :func:`docfunnel.parse.parse_file`, :class:`docfunnel.extract.Extractor`
and :func:`docfunnel.config.build_extractor`.
"""

from __future__ import annotations

import asyncio

from docfunnel.config import Settings, build_extractor
from docfunnel.extract.extractor import Extractor
from docfunnel.extract.schema import ExtractionResult
from docfunnel.inputs import ModelInput, Route, build_input, parse_route
from docfunnel.parse.model import ParsedDocument
from docfunnel.parse.pipeline import ParseOptions, parse_file
from docfunnel.sources import FetchPolicy, SourceLike, open_source

__all__ = ["aextract_document", "aparse_document", "extract_document", "parse_document"]


def parse_document(
    source: SourceLike,
    *,
    options: ParseOptions | None = None,
    fetch: FetchPolicy | None = None,
    doc_id: str | None = None,
) -> ParsedDocument:
    """Parse a PDF, image or text file into pages and blocks. No LLM call.

    ``source`` is a local path, an ``http(s)://`` URL (downloaded under ``fetch``) or the
    document's bytes. ``source_path`` on the result is the path or URL that was given.
    """
    with open_source(source, fetch, name=doc_id) as resolved:
        document = parse_file(resolved.path, options, doc_id=resolved.name)
    return document.model_copy(update={"source_path": resolved.origin})


def extract_document(
    source: SourceLike | None = None,
    *,
    text: str | None = None,
    extractor: Extractor | None = None,
    settings: Settings | None = None,
    parse_options: ParseOptions | None = None,
    fetch: FetchPolicy | None = None,
    route: Route | str | None = None,
) -> ExtractionResult:
    """Extract a receipt or invoice into validated JSON, with a review decision.

    Pass either ``source`` (path, URL or bytes; PDFs and images go through the parse
    stage) or ``text``. The model comes from ``extractor``, else from ``settings``, else
    from the ``DOCFUNNEL_*`` environment variables (the offline ``fake`` provider when
    nothing is set). Bad model output never raises: it ends up in the result with
    ``needs_review=True``.

    ``route`` sets what the model is sent for a PDF or image (see
    :mod:`docfunnel.inputs`): ``"text"`` (the default), ``"hybrid"``, ``"hybrid-ocr"``
    (most accurate on scans in our runs) or ``"native"``. It defaults to
    ``settings.route`` (``DOCFUNNEL_ROUTE``).
    """
    if (source is None) == (text is None):
        raise ValueError("pass exactly one of source or text")
    if text is not None:
        model_input = ModelInput(text)
    else:
        assert source is not None
        if route is None:
            route = (settings or Settings.from_env()).route
        with open_source(source, fetch) as resolved:
            model_input = build_input(resolved.path, parse_route(route), parse_options)
    if extractor is None:
        extractor = build_extractor(settings or Settings.from_env())
    return extractor.extract(model_input.text, attachments=model_input.attachments)


async def aparse_document(
    source: SourceLike,
    *,
    options: ParseOptions | None = None,
    fetch: FetchPolicy | None = None,
    doc_id: str | None = None,
) -> ParsedDocument:
    """:func:`parse_document` in a worker thread."""
    return await asyncio.to_thread(
        parse_document, source, options=options, fetch=fetch, doc_id=doc_id
    )


async def aextract_document(
    source: SourceLike | None = None,
    *,
    text: str | None = None,
    extractor: Extractor | None = None,
    settings: Settings | None = None,
    parse_options: ParseOptions | None = None,
    fetch: FetchPolicy | None = None,
    route: Route | str | None = None,
) -> ExtractionResult:
    """:func:`extract_document` in a worker thread."""
    return await asyncio.to_thread(
        extract_document,
        source,
        text=text,
        extractor=extractor,
        settings=settings,
        parse_options=parse_options,
        fetch=fetch,
        route=route,
    )
