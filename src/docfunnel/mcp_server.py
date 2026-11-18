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

import functools
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

from docfunnel.library import extract_document as _extract
from docfunnel.library import parse_document as _parse
from docfunnel.parse.markdown import to_markdown
from docfunnel.parse.ocr import OcrUnavailableError
from docfunnel.providers.base import ProviderNotConfiguredError
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

# MCP tool annotations, in the protocol's field names. Both tools only read: temporary
# downloads are deleted when the call ends, so they are read-only, non-destructive and
# idempotent. Both are open-world: they may fetch URLs, and extraction calls an LLM API.
ANNOTATIONS: dict[str, dict[str, str | bool]] = {
    "parse_document": {
        "title": "Parse document",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
    "extract_document": {
        "title": "Extract receipt or invoice",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
}


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


def extract_document(
    source: str | None = None,
    text: str | None = None,
    route: Literal["text", "hybrid", "hybrid-ocr", "native"] | None = None,
) -> dict[str, Any]:
    """Extract a receipt or invoice from ``source`` or ``text`` as JSON-compatible data.

    ``route`` sets what the model is sent for a PDF or image: ``text`` (the parsed
    text), ``hybrid-ocr`` (adds an image of each scanned page and its OCR text),
    ``hybrid`` (the image without the OCR text) or ``native`` (the file). The server's
    ``DOCFUNNEL_ROUTE`` applies when it is left out.
    """
    settings = get_settings()
    result = _extract(
        source,
        text=text,
        extractor=get_extractor(),
        fetch=settings.fetch_policy(),
        route=route or settings.route,
    )
    return result.model_dump(mode="json", exclude={"calls"})


# Failures the caller can act on: a bad source, a blocked URL, a missing page, a missing
# extra or API key. Their message reaches the model; anything else is reported as a crash.
ANTICIPATED = (ValueError, OSError, ImportError, OcrUnavailableError, ProviderNotConfiguredError)


def _reporting(
    fn: Callable[..., dict[str, Any]], tool_error: type[Exception]
) -> Callable[..., dict[str, Any]]:
    """Re-raise anticipated failures as the SDK's ToolError, so the model reads the reason."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return fn(*args, **kwargs)
        except ANTICIPATED as exc:
            raise tool_error(str(exc)) from exc

    return wrapper


def build_server() -> MCPServer:
    try:
        from mcp.server.mcpserver import MCPServer  # mcp >= 2
        from mcp.server.mcpserver.exceptions import ToolError

        server = MCPServer("docfunnel")
    except ImportError:  # pragma: no cover - mcp 1.x
        try:
            # Checked against the locked mcp 2.x, where this module is an import-time stub.
            from mcp.server.fastmcp import FastMCP  # type: ignore[attr-defined]
            from mcp.server.fastmcp.exceptions import (  # type: ignore[import-not-found, no-redef]
                ToolError,
            )
        except ImportError as exc:
            raise RuntimeError(
                "the MCP server requires the 'mcp' extra: uv sync --extra mcp"
            ) from exc
        server = FastMCP("docfunnel")  # same constructor and .tool()/.run() API in 1.x
    from mcp.types import ToolAnnotations

    for name, fn, description in (
        ("parse_document", parse_document, PARSE_DESCRIPTION),
        ("extract_document", extract_document, EXTRACT_DESCRIPTION),
    ):
        annotations = ToolAnnotations.model_validate(ANNOTATIONS[name])
        server.tool(
            name=name,
            title=annotations.title,
            description=description,
            annotations=annotations,
        )(_reporting(fn, ToolError))
    return server


def main() -> None:  # pragma: no cover - blocking stdio loop
    build_server().run()


if __name__ == "__main__":  # pragma: no cover
    main()
