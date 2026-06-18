"""Extractors: the mock reads the real sample notes correctly; the naive baseline
demonstrably does not (that gap is the value of the LLM)."""

from qc_pipeline.config import DEFAULT_DATA_DIR
from qc_pipeline.extraction.baseline_extractor import NaiveBaselineExtractor
from qc_pipeline.extraction.mock_extractor import MockExtractor
from qc_pipeline.loader import load_reports
from qc_pipeline.metrics.golden import GOLDEN


def _notes_by_site():
    reports, errors = load_reports(DEFAULT_DATA_DIR)
    assert not errors, errors
    return {r.site_code: r for r in reports}


def test_mock_matches_golden_on_every_sample():
    mock = MockExtractor()
    notes = _notes_by_site()
    for code, g in GOLDEN.items():
        r = notes[code]
        extraction, _ = mock.extract(r.major_note, r.minor_note)
        assert extraction.major_defects == g.major, (code, "major", extraction.major_evidence)
        assert extraction.minor_defects == g.minor, (code, "minor", extraction.minor_evidence)


def test_baseline_misreads_the_trap():
    """The naive baseline reads '13 hundred' as 13 — the whole reason we need an LLM."""
    baseline = NaiveBaselineExtractor()
    r = _notes_by_site()["NA-CHI-021"]
    extraction, _ = baseline.extract(r.major_note, r.minor_note)
    assert extraction.minor_defects == 13            # wrong (golden is 1300)
    assert GOLDEN["NA-CHI-021"].minor == 1300


def test_extractors_share_the_interface():
    for ex in (MockExtractor(), NaiveBaselineExtractor()):
        extraction, meta = ex.extract("11 units failed", "None")
        assert extraction.major_defects == 11
        assert extraction.minor_defects == 0
        assert meta.model is None


def test_llm_extractor_roundtrips_with_injected_client():
    """The live path is exercised with a fake SDK client (no key, no network):
    structured output round-trips and token usage feeds the cost estimate."""
    from qc_pipeline.extraction.llm_extractor import LLMExtractor
    from qc_pipeline.extraction.schema import DefectExtraction
    from qc_pipeline.pipeline import _cost_usd

    class FakeUsage:
        input_tokens, output_tokens = 1000, 200

    class FakeResp:
        parsed_output = DefectExtraction(
            major_defects=0, minor_defects=1300,
            major_confidence=0.95, minor_confidence=0.9,
            major_evidence="No critical failures", minor_evidence="13 hundred")
        usage = FakeUsage()
        stop_reason = "end_turn"
        model = "claude-sonnet-4-6"   # the model the API reports it served

    class FakeMessages:
        def parse(self, **kwargs):
            assert kwargs["output_format"] is DefectExtraction   # forced structured output
            return FakeResp()

    class FakeClient:
        messages = FakeMessages()

    # Request one id; the fake API reports it served "claude-sonnet-4-6" -> meta
    # must reflect what actually ran (response.model), not just the request.
    ex = LLMExtractor(model="claude-opus-4-8", client=FakeClient())
    extraction, meta = ex.extract("No critical failures verified.", "13 hundred units")
    assert extraction.minor_defects == 1300
    assert meta.model == "claude-sonnet-4-6"      # from response.model, proving the served model
    assert meta.input_tokens == 1000 and meta.output_tokens == 200
    # 1000/1e6*$3 + 200/1e6*$15 = 0.006
    assert abs(_cost_usd(meta) - 0.006) < 1e-9
