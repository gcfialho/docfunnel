import asyncio
import json
from pathlib import Path

import pytest

from docfunnel import mcp_server
from docfunnel.config import Settings
from docfunnel.loaders import UnsupportedDocumentError, load_document, register_loader
from docfunnel.sources import SourceError

from helpers import REPO_ROOT, US_RECEIPT, DocServer

EXAMPLES = REPO_ROOT / "examples"


@pytest.fixture
def mcp_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    settings = Settings(provider="fake", allow_private_urls=True)
    monkeypatch.setattr(mcp_server, "get_settings", lambda: settings)
    return settings


def test_extract_document_tool_takes_text_or_a_source(mcp_settings: Settings) -> None:
    by_text = mcp_server.extract_document(text=US_RECEIPT)
    assert by_text["document"]["total"] == 29.42
    assert "calls" not in by_text
    assert isinstance(by_text["needs_review"], bool)
    by_path = mcp_server.extract_document(source=str(EXAMPLES / "receipt_us.txt"))
    assert by_path["document"]["vendor_name"] == "Maple Street Hardware"


def test_parse_document_tool_returns_markdown_and_a_page_summary(mcp_settings: Settings) -> None:
    result = mcp_server.parse_document(str(EXAMPLES / "invoice_multipage.pdf"))
    assert result["doc_id"] == "invoice_multipage"
    assert result["page_count"] == len(result["pages"]) >= 2
    assert result["pages"][0] == {
        "number": 1,
        "route": "text_layer",
        "source": "text_layer",
        "chars": result["pages"][0]["chars"],
        "error": None,
    }
    assert result["content"].startswith("# invoice_multipage\n\n## Page 1")
    assert "## Page 2" in result["content"]
    assert result["truncated"] is False


def test_parse_document_tool_selects_pages_and_truncates(mcp_settings: Settings) -> None:
    source = str(EXAMPLES / "invoice_multipage.pdf")
    second = mcp_server.parse_document(source, pages=[2], format="text")
    assert [p["number"] for p in second["pages"]] == [2]
    assert "## Page" not in second["content"]
    short = mcp_server.parse_document(source, max_chars=100)
    assert len(short["content"]) == 100
    assert short["truncated"] is True
    assert "fewer pages" in short["hint"]
    with pytest.raises(ValueError, match=r"pages \[99\] do not exist"):
        mcp_server.parse_document(source, pages=[99])


def test_tools_respect_the_input_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "r.txt").write_text(US_RECEIPT)
    settings = Settings(provider="fake", input_dir=tmp_path)
    monkeypatch.setattr(mcp_server, "get_settings", lambda: settings)
    assert mcp_server.extract_document(source="r.txt")["document"]["total"] == 29.42
    with pytest.raises(SourceError, match="must stay inside"):
        mcp_server.parse_document(str(EXAMPLES / "invoice_multipage.pdf"))


def test_parse_document_tool_downloads_urls(mcp_settings: Settings, doc_server: DocServer) -> None:
    url = doc_server.serve("/in/invoice.pdf", (EXAMPLES / "invoice_multipage.pdf").read_bytes())
    result = mcp_server.parse_document(url)
    assert result["source"] == url
    assert result["doc_id"] == "invoice"


def test_mcp_server_lists_and_calls_the_tools(mcp_settings: Settings) -> None:
    pytest.importorskip("mcp")
    from mcp.types import CallToolResult, TextContent, Tool

    server = mcp_server.build_server()

    async def roundtrip() -> tuple[list[Tool], object, object]:
        tools = await server.list_tools()
        extracted = await server.call_tool("extract_document", {"text": US_RECEIPT})
        parsed = await server.call_tool(
            "parse_document", {"source": str(EXAMPLES / "receipt_us.txt")}
        )
        return tools, extracted, parsed

    tools, extracted, parsed = asyncio.run(roundtrip())
    assert sorted(t.name for t in tools) == ["extract_document", "parse_document"]
    assert isinstance(extracted, CallToolResult)
    assert isinstance(parsed, CallToolResult)
    extracted_text = extracted.content[0]
    parsed_text = parsed.content[0]
    assert isinstance(extracted_text, TextContent)
    assert isinstance(parsed_text, TextContent)
    assert json.loads(extracted_text.text)["document"]["vendor_name"] == "Maple Street Hardware"
    assert "MAPLE STREET HARDWARE" in json.loads(parsed_text.text)["content"]


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


def test_anticipated_tool_failures_reach_the_model(mcp_settings: Settings) -> None:
    pytest.importorskip("mcp")
    from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

    server = mcp_server.build_server()
    source = str(EXAMPLES / "invoice_multipage.pdf")

    async def call() -> object:
        return await server.call_tool("parse_document", {"source": source, "pages": [99]})

    # A ToolError's text goes to the model; an UnexpectedToolError's text is withheld.
    with pytest.raises(ToolError, match=r"pages \[99\] do not exist") as info:
        asyncio.run(call())
    assert not isinstance(info.value, UnexpectedToolError)
