"""End-to-end evaluation on PDFs: what the model is sent, against accuracy and cost.

Answers the question the project exists for: should a model get the parse stage's text,
the PDF itself, or page images (with or without their OCR text), and what does each
cost? See :mod:`docfunnel.evals.e2e.runner`; committed runs are indexed and charted by
:mod:`docfunnel.evals.e2e.summary`.
"""

from docfunnel.evals.e2e.dataset import E2EDoc, build_e2e_set, load_e2e_set
from docfunnel.evals.e2e.report import load_e2e_report, render_e2e_markdown, write_e2e_report
from docfunnel.evals.e2e.runner import (
    DEFAULT_ROUTES,
    ROUTES,
    E2EConfig,
    E2EReport,
    E2ERow,
    run_e2e,
)

__all__ = [
    "DEFAULT_ROUTES",
    "ROUTES",
    "E2EConfig",
    "E2EDoc",
    "E2EReport",
    "E2ERow",
    "build_e2e_set",
    "load_e2e_report",
    "load_e2e_set",
    "render_e2e_markdown",
    "run_e2e",
    "write_e2e_report",
]
