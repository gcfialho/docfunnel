"""End-to-end evaluation on PDFs: the docfunnel route against native PDF input.

Answers the question the project exists for: does parsing on the CPU first, then
sending text to a small model, cost less than sending the PDF to the model, and at what
accuracy? See :mod:`docfunnel.evals.e2e.runner`.
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
