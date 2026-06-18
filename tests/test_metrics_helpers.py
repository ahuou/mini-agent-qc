"""Unit tests for the stats helpers behind the metrics."""

from qc_pipeline.extraction.schema import DefectExtraction, ExtractedReport
from qc_pipeline.metrics.evaluation import _accuracy_block, _confusion, _percentile, _safe_div


def _rep(site, major, minor):
    return ExtractedReport(
        site_code=site, total_products=1000,
        extraction=DefectExtraction(
            major_defects=major, minor_defects=minor,
            major_confidence=0.9, minor_confidence=0.9,
            major_evidence="", minor_evidence=""),
        baseline_major=major, baseline_minor=minor, extractor="mock",
    )


def test_mae_is_absolute_not_signed():
    """NA-DEN-006 golden = major 7, minor 9. Over-read major by 3, under-read minor
    by 4: a signed sum would cancel to -0.5; absolute error must be (3+4)/2 = 3.5."""
    block = _accuracy_block([_rep("NA-DEN-006", 10, 5)], use_baseline=False)
    assert block["mean_absolute_error"] == (3 + 4) / 2


def test_percentile_basic():
    assert _percentile([10, 20, 30, 40, 50], 0.5) == 30
    assert _percentile([], 0.95) == 0.0
    assert _percentile([7], 0.5) == 7


def test_confusion_perfect():
    c = _confusion({"a": True, "b": False}, {"a": True, "b": False})
    assert c["tp"] == 1 and c["tn"] == 1 and c["fp"] == 0 and c["fn"] == 0
    assert c["precision"] == 1.0 and c["recall"] == 1.0 and c["f1"] == 1.0


def test_confusion_missed_alert():
    # predicted nothing, but one was expected -> recall 0
    c = _confusion({"a": False}, {"a": True})
    assert c["fn"] == 1 and c["recall"] == 0.0


def test_confusion_no_positives_defaults_precision_recall_one():
    c = _confusion({"a": False, "b": False}, {"a": False, "b": False})
    assert c["precision"] == 1.0 and c["recall"] == 1.0


def test_safe_div_guards_zero():
    assert _safe_div(1, 0) == 0.0
    assert _safe_div(1, 0, default=1.0) == 1.0
    assert _safe_div(3, 6) == 0.5
