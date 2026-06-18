"""Extraction layer: turn free-text audit notes into structured defect counts.

- ``base.Extractor``     — the pluggable interface every extractor implements.
- ``mock_extractor``     — deterministic, offline, robust (backs all $0 runs/tests).
- ``llm_extractor``      — real Anthropic structured-output extraction (live mode).
- ``baseline_extractor`` — deliberately naive rule reader, used as a cross-check.
"""
