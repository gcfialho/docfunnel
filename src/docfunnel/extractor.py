"""The extraction pipeline: prompt -> LLM -> parse -> validate -> retry/repair -> fallback.

Failure handling, from cheapest to most expensive:

1. Harmless formatting deviations (markdown fences, prose around the JSON) are fixed
   in code by :func:`docfunnel.prompts.parse_json_object`.
2. Invalid JSON or schema violations trigger a *repair* turn: the model sees its own
   answer plus the concrete validation errors and is asked to fix them.
3. Transient provider errors (429/5xx/timeouts) are retried with exponential backoff
   and jitter; non-retryable errors skip straight to the next model.
4. When a model exhausts its attempts, the next target in the fallback chain is tried.
5. If everything fails, the result is returned with ``document=None`` and
   ``needs_review=True`` - the pipeline never raises on bad model output.

Business-rule violations do *not* trigger retries: they describe the document, not
the model, and are routed to human review instead.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TypedDict

from pydantic import ValidationError

from docfunnel.pricing import PriceTable
from docfunnel.prompts import (
    OutputParseError,
    format_validation_errors,
    parse_json_object,
    repair_prompt,
    system_prompt,
    user_prompt,
)
from docfunnel.providers.base import (
    CompletionRequest,
    LLMProvider,
    Message,
    ProviderError,
)
from docfunnel.schema import (
    CallPurpose,
    CallRecord,
    CallStatus,
    ExtractionResult,
    ReceiptExtraction,
    UsageSummary,
)
from docfunnel.validation import ReviewPolicy, check_business_rules, review_decision

logger = logging.getLogger(__name__)

MAX_DOCUMENT_CHARS = 30_000


@dataclass(frozen=True)
class ModelTarget:
    provider: LLMProvider
    model: str

    @property
    def label(self) -> str:
        return f"{self.provider.name}:{self.model}"


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    backoff_base_s: float = 0.5
    backoff_max_s: float = 8.0

    def delay(self, retry_number: int, rng: random.Random) -> float:
        """Exponential backoff with "equal jitter" for the n-th retry (1-based)."""
        if self.backoff_base_s <= 0:
            return 0.0
        ceiling = min(self.backoff_max_s, self.backoff_base_s * 2.0 ** (retry_number - 1))
        return ceiling / 2 + rng.uniform(0, ceiling / 2)


class _ResponseUsage(TypedDict):
    """What a provider reported for one successful call, as ``_record`` keyword arguments."""

    input_tokens: int
    output_tokens: int
    model: str


@dataclass
class _Attempt:
    """Mutable state for one model in the fallback chain."""

    messages: list[Message]
    retries: int = 0
    calls: list[CallRecord] = field(default_factory=list)


class Extractor:
    def __init__(
        self,
        targets: Sequence[ModelTarget],
        *,
        retry: RetryPolicy | None = None,
        review: ReviewPolicy | None = None,
        prices: PriceTable | None = None,
        max_output_tokens: int = 2048,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.perf_counter,
        rng: random.Random | None = None,
    ) -> None:
        if not targets:
            raise ValueError("at least one model target is required")
        self.targets = list(targets)
        self.retry = retry or RetryPolicy()
        self.review = review or ReviewPolicy()
        self.prices = prices or PriceTable.load()
        self.max_output_tokens = max_output_tokens
        self._sleep = sleep
        self._clock = clock
        self._rng = rng or random.Random()

    def extract(self, text: str) -> ExtractionResult:
        if not text or not text.strip():
            raise ValueError("document text is empty")
        if len(text) > MAX_DOCUMENT_CHARS:
            raise ValueError(f"document exceeds {MAX_DOCUMENT_CHARS} characters")

        calls: list[CallRecord] = []
        started = self._clock()
        base = [Message("system", system_prompt()), Message("user", user_prompt(text))]

        for index, target in enumerate(self.targets):
            document = self._run_target(target, list(base), calls)
            if document is not None:
                return self._finish(document, target, calls, started, used_fallback=index > 0)
            logger.warning(
                "target %s exhausted; %s",
                target.label,
                "falling back" if index + 1 < len(self.targets) else "giving up",
            )

        return self._finish(None, None, calls, started, used_fallback=len(self.targets) > 1)

    def _run_target(
        self, target: ModelTarget, messages: list[Message], calls: list[CallRecord]
    ) -> ReceiptExtraction | None:
        for attempt in range(1, self.retry.max_attempts + 1):
            if attempt > 1:
                self._sleep(self.retry.delay(attempt - 1, self._rng))
            purpose: CallPurpose = "repair" if len(messages) > 2 else "extract"
            request = CompletionRequest(
                model=target.model,
                messages=tuple(messages),
                max_output_tokens=self.max_output_tokens,
            )
            t0 = self._clock()
            try:
                response = target.provider.complete(request)
            except ProviderError as exc:
                calls.append(
                    self._record(target, attempt, purpose, "provider_error", t0, error=str(exc))
                )
                if not exc.retryable:
                    return None
                continue

            record: _ResponseUsage = {
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "model": response.model,
            }
            try:
                data = parse_json_object(response.text)
                document = ReceiptExtraction.model_validate(data)
            except OutputParseError as exc:
                calls.append(
                    self._record(
                        target, attempt, purpose, "invalid_json", t0, error=str(exc), **record
                    )
                )
                errors = [f"output is not a valid JSON object ({exc})"]
            except ValidationError as exc:
                errors = format_validation_errors(exc)
                calls.append(
                    self._record(
                        target,
                        attempt,
                        purpose,
                        "schema_error",
                        t0,
                        error="; ".join(errors),
                        **record,
                    )
                )
            else:
                calls.append(self._record(target, attempt, purpose, "ok", t0, **record))
                return document

            messages = [
                *messages[:2],
                Message("assistant", response.text),
                Message("user", repair_prompt(response.text, errors)),
            ]
        return None

    def _record(
        self,
        target: ModelTarget,
        attempt: int,
        purpose: CallPurpose,
        status: CallStatus,
        t0: float,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        model: str | None = None,
        error: str | None = None,
    ) -> CallRecord:
        latency_ms = (self._clock() - t0) * 1000
        record = CallRecord(
            provider=target.provider.name,
            model=model or target.model,
            attempt=attempt,
            purpose=purpose,
            status=status,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=self.prices.cost(target.model, input_tokens, output_tokens),
            latency_ms=round(latency_ms, 3),
            error=error,
        )
        logger.info("llm_call %s", record.model_dump_json(exclude={"error"}))
        return record

    def _finish(
        self,
        document: ReceiptExtraction | None,
        target: ModelTarget | None,
        calls: list[CallRecord],
        started: float,
        *,
        used_fallback: bool,
    ) -> ExtractionResult:
        issues = check_business_rules(document, self.review) if document else []
        needs_review, reasons = review_decision(document, issues, self.review)
        known_costs = [c.cost_usd for c in calls if c.cost_usd is not None]
        usage = UsageSummary(
            calls=len(calls),
            input_tokens=sum(c.input_tokens for c in calls),
            output_tokens=sum(c.output_tokens for c in calls),
            # One unpriced call makes the total unknown rather than silently too low.
            cost_usd=round(sum(known_costs), 8) if len(known_costs) == len(calls) else None,
            latency_ms=round((self._clock() - started) * 1000, 3),
        )
        return ExtractionResult(
            document=document,
            schema_valid=document is not None,
            needs_review=needs_review,
            review_reasons=reasons,
            issues=issues,
            provider=target.provider.name if target else None,
            model=target.model if target else None,
            attempts=len(calls),
            used_fallback=used_fallback,
            first_attempt_schema_valid=bool(calls) and calls[0].status == "ok",
            usage=usage,
            calls=calls,
        )
