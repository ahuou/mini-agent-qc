"""Live extraction via the Anthropic API using structured outputs.

The model is *forced* to return a ``DefectExtraction`` (validated against the
Pydantic schema by ``messages.parse``), so we never hand-parse free-form text.
The prompt teaches general natural-language number reading — it does NOT mention
the sample reports, so the extractor generalises rather than overfitting.

Configuration skeleton (no key needed for mock mode):
    export ANTHROPIC_API_KEY=sk-ant-...      # read automatically by the SDK
    python -m qc_pipeline --mode live --tier balanced

``anthropic`` is imported lazily inside ``__init__`` so the package imports and
runs in mock mode even when the SDK is not installed.
"""

from __future__ import annotations

from typing import Optional

from ..config import Config
from .base import CallMeta, Extractor
from .schema import DefectExtraction

_SYSTEM_PROMPT = """\
You read quality-assurance audit notes from a manufacturing line and report how \
many units were found defective. You will be given two free-text notes for one \
production run: one about MAJOR (critical/functional) defects and one about MINOR \
(cosmetic/non-functional) defects.

For each note, return the integer COUNT OF DEFECTIVE UNITS it describes:
- Read natural-language quantities exactly, composing compound numbers: \
"a dozen" = 12, "half a dozen" = 6, "a single unit" = 1, "a couple" = 2, \
"sixty five" = 65, "two hundred and fifty" = 250, and multiplier phrases like \
"a hundred" = 100, "nineteen hundred" = 1900, "two thousand" = 2000, "1.5k" = 1500.
- If the note states no defects were found (e.g. "none", "no critical failures", \
"did not find any", "0 critical defects"), the count is 0.
- Report the number of DEFECTIVE units, not totals, yields, or unrelated figures.
- Notes vary widely in wording and may contain typos; reason about meaning, do \
not pattern-match fixed phrases.

Also report a confidence in [0,1] for each count (1.0 = the note is explicit and \
unambiguous; lower it when the wording is vague, e.g. "several", "a few"), and \
quote the exact snippet you based each count on as evidence.
"""


class LLMExtractor(Extractor):
    name = "llm"

    def __init__(self, model: str, client=None, api_key: Optional[str] = None):
        self.model = model
        if client is None:
            import anthropic  # lazy: only required for live mode
            # Bound per-call time so one slow/hung request can't stall a whole run
            # (the SDK default read timeout is 10 min). api_key=None -> SDK reads
            # ANTHROPIC_API_KEY from the environment.
            kwargs = {"timeout": 60.0, "max_retries": 1}
            if api_key:
                kwargs["api_key"] = api_key
            client = anthropic.Anthropic(**kwargs)
        self._client = client

    @classmethod
    def from_config(cls, config: Config, api_key: Optional[str] = None) -> "LLMExtractor":
        return cls(model=config.model_id, api_key=api_key)

    def extract(
        self,
        major_note: str,
        minor_note: str,
        *,
        context: Optional[dict] = None,
    ) -> tuple[DefectExtraction, CallMeta]:
        user = (
            "Extract the defect counts from this production run's audit notes.\n\n"
            f"MAJOR defects note:\n{major_note!r}\n\n"
            f"MINOR defects note:\n{minor_note!r}"
        )
        response = self._client.messages.parse(
            model=self.model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user}],
            output_format=DefectExtraction,
        )
        extraction = response.parsed_output
        if extraction is None:
            raise RuntimeError(
                f"extraction failed (stop_reason={getattr(response, 'stop_reason', '?')})"
            )
        usage = getattr(response, "usage", None)
        meta = CallMeta(
            # Report the model the API actually served (proves which model ran),
            # falling back to the requested id if the field is absent.
            model=getattr(response, "model", None) or self.model,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
        )
        return extraction, meta
