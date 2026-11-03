import asyncio
import json
from pathlib import Path

import pytest

from docfunnel import mcp_server
from docfunnel.loaders import UnsupportedDocumentError, load_document, register_loader

from helpers import US_RECEIPT


def test_extract_document_tool_returns_json_compatible_data() -> None:
    result = mcp_server.extract_document(US_RECEIPT)
    assert result["document"]["total"] == 29.42
    assert "calls" not in result
    assert isinstance(result["needs_review"], bool)


def test_mcp_server_lists_and_calls_the_tool() -> None:
    pytest.importorskip("mcp")
    server = mcp_server.build_server()

    async def roundtrip() -> tuple[list, object]:
        tools = await server.list_tools()
        result = await server.call_tool("extract_document", {"text": US_RECEIPT})
        return tools, result

    tools, result = asyncio.run(roundtrip())
    assert [t.name for t in tools] == ["extract_document"]
    payload = json.loads(result.content[0].text)
    assert payload["document"]["vendor_name"] == "Maple Street Hardware"


def test_text_loader(tmp_path: Path) -> None:
    path = tmp_path / "r.txt"
    path.write_text(US_RECEIPT)
    assert load_document(path) == US_RECEIPT


def test_unknown_suffix_and_custom_loader(tmp_path: Path) -> None:
    path = tmp_path / "r.custom"
    path.write_text("ignored")
    with pytest.raises(UnsupportedDocumentError):
        load_document(path)
    register_loader(".custom", lambda p: "from custom loader")
    assert load_document(path) == "from custom loader"


def test_pdf_loader(tmp_path: Path) -> None:
    pypdf = pytest.importorskip("pypdf")
    path = tmp_path / "blank.pdf"
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with path.open("wb") as handle:
        writer.write(handle)
    with pytest.raises(UnsupportedDocumentError, match="no text found"):
        load_document(path)
