"""Text-similarity metrics for the parse stage: CER, WER and quote lookup."""

from __future__ import annotations


def normalize_whitespace(text: str) -> str:
    """Collapse every run of whitespace (including line breaks) to one space.

    CER and WER are measured on this form: the parse stage is judged on the
    characters it recovers and their order, not on how it splits lines or columns.
    """
    return " ".join(text.split())


def edit_counts(reference: str, hypothesis: str) -> tuple[int, int, int, int]:
    """``(char_edits, ref_chars, word_edits, ref_words)`` after whitespace normalization."""
    from rapidfuzz.distance import Levenshtein

    ref, hyp = normalize_whitespace(reference), normalize_whitespace(hypothesis)
    ref_words, hyp_words = ref.split(), hyp.split()
    return (
        Levenshtein.distance(ref, hyp),
        len(ref),
        Levenshtein.distance(ref_words, hyp_words),
        len(ref_words),
    )


def char_error_rate(reference: str, hypothesis: str) -> float:
    edits, chars, _, _ = edit_counts(reference, hypothesis)
    return edits / chars if chars else float(bool(normalize_whitespace(hypothesis)))


def word_error_rate(reference: str, hypothesis: str) -> float:
    _, _, edits, words = edit_counts(reference, hypothesis)
    return edits / words if words else float(bool(normalize_whitespace(hypothesis)))


def quote_found(quote: str, text: str) -> bool:
    """Does the printed value appear in the parsed text? Whitespace is ignored."""
    return "".join(quote.split()) in "".join(text.split())
