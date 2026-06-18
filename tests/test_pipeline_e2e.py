"""End-to-end: the offline mock run must catch exactly the one real breach,
need no API key, read 100% correctly, and show the naive baseline missing it."""

import json

import pytest

from qc_pipeline.config import Config
from qc_pipeline.pipeline import run_pipeline


@pytest.fixture
def metrics(tmp_path, monkeypatch):
    # Prove the offline path needs no credentials whatsoever.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg = Config(mode="mock", results_dir=tmp_path)
    return run_pipeline(cfg), tmp_path


def test_runs_without_api_key_and_writes_results(metrics):
    m, tmp_path = metrics
    results_file = tmp_path / "results.json"
    assert results_file.exists()
    json.loads(results_file.read_text())  # valid JSON
    assert m["run"]["n_reports"] == 12


def test_exactly_na_chi_alerts(metrics):
    m, _ = metrics
    assert m["alert_quality"]["predicted_alert_sites"] == ["NA-CHI-021"]
    assert m["alert_quality"]["expected_alert_sites"] == ["NA-CHI-021"]


def test_primary_reads_everything_correctly(metrics):
    m, _ = metrics
    p = m["extraction_quality"]["primary"]
    assert p["field_accuracy"] == 1.0
    assert p["report_accuracy"] == 1.0
    assert p["mean_absolute_error"] == 0.0


def test_alert_decision_is_perfect(metrics):
    m, _ = metrics
    ap = m["alert_quality"]["primary"]
    assert ap["precision"] == 1.0 and ap["recall"] == 1.0
    assert ap["fp"] == 0 and ap["fn"] == 0 and ap["tp"] == 1


def test_naive_baseline_would_miss_the_breach(metrics):
    m, _ = metrics
    # Lower reading accuracy AND it fails to fire the one alert.
    assert m["extraction_quality"]["baseline"]["field_accuracy"] < 1.0
    assert m["alert_quality"]["baseline"]["recall"] == 0.0
    assert m["extraction_quality"]["llm_value"]["baseline_missed_alert_sites"] == ["NA-CHI-021"]


def test_breach_is_flagged_for_human_review(metrics):
    m, _ = metrics
    assert "NA-CHI-021" in m["confidence_and_review"]["flagged_sites"]


def test_full_coverage(metrics):
    m, _ = metrics
    assert m["coverage"]["coverage_rate"] == 1.0
    assert m["coverage"]["extraction_errors"] == 0


def test_metrics_are_about_the_tool_not_defect_rates(metrics):
    m, _ = metrics
    # The headline sections measure the agent's performance.
    for section in ("extraction_quality", "alert_quality", "confidence_and_review",
                    "performance", "cost", "coverage", "stakeholder_summary"):
        assert section in m
    assert m["cost"]["total_usd"] == 0.0  # mock is free


def test_unread_breach_is_a_miss_not_a_perfect_run(tmp_path, monkeypatch):
    """Safety-critical: if extraction fails on the ONE breaching report, it must be
    scored as a false negative (recall < 1) and flagged — never silently as 100%."""
    from qc_pipeline.extraction.base import Extractor
    from qc_pipeline.extraction.mock_extractor import MockExtractor

    class RaiseOnBreach(Extractor):
        name = "mock"
        _mock = MockExtractor()

        def extract(self, major_note, minor_note, *, context=None):
            if context and context.get("site_code") == "NA-CHI-021":
                raise RuntimeError("simulated extraction failure on the breach")
            return self._mock.extract(major_note, minor_note, context=context)

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("qc_pipeline.pipeline.make_extractor", lambda config: RaiseOnBreach())
    m = run_pipeline(Config(mode="mock", results_dir=tmp_path))

    assert m["coverage"]["extraction_errors"] == 1
    assert m["coverage"]["coverage_rate"] < 1.0
    ap = m["alert_quality"]["primary"]
    assert ap["fn"] == 1 and ap["recall"] == 0.0          # the unread breach is a miss
    assert "NA-CHI-021" not in m["alert_quality"]["predicted_alert_sites"]
    assert "NA-CHI-021" in m["confidence_and_review"]["flagged_sites"]
    assert "unread" in m["stakeholder_summary"]            # surfaced to the reader
