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
from docfunnel.extractor import MAX_DOCUMENT_CHARS, Extractor
from docfunnel.loaders import UnsupportedDocumentError, load_document
from docfunnel.schema import ExtractionResult
from docfunnel.service import get_extractor, get_settings

app = FastAPI(
    title="LLM document extraction",
    version=__version__,
    description="Schema-constrained extraction of receipts and invoices with review routing.",
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
        raise HTTPException(status.HTTP_403_FORBIDDEN, "path escapes the input directory")
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
        try:
            text = load_document(_resolve_input(request.path, settings))
        except UnsupportedDocumentError as exc:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    else:
        text = request.text or ""
    try:
        return extractor.extract(text)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
