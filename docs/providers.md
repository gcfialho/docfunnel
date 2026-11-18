# Providers, models and pricing

OpenAI, Anthropic and Gemini are selected with environment variables or CLI flags (`--provider`, `--model`, `--fallback provider:model`). Three more providers need no API key:

- **`ollama`**: a model on a local [Ollama](https://ollama.com) server (`OLLAMA_HOST`, default `http://localhost:11434`), through its OpenAI-compatible endpoint. The extraction schema is sent as a JSON Schema constraint and thinking is turned off (`reasoning_effort: "none"`). Ollama takes page images but not PDF files, so use the `text`, `hybrid` or `hybrid-ocr` route (`hybrid-ocr` was the most accurate for a local Gemma 4 12B). Local models have no API charge; the price table lists them at $0, without hardware or power.

- **`fake`**: a deterministic regex parser written for the synthetic templates, with fault injection (malformed JSON, schema violations, hard failures and confident hallucinations at fixed rates). It exists to test the harness and the failure handling, not to measure a model.
- **`replay`**: plays back a cassette recorded with `docfunnel eval --record`, so a real-model run can be re-scored offline after changing a metric.

## Default models

Each provider defaults to the low-cost tier of its current model family:

| Provider | Default | Price per 1M input / output tokens |
| --- | --- | --- |
| OpenAI | `gpt-6-luna` | $0.10 / $0.50 |
| Anthropic | `claude-haiku-5-5` | $0.10 / $0.50 (up to 100K input tokens) |
| Gemini | `gemini-3.5-flash-lite` | $0.30 / $2.50 |

For a fallback that steps up in capability rather than switching vendor, use `openai:gpt-6.1-terra` or `anthropic:claude-sonnet-5-5`.

## What each adapter sends

Request parameters come from a per-model table in [`providers/capabilities.py`](../src/docfunnel/providers/capabilities.py), not from the model name. Where the model supports it, the extraction schema is sent as a native structured-output constraint (a strict, provider-neutral subset of the JSON Schema: every field required, optional values as `null`). The system prompt keeps the schema too, and pydantic still validates every answer.

| Model | Output format | Reasoning / thinking | Sampling | Output-token floor |
|---|---|---|---|---|
| `gpt-6-luna` | `response_format` `json_schema` (strict) | `reasoning_effort: "none"` | not sent | 4,096 |
| `gpt-6.1-terra` | `json_schema` (strict) | `reasoning_effort: "low"` | not sent | 16,000 |
| `gpt-4o-mini`, `gpt-4.1-mini` | `json_schema` (strict) | none | `temperature: 0` | none |
| `claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5`, `claude-fable-5-1` | `output_config.format` | adaptive thinking (the default), `effort: "low"` | not sent | 8,192 |
| `claude-haiku-4-5` | `output_config.format` | none (thinking is off by default) | not sent | none |
| `gemini-3.5-flash-lite` | `response_json_schema` | `thinking_level: "minimal"` | not sent | 8,192 |
| `gemini-2.5-flash-lite` | JSON MIME type | none | `temperature: 0` | none |
| any other model | JSON mode / MIME type (OpenAI, Gemini); `output_config.format` (Anthropic) | none | not sent | none |

The floor raises the output-token limit (2,048 by default) because reasoning and thinking tokens count against it. Thinking and reasoning tokens are billed as output, and they are counted in `output_tokens` and the cost (Gemini reports them separately; they are added in).

The Anthropic adapter never sends `temperature`: the `anthropic` 2.x SDK sends API version `2026-10-21`, which rejects sampling parameters on every model. Claude models that think are not asked to disable it: the Haiku 5.5 migration guide says to lower `effort` instead (at `low` the model skips thinking on simple tasks), and Sonnet 5.5, Opus 5.5 and Fable 5.1 reject `thinking: disabled`.

A refusal (OpenAI `refusal`, Anthropic `stop_reason: "refusal"`) is a non-retryable error, so the fallback chain takes over. SDK-level retries are disabled: the extractor owns the retry policy, so every attempt is accounted for.

The tests check the request each SDK would send, offline: once against stubbed clients, and once with the real SDK clients on a mock HTTP transport, comparing the JSON body sent for each default model. Since 2026-11-17 every default model has also been run against the live API; what that found is in [the findings log](evaluation/findings.md).

### Files and page images

A request can carry attachments (`CompletionRequest.attachments`): a PDF, or a PNG, JPEG, GIF or WebP image. Gemini gets them as inline parts, Anthropic as `document` and `image` blocks, OpenAI as a `file` part (PDF) or an `image_url` data URL at `detail: "high"`. A `[[attachment:N]]` marker in the user prompt puts file N at that point, between the text around it; files without a marker go first.

### Model variants

`provider:model+key=value` changes one field of the model's row in the table above for a run, without a code change: `anthropic:claude-haiku-5-5+effort=medium`, `openai:gpt-6-luna+reasoning_effort=low`, `gemini:gemini-3.8-flash+thinking_level=medium`. The API gets the name before the first `+`, and the price table matches it the same way.

Sources, checked on 2026-11-03: OpenAI [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna), [GPT-6.1 Terra](https://developers.openai.com/api/docs/models/gpt-6.1-terra), [Using GPT-6](https://developers.openai.com/api/docs/guides/latest-model), [Reasoning](https://developers.openai.com/api/docs/guides/reasoning) and [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs); Anthropic [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs), [Steering thinking](https://platform.claude.com/docs/en/build-with-claude/thinking-steering-and-cost) and the [Claude Haiku 5.5 migration guide](https://platform.claude.com/docs/en/models/haiku-5-5/migration-guide); Google [Gemini 3.5 Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite), [What's new in Gemini 3.6 Flash and 3.5 Flash-Lite](https://ai.google.dev/gemini-api/docs/generate-content/whats-new-gemini-3.6), [Thinking](https://ai.google.dev/gemini-api/docs/thinking) and [Structured output](https://ai.google.dev/gemini-api/docs/structured-output); plus the installed SDKs (`openai` 3.42, `anthropic` 2.4, `google-genai` 2.34).

## Pricing

Prices come from [`src/docfunnel/extract/pricing.json`](../src/docfunnel/extract/pricing.json): standard list prices in USD per 1M tokens, copied from the official OpenAI, Anthropic and Google pricing pages on 2026-11-03. Each entry records its source URL and that date.

Where a provider charges more for long prompts, the entry has a `long_context` tier that applies to the whole call above the threshold (Claude Haiku 5.5 above 100K input tokens, GPT-6 models above 272K). Batch and cache discounts are not modelled. Prices change, so re-check the source pages, or point `DOCFUNNEL_PRICING_FILE` at your own table. Models missing from the table are reported with cost "unknown", never as $0.

## Adding a provider

1. Implement `LLMProvider.complete(CompletionRequest) -> CompletionResponse` in `providers/<name>_provider.py`, importing the SDK lazily (`get_provider` imports adapter modules only when selected) so the core stays dependency-free. Raise `ProviderError(retryable=...)` so the extractor can decide between backoff and fallback.
2. Add the models to `providers/capabilities.py` and prices to `extract/pricing.json` (with source URL and check date).
3. Register the name in `get_provider` and `DEFAULT_MODELS` in `providers/__init__.py`, and add an optional extra in `pyproject.toml`.
4. Add stubbed-client tests (`tests/providers/test_sdk_adapters.py`) and a wire test of the HTTP body (`tests/providers/test_http_wire.py`).
