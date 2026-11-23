"""Stage-level evaluations and their regression gates.

* :mod:`~docfunnel.evals.extract`: the LLM step on the labelled receipt dataset
  (field accuracy, hallucination, review precision/recall, cost, latency).
* :mod:`~docfunnel.evals.parse`: the parse stage on the synthetic PDF set
  (OCR routing, CER/WER, field recall, throughput).
* :mod:`~docfunnel.evals.gate`, :mod:`~docfunnel.evals.stats`,
  :mod:`~docfunnel.evals.text`, :mod:`~docfunnel.evals.formatting`: shared pieces.
"""
