import json

from docfunnel.evals.dataset import load_dataset
from docfunnel.schema import ReceiptExtraction
from docfunnel.synthetic import generate, ocr_noise
from docfunnel.validation import check_business_rules

from helpers import DATASET


def test_generation_is_deterministic() -> None:
    first = [s.to_json() for s in generate(n=20, seed=1)]
    second = [s.to_json() for s in generate(n=20, seed=1)]
    assert first == second
    assert first != [s.to_json() for s in generate(n=20, seed=2)]


def test_committed_dataset_matches_generator() -> None:
    """Guards against hand-edits of the bundled dataset drifting from its generator."""
    committed = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines()]
    assert committed == [s.to_json() for s in generate()]


def test_dataset_covers_the_interesting_cases() -> None:
    docs = load_dataset(DATASET)
    tags = {(d.tags["layout"], d.tags["variant"]) for d in docs}
    assert {d.tags["locale"] for d in docs} == {"us", "uk", "de", "br"}
    assert {"pos", "invoice", "minimal"} == {layout for layout, _ in tags}
    assert {"clean", "ocr_noise", "misprinted"} == {variant for _, variant in tags}
    # Absent fields are what make hallucination measurable.
    assert any(d.label.vendor_tax_id is None for d in docs)
    assert any(d.label.tax is None for d in docs)


def test_labels_obey_business_rules_unless_misprinted() -> None:
    for doc in load_dataset(DATASET):
        label = ReceiptExtraction.model_validate(doc.label.model_dump())
        errors = [i for i in check_business_rules(label) if i.severity == "error"]
        assert bool(errors) == doc.expected_review, (doc.id, errors)


def test_ocr_noise_changes_text_but_keeps_line_structure() -> None:
    import random

    text = "TOTAL  $10.00\nSubtotal  $9.00\n" * 20
    noisy = ocr_noise(text, random.Random(0), rate=0.3)
    assert noisy != text
    assert noisy.count("\n") == text.rstrip("\n").count("\n")
