# Using docfunnel from an agent

An agent that reads a PDF itself spends tokens on every page and loses track of where each fact came from. docfunnel does the cheap part on the CPU: it reads the text layer, OCRs only the pages that need it, and returns Markdown with one `## Page N` section per page, so the agent can quote and cite pages. For receipts and invoices it can also return validated JSON with a review decision.

The bridge is an [MCP](https://modelcontextprotocol.io) server over stdio, so one setup works in Claude Code, the Claude Agent SDK, the OpenAI Agents SDK, Gemini CLI, LiteLLM and any other MCP client. In Python code without an agent framework, call the [library API](usage.md#python-api) directly.

## The tools

| Tool | Input | Returns | LLM call |
| --- | --- | --- | --- |
| `parse_document` | `source` (local path or http(s) URL), `format` (`markdown` or `text`), `pages` (list of page numbers), `max_chars` (default 40,000) | `content`, plus `page_count`, a per-page summary (`route`, `source`, `chars`, `error`) and `truncated` | No |
| `extract_document` | `source` or `text` | Receipt or invoice fields, per-field confidence, business-rule `issues`, `needs_review` with reasons, token and cost totals | Yes, with the model set by `DOCFUNNEL_PROVIDER` / `DOCFUNNEL_MODEL` |

Both tools are annotated read-only, non-destructive, idempotent and open-world (they may fetch URLs, and extraction calls an LLM API), so hosts can decide when to ask before a call. `parse_document` works on any document and needs no API key. `extract_document` only knows the receipt and invoice schema; its default provider, `fake`, is the offline test double, so set a real provider for real documents.

## Run the server

```bash
uv run --directory /path/to/docfunnel --extra mcp --extra cpu docfunnel mcp
```

`--extra cpu` adds RapidOCR for scanned pages; without it, scanned pages come back with `OCR needed but no OCR engine is installed`. Add `--extra providers` (or just the one you use) for `extract_document` with a real model.

### What the server may read

| Variable | Effect | Default |
| --- | --- | --- |
| `DOCFUNNEL_INPUT_DIR` | Local paths must stay inside this directory | Not set: any local file of a supported type (pdf, png, jpg, tiff, webp, bmp, txt, md) |
| `DOCFUNNEL_ALLOW_URLS` | Download http(s) URLs | `1` |
| `DOCFUNNEL_ALLOW_PRIVATE_URLS` | Allow URLs on private, loopback and link-local addresses | `0` |
| `DOCFUNNEL_MAX_DOWNLOAD_MB` | Download size limit | `50` |

Set `DOCFUNNEL_INPUT_DIR` whenever the agent handles untrusted input. Private addresses are blocked so that a document link cannot make the server call internal services (cloud metadata endpoints, admin panels); the check covers every redirect. Tool output is document content: a document can contain text written to look like instructions, so treat it as data in the agent's prompt.

## Claude Code

```bash
claude mcp add --env DOCFUNNEL_PROVIDER=anthropic --transport stdio docfunnel \
  -- uv run --directory /path/to/docfunnel --extra mcp --extra cpu --extra anthropic docfunnel mcp
```

Everything after `--` is the server command. Then ask, for example, "summarize https://example.com/report.pdf and cite pages".

## Claude Agent SDK (Python)

```python
import asyncio

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

DOCFUNNEL = "/path/to/docfunnel"


async def main() -> None:
    options = ClaudeAgentOptions(
        mcp_servers={
            "docfunnel": {
                "command": "uv",
                "args": [
                    "run",
                    "--directory",
                    DOCFUNNEL,
                    "--extra",
                    "mcp",
                    "--extra",
                    "cpu",
                    "docfunnel",
                    "mcp",
                ],
                "env": {"DOCFUNNEL_INPUT_DIR": "/srv/inbox"},
            }
        },
        allowed_tools=["mcp__docfunnel__parse_document"],
    )
    prompt = "Read invoice-0042.pdf and list every line item with its page number."
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage) and message.subtype == "success":
            print(message.result)


asyncio.run(main())
```

MCP tools need explicit permission: `allowed_tools` takes the full names, `mcp__docfunnel__parse_document` and `mcp__docfunnel__extract_document`, or `mcp__docfunnel__*` for both. See the [Agent SDK MCP guide](https://code.claude.com/docs/en/agent-sdk/mcp).

## OpenAI Agents SDK

```python
import asyncio

from agents import Agent, Runner
from agents.mcp import MCPServerStdio


async def main() -> None:
    async with MCPServerStdio(
        name="docfunnel",
        params={
            "command": "uv",
            "args": [
                "run",
                "--directory",
                "/path/to/docfunnel",
                "--extra",
                "mcp",
                "--extra",
                "cpu",
                "docfunnel",
                "mcp",
            ],
        },
        client_session_timeout_seconds=120,  # OCR on a long scan takes a while
    ) as server:
        agent = Agent(
            name="Analyst",
            instructions="Read documents with parse_document and cite page numbers.",
            mcp_servers=[server],
        )
        result = await Runner.run(agent, "What is the notice period in contract.pdf?")
        print(result.final_output)


asyncio.run(main())
```

## Gemini CLI

In `~/.gemini/settings.json` (user) or `.gemini/settings.json` (project):

```json
{
  "mcpServers": {
    "docfunnel": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/docfunnel", "--extra", "mcp",
               "--extra", "cpu", "docfunnel", "mcp"],
      "env": { "DOCFUNNEL_INPUT_DIR": "/path/to/documents" }
    }
  }
}
```

## LiteLLM

Through the LiteLLM proxy, every model it routes to gets the tools. Add the server to the proxy's `config.yaml`:

```yaml
mcp_servers:
  docfunnel:
    transport: "stdio"
    command: "uv"
    args: ["run", "--directory", "/path/to/docfunnel", "--extra", "mcp", "--extra", "cpu",
           "docfunnel", "mcp"]
    env:
      DOCFUNNEL_INPUT_DIR: "/srv/inbox"
```

Start the proxy with `LITELLM_ENABLE_MCP_STDIO=true` in its environment (setting it under `environment_variables` in the config has no effect). Clients then reference the proxy's MCP servers as a tool, for example in a Responses API request:

```json
{"type": "mcp", "server_label": "litellm", "server_url": "litellm_proxy/mcp/docfunnel", "require_approval": "never"}
```

Without the proxy, the LiteLLM Python SDK can load MCP tools in OpenAI format from an MCP client session (`litellm.mcp_client.load_mcp_tools` and `call_openai_tool`). See the [LiteLLM MCP docs](https://docs.litellm.ai/docs/mcp).

## Any other MCP client

The command is the same everywhere:

```json
{
  "mcpServers": {
    "docfunnel": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/docfunnel", "--extra", "mcp", "--extra", "cpu",
               "docfunnel", "mcp"]
    }
  }
}
```
