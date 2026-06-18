"""Data shapes shared across the extraction layer.

``DefectExtraction`` is the *contract* a structured-output extractor must
satisfy — the LLM is forced to return exactly this shape. ``ExtractedReport``
is the richer, downstream record the pipeline assembles per report (primary
extraction + naive-baseline cross-check + timing/cost/review metadata).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel, Field


class DefectExtraction(BaseModel):
    """Structured result of reading one report's free-text audit notes.

    A single extractor call fills this in for one inspection report. Counts are
    absolute unit counts (NOT percentages). Confidences are the extractor's own
    certainty in each count, in [0, 1]. Evidence quotes the snippet the count
    was derived from, which makes every number auditable by a human.
    """

    major_defects: int = Field(
        ge=0,
        description="Number of MAJOR/critical defective units. 0 if the notes "
        "state no critical defects were found.",
    )
    minor_defects: int = Field(
        ge=0,
        description="Number of MINOR/cosmetic defective units. 0 if the notes "
        "state none were found.",
    )
    major_confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence in the major_defects count, 0-1.",
    )
    minor_confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence in the minor_defects count, 0-1.",
    )
    major_evidence: str = Field(
        description="Exact snippet of the audit note the major count came from.",
    )
    minor_evidence: str = Field(
        description="Exact snippet of the audit note the minor count came from.",
    )


@dataclass
class ExtractedReport:
    """Everything the pipeline knows about one report after extraction.

    Carries the trusted *primary* extraction (LLM in live mode, deterministic
    mock offline), the independent *naive baseline* counts used as a cross-check,
    and the operational metadata the metrics layer needs.
    """

    site_code: str
    total_products: int
    extraction: DefectExtraction          # the trusted, primary reading
    baseline_major: int                   # naive rule-based second opinion
    baseline_minor: int
    extractor: str                        # "mock" | "llm"
    model: Optional[str] = None           # concrete model id, live mode only
    source: str = ""                      # source filename (for the report viewer)
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    cached: bool = False                   # served from the extraction cache (no API call)
    error: Optional[str] = None           # populated if extraction failed

    # Filled in by the confidence logic (pipeline.py):
    needs_review: bool = False
    review_reasons: list[str] = field(default_factory=list)

    @property
    def major(self) -> int:
        return self.extraction.major_defects

    @property
    def minor(self) -> int:
        return self.extraction.minor_defects

    @property
    def baseline_agrees(self) -> bool:
        """True iff the naive baseline matches the primary reading on both counts."""
        return (
            self.baseline_major == self.major
            and self.baseline_minor == self.minor
        )
