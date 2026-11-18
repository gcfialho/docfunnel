"""An accounts-payable inbox: extract every invoice in a folder, accept or queue for review.

Each document gets validated JSON and a review decision. Accepted invoices go to
``accepted.csv``, ready to import; the rest go to ``review.jsonl`` with the reasons a
person should look at them (totals that do not add up, missing line items, low
confidence, invalid output). The run prints what it cost.

Offline, with the deterministic ``fake`` provider (no key, not a real model)::

    uv run python examples/invoice_inbox.py examples/

With a real model, page images and OCR text for scanned pages::

    export OPENAI_API_KEY=...
    uv run python examples/invoice_inbox.py examples/ --provider openai --route hybrid-ocr
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import docfunnel
from docfunnel.config import Settings
from docfunnel.inputs import ROUTES, parse_route

SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".txt"}
COLUMNS = ["file", "vendor_name", "vendor_tax_id", "document_number", "date", "currency"]
COLUMNS += ["subtotal", "tax", "total", "line_items"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("inbox", type=Path, help="folder of invoices and receipts")
    parser.add_argument("--out", type=Path, default=Path("inbox-out"), help="output folder")
    parser.add_argument("--provider", help="openai, anthropic, gemini, ollama or fake")
    parser.add_argument("--model", help="model name (default: the provider's default)")
    parser.add_argument("--route", default="text", choices=ROUTES, help="what the model reads")
    args = parser.parse_args()

    settings = Settings.from_env().with_overrides(
        provider=args.provider, model=args.model, route=parse_route(args.route)
    )
    files = sorted(p for p in args.inbox.iterdir() if p.suffix.lower() in SUFFIXES)
    args.out.mkdir(parents=True, exist_ok=True)
    accepted, queued, cost = 0, 0, 0.0
    models: set[str] = set()

    with (
        (args.out / "accepted.csv").open("w", newline="") as accepted_file,
        (args.out / "review.jsonl").open("w") as review_file,
    ):
        writer = csv.DictWriter(accepted_file, fieldnames=COLUMNS)
        writer.writeheader()
        for path in files:
            result = docfunnel.extract_document(path, settings=settings)
            cost += result.usage.cost_usd or 0.0
            models.add(f"{result.provider}:{result.model}")
            doc = result.document
            if result.needs_review or doc is None:
                queued += 1
                entry = {"file": path.name, "reasons": result.review_reasons}
                entry["extracted"] = doc.model_dump(mode="json") if doc else None
                review_file.write(json.dumps(entry) + "\n")
                print(f"  review  {path.name}: {', '.join(result.review_reasons)}")
                continue
            accepted += 1
            row = doc.model_dump(mode="json", include=set(COLUMNS))
            writer.writerow({**row, "file": path.name, "line_items": len(doc.line_items)})
            print(f"  accept  {path.name}: {doc.vendor_name}, {doc.total} {doc.currency}")

    print(
        f"{len(files)} documents: {accepted} accepted, {queued} sent to review; "
        f"model cost ${cost:.4f} ({', '.join(sorted(models))}; route {settings.route})"
    )
    print(f"Wrote {args.out}/accepted.csv and {args.out}/review.jsonl")


if __name__ == "__main__":
    main()
