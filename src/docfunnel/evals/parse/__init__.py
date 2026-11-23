"""Stage-level evaluation of the parse stage on the synthetic PDF set.

What is measured, per page, against ground truth from :mod:`docfunnel.datasets.pdfs`:

* **OCR routing**: precision, recall and accuracy of "this page needs OCR" (label:
  the page is a scanned image).
* **Text quality**: CER and WER after whitespace normalization, for digital pages
  and for scanned pages by noise level and OCR engine.
* **Field recall**: does the printed value of each labelled field appear in the
  parsed text of its gold page? This is what the LLM step can see at best.
* **Throughput**: text-layer pages/s in one process (pypdfium2 vs the ``pypdf``
  baseline, when installed), and the full pipeline in the page pool (pages/s,
  OCR pages/s, cold start, per-page OCR latency, peak worker memory). The hardware
  is recorded in the report because these numbers mean nothing without it.

``compare_parse_reports`` gates quality metrics in CI; throughput is reported but
not gated, except for one relative check inside the same job (pypdfium2 must stay
several times faster than pypdf on the same pages).
"""

from docfunnel.evals.parse.compare import (
    ParseComparison,
    ParseThresholds,
    compare_parse_reports,
    render_parse_comparison,
)
from docfunnel.evals.parse.models import ParseEvalReport
from docfunnel.evals.parse.report import (
    load_parse_report,
    render_parse_markdown,
    summary_rows,
    write_parse_report,
)
from docfunnel.evals.parse.runner import ParseEvalConfig, run_parse_eval

__all__ = [
    "ParseComparison",
    "ParseEvalConfig",
    "ParseEvalReport",
    "ParseThresholds",
    "compare_parse_reports",
    "load_parse_report",
    "render_parse_comparison",
    "render_parse_markdown",
    "run_parse_eval",
    "summary_rows",
    "write_parse_report",
]
