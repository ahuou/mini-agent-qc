"""A deliberately naive, rules-only extractor used as an independent cross-check.

This is what you get *without* an LLM: grab the first integer you see, fall back
to a tiny word table, otherwise assume zero. It is intentionally not robust — it
reads "13 hundred" as **13** and "a hundred" as **1** — and that is the point.

Comparing the trusted extractor against this naive reader gives us, for free:
  * a confidence signal — disagreement flags a report for human review, and
  * a quantified value-of-the-LLM number in the metrics (the LLM catches the
    breaches this baseline silently misses).

It must never be the primary extractor; it exists to be disagreed with.
"""

from __future__ import annotations

import re
from typing import Optional

from .base import CallMeta, Extractor
from .schema import DefectExtraction

_FIRST_INT = re.compile(r"\d+")
_ABSENCE = re.compile(r"\b(no|none|not|without|nil|never|zero)\b")
_DOZEN = re.compile(r"\bdozen\b")
_ARTICLE = re.compile(r"\b(a|an|one)\b")


def _naive_count(note: str) -> tuple[int, float, str]:
    """First-integer-wins parsing. Returns (count, confidence, evidence)."""
    if not note:
        return 0, 0.3, ""
    t = note.lower()
    if (m := _FIRST_INT.search(t)):
        # Grabs the leading digits only — no multiplier awareness, so
        # "13 hundred" collapses to 13 and "1,300" collapses to 1.
        return int(m.group()), 0.80, m.group()
    if _ABSENCE.search(t):
        return 0, 0.70, "absence"
    if _DOZEN.search(t):           # knows "dozen" == 12 but not "half a dozen"
        return 12, 0.50, "dozen"
    if _ARTICLE.search(t):         # "a single unit" -> 1, but also "a hundred" -> 1
        return 1, 0.40, "a"
    return 0, 0.30, ""


class NaiveBaselineExtractor(Extractor):
    name = "baseline"

    def extract(
        self,
        major_note: str,
        minor_note: str,
        *,
        context: Optional[dict] = None,
    ) -> tuple[DefectExtraction, CallMeta]:
        maj, maj_c, maj_e = _naive_count(major_note)
        minr, min_c, min_e = _naive_count(minor_note)
        return (
            DefectExtraction(
                major_defects=maj,
                minor_defects=minr,
                major_confidence=maj_c,
                minor_confidence=min_c,
                major_evidence=maj_e,
                minor_evidence=min_e,
            ),
            CallMeta(model=None),
        )
