"""MCP server exposing an ``extract_document`` tool (optional extra ``mcp``).

Run it over stdio for MCP clients (Claude Desktop, IDEs, agents)::

    uv run --extra mcp docfunnel mcp

The tool logic is a plain function (:func:`extract_document`) so it can be tested
without the SDK installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from docfunnel.service import get_extractor

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

TOOL_DESCRIPTION = (
    "Extract structured data (vendor, date, currency, subtotal, tax, total, payment method, "
    "line items) from the text of a receipt or invoice. Returns validated JSON with per-field "
    "confidence, business-rule issues, and a needs_review flag with reasons."
)


def extract_document(text: str) -> dict[str, Any]:
    """Extract a receipt/invoice from raw text and return the result as JSON-compatible data."""
    result = get_extractor().extract(text)
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
    server.tool(name="extract_document", description=TOOL_DESCRIPTION)(extract_document)
    return server


def main() -> None:  # pragma: no cover - blocking stdio loop
    build_server().run()


if __name__ == "__main__":  # pragma: no cover
    main()
