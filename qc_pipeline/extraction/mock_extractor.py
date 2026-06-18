"""Deterministic, offline stand-in for the LLM extractor.

This is what makes the whole pipeline runnable with **no API key and zero cost**
— it backs every test and the default ``--mode mock`` run. It is *not* a lookup
table of the 12 sample answers (that would overfit); it runs the same robust
natural-language parser (``number_words.parse_count``) the brief asks an LLM to
emulate, so it generalises to unseen phrasings exactly as the live path would.

Think of it as "the model, frozen": same interface, same output shape, fully
reproducible.
"""

from __future__ import annotations

from typing import Optional

from .base import CallMeta, Extractor
from .number_words import parse_count
from .schema import DefectExtraction


class MockExtractor(Extractor):
    name = "mock"

    def extract(
        self,
        major_note: str,
        minor_note: str,
        *,
        context: Optional[dict] = None,
    ) -> tuple[DefectExtraction, CallMeta]:
        major = parse_count(major_note)
        minor = parse_count(minor_note)
        return (
            DefectExtraction(
                major_defects=major.value,
                minor_defects=minor.value,
                major_confidence=major.confidence,
                minor_confidence=minor.confidence,
                major_evidence=_evidence(major, major_note),
                minor_evidence=_evidence(minor, minor_note),
            ),
            CallMeta(model=None),
        )


def _evidence(parse, note: str) -> str:
    """Show the matched span for explicit counts; the whole note for absences /
    no-match, where a bare token like 'no' would be cryptic to a reader."""
    if parse.method in ("absence", "none_found", "empty") or len(parse.evidence) < 3:
        return note.strip()[:120] or "(empty note)"
    return parse.evidence
