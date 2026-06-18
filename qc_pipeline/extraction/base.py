"""The pluggable extractor interface.

Every extractor reads one report's two audit-note fields and returns a
``DefectExtraction``. Swapping the LLM provider, the offline mock, or the naive
baseline is just a matter of choosing a different ``Extractor`` — the pipeline
doesn't care which one it holds.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from .schema import DefectExtraction


@dataclass
class CallMeta:
    """Per-call telemetry returned alongside an extraction (cost accounting)."""

    model: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cached: bool = False  # True if served from the extraction cache (no API call)


class Extractor(ABC):
    """Reads defect counts from a report's free-text audit notes."""

    #: Short stable identifier, surfaced in metrics ("mock", "llm", "baseline").
    name: str = "extractor"

    @abstractmethod
    def extract(
        self,
        major_note: str,
        minor_note: str,
        *,
        context: Optional[dict] = None,
    ) -> tuple[DefectExtraction, CallMeta]:
        """Return the structured extraction plus call telemetry.

        ``context`` may carry hints (e.g. site_code, total_products) but a
        well-behaved extractor must not *need* them — the counts live entirely
        in the free text.
        """
        raise NotImplementedError
