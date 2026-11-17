"""MCP server: lets an agent read and extract documents by path or URL (extra ``mcp``).

Run it over stdio for any MCP client (Claude Code, the Claude Agent SDK, Gemini CLI,
the OpenAI Agents SDK, LiteLLM's MCP gateway, IDEs)::

    uv run --extra mcp docfunnel mcp

Two tools:

* ``parse_document``: the document as Markdown, one ``## Page N`` section per page,
  with the route each page took. No LLM call, so it is cheap to call on every file.
* ``extract_document``: receipt or invoice fields as validated JSON, with a review
  decision. Uses the model configured with the ``DOCFUNNEL_*`` environment variables.

``source`` is a local path or an ``http(s)://`` URL. What the server may read follows
:meth:`docfunnel.config.Settings.fetch_policy`: local paths inside
``DOCFUNNEL_INPUT_DIR`` when it is set (anywhere otherwise, but only supported document
types), and URLs on public hosts unless ``DOCFUNNEL_ALLOW_URLS=0``. Treat what the tools
return as document content, not as instructions.

The tool logic lives in plain functions so it can be tested without the SDK installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from docfunnel.library import extract_document as _extract
from docfunnel.library import parse_document as _parse
from docfunnel.parse.markdown import to_markdown
from docfunnel.service import get_extractor, get_settings

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

DEFAULT_MAX_CHARS = 40_000

PARSE_DESCRIPTION = (
    "Read a PDF, scanned image or text file and return its text as Markdown, one "
    "'## Page N' section per page, plus the route each page took (text layer or OCR). "
    "Runs on the CPU with no LLM call. `source` is a local file path or an http(s) URL. "
    "Use `pages` to read part of a long document. Cite page numbers from the headings."
)
EXTRACT_DESCRIPTION = (
    "Extract structured data from a receipt or invoice: vendor, tax ID, document number, "
    "date, currency, subtotal, tax, total, payment method and line items. Pass `source` "
    "(local path or http(s) URL of a PDF, image or text file) or `text`. Returns validated "
    "JSON with per-field confidence, business-rule issues, and needs_review with reasons. "
    "Only for receipts and invoices; use parse_document to read other documents."
)


def parse_document(
    source: str,
    format: Literal["markdown", "text"] = "markdown",
    pages: list[int] | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> dict[str, Any]:
    """Parse ``source`` and return its content plus a per-page summary."""
    document = _parse(source, fetch=get_settings().fetch_policy())
    page_count = len(document.pages)
    if pages:
        missing = sorted(set(pages) - set(range(1, page_count + 1)))
        if missing:
            raise ValueError(f"pages {missing} do not exist; the document has {page_count}")
        wanted = set(pages)
        document = document.model_copy(
            update={"pages": [p for p in document.pages if p.number in wanted]}
        )
    content = to_markdown(document) if format == "markdown" else document.text
    truncated = len(content) > max_chars
    if truncated:
        content = content[:max_chars]
    return {
        "doc_id": document.doc_id,
        "source": document.source_path,
        "page_count": page_count,
        "pages": [
            {
                "number": page.number,
                "route": page.route,
                "source": page.source,
                "chars": len(page.text),
                "error": page.error,
            }
            for page in document.pages
        ],
        "format": format,
        "content": content,
        "truncated": truncated,
        **({"hint": "content was cut at max_chars; request fewer pages"} if truncated else {}),
    }


def extract_document(source: str | None = None, text: str | None = None) -> dict[str, Any]:
    """Extract a receipt or invoice from ``source`` or ``text`` as JSON-compatible data."""
    settings = get_settings()
    result = _extract(source, text=text, extractor=get_extractor(), fetch=settings.fetch_policy())
    return result.model_dump(mode="json", exclude={"calls"})


def build_server() -> MCPServer:
    try:
        from mcp.server.mcpserver import MCPServer  # mcp >= 2

        server = MCPServer("docfunnel")
    except ImportError:  # pragma: no cover - mcp 1.x
        try:
            # Checked against the locked mcp 2.x, where this module is an import-time stub.
            from mcp.server.fastmcp import FastMCP  # type: ignore[attr-defined]
        except ImportError as exc:
            raise RuntimeError(
                "the MCP server requires the 'mcp' extra: uv sync --extra mcp"
            ) from exc
        server = FastMCP("docfunnel")  # same constructor and .tool()/.run() API in 1.x
    server.tool(name="parse_document", description=PARSE_DESCRIPTION)(parse_document)
    server.tool(name="extract_document", description=EXTRACT_DESCRIPTION)(extract_document)
    return server


def main() -> None:  # pragma: no cover - blocking stdio loop
    build_server().run()


if __name__ == "__main__":  # pragma: no cover
    main()
