"""HTTP API (FastAPI).

``POST /extract`` accepts either inline ``text`` or a ``path`` to a file inside the
directory configured by ``DOCFUNNEL_INPUT_DIR`` (disabled when unset, so the API
cannot be used to read arbitrary files from the host).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Self

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from docfunnel import __version__
from docfunnel.config import Settings
from docfunnel.extract.extractor import MAX_DOCUMENT_CHARS, Extractor
from docfunnel.extract.schema import ExtractionResult
from docfunnel.inputs import ModelInput, Route, build_input
from docfunnel.loaders import UnsupportedDocumentError
from docfunnel.service import get_extractor, get_settings

app = FastAPI(
    title="docfunnel",
    version=__version__,
    description=(
        "Schema-validated LLM extraction of receipts and invoices, with business-rule "
        "checks and human-review routing. Text, PDF and image input go through the "
        "CPU parse stage first."
    ),
)


class ExtractRequest(BaseModel):
    text: str | None = Field(
        default=None,
        max_length=MAX_DOCUMENT_CHARS,
        description="Raw document text (e.g. OCR output).",
    )
    path: str | None = Field(
        default=None, description="File (txt/pdf/image) relative to DOCFUNNEL_INPUT_DIR."
    )
    route: Route | None = Field(
        default=None,
        description="What the model is sent for a file: text, hybrid, hybrid-ocr or native. "
        "Defaults to DOCFUNNEL_ROUTE (text).",
    )

    @model_validator(mode="after")
    def _exactly_one_input(self) -> Self:
        if (self.text is None) == (self.path is None):
            raise ValueError("provide exactly one of 'text' or 'path'")
        return self


class Health(BaseModel):
    status: str
    version: str
    provider: str
    model: str


def _resolve_input(path: str, settings: Settings) -> Path:
    if settings.input_dir is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "file input is disabled; set DOCFUNNEL_INPUT_DIR to enable it",
        )
    root = settings.input_dir.resolve()
    candidate = (root / path).resolve()
    if not candidate.is_relative_to(root):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "path must stay inside DOCFUNNEL_INPUT_DIR")
    if not candidate.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"file not found: {path}")
    return candidate


@app.get("/health")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> Health:
    provider, model = settings.primary
    return Health(status="ok", version=__version__, provider=provider, model=model)


@app.post("/extract")
def extract(
    request: ExtractRequest,
    extractor: Annotated[Extractor, Depends(get_extractor)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ExtractionResult:
    if request.path is not None:
        path = _resolve_input(request.path, settings)
        try:
            model_input = build_input(path, request.route or settings.route)
        except UnsupportedDocumentError as exc:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    else:
        model_input = ModelInput(request.text or "")
    try:
        return extractor.extract(model_input.text, attachments=model_input.attachments)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
