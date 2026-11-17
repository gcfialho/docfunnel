import asyncio
from pathlib import Path

import pytest

import docfunnel
from docfunnel.config import Settings
from docfunnel.sources import FetchPolicy, SourceError

from helpers import REPO_ROOT, US_RECEIPT, DocServer

EXAMPLES = REPO_ROOT / "examples"
OFFLINE = Settings(provider="fake")


def test_top_level_exports_are_lazy_and_do_not_clash_with_subpackages() -> None:
    import docfunnel.extract
    import docfunnel.parse

    assert callable(docfunnel.parse_document)
    assert callable(docfunnel.extract_document)
    assert docfunnel.FetchPolicy is FetchPolicy
    with pytest.raises(AttributeError, match="no attribute 'nope'"):
        _ = docfunnel.nope


def test_parse_document_from_a_path_keeps_the_given_source() -> None:
    source = str(EXAMPLES / "invoice_multipage.pdf")
    document = docfunnel.parse_document(source)
    assert document.doc_id == "invoice_multipage"
    assert document.source_path == source
    assert len(document.pages) >= 2
    assert all(page.route == "text_layer" for page in document.pages)


def test_parse_document_from_a_url_and_from_bytes(doc_server: DocServer) -> None:
    pdf = (EXAMPLES / "invoice_multipage.pdf").read_bytes()
    url = doc_server.serve("/docs/march.pdf", pdf)
    from_url = docfunnel.parse_document(url, fetch=FetchPolicy(allow_private_hosts=True))
    from_bytes = docfunnel.parse_document(pdf, doc_id="inline")
    assert from_url.doc_id == "march"
    assert from_url.source_path == url
    assert from_bytes.doc_id == "inline"
    assert from_url.text == from_bytes.text


def test_extract_document_from_path_bytes_and_text() -> None:
    path = EXAMPLES / "receipt_us.txt"
    by_path = docfunnel.extract_document(path, settings=OFFLINE)
    by_bytes = docfunnel.extract_document(path.read_bytes(), settings=OFFLINE)
    by_text = docfunnel.extract_document(text=path.read_text(), settings=OFFLINE)
    assert by_path.document is not None
    assert by_path.document.total == by_bytes.document.total == by_text.document.total  # type: ignore[union-attr]


def test_extract_document_needs_exactly_one_input() -> None:
    with pytest.raises(ValueError, match="exactly one of source or text"):
        docfunnel.extract_document()
    with pytest.raises(ValueError, match="exactly one of source or text"):
        docfunnel.extract_document("a.txt", text=US_RECEIPT)


def test_source_errors_surface_unchanged(tmp_path: Path) -> None:
    with pytest.raises(SourceError, match="file not found"):
        docfunnel.parse_document(str(tmp_path / "missing.pdf"))


def test_async_variants() -> None:
    async def run() -> tuple[int, bool]:
        document = await docfunnel.aparse_document(EXAMPLES / "invoice_multipage.pdf")
        result = await docfunnel.aextract_document(text=US_RECEIPT, settings=OFFLINE)
        return len(document.pages), result.schema_valid

    pages, valid = asyncio.run(run())
    assert pages >= 2
    assert valid
