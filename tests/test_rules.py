"""Threshold engine: golden cross-check, the branches the sample never exercises,
and strict-boundary behaviour."""

from qc_pipeline.config import Config
from qc_pipeline.metrics.golden import GOLDEN
from qc_pipeline.rules import evaluate, evaluate_thresholds

CFG = Config()


def _alert(total, major, minor):
    return evaluate("TEST", total, major, minor, CFG).alert


def test_rules_match_golden():
    """The engine's decision must equal the hand-derived expected_alert for all 12."""
    for code, g in GOLDEN.items():
        decision = evaluate(code, g.total_products, g.major, g.minor, CFG)
        assert decision.alert == g.expected_alert, (code, decision.reasons)


def test_only_na_chi_alerts_in_golden():
    alerting = {c for c, g in GOLDEN.items()
                if evaluate(c, g.total_products, g.major, g.minor, CFG).alert}
    assert alerting == {"NA-CHI-021"}


def test_na_chi_trips_minor_and_overall():
    g = GOLDEN["NA-CHI-021"]
    d = evaluate("NA-CHI-021", g.total_products, g.major, g.minor, CFG)
    assert d.alert
    joined = " ".join(d.reasons)
    assert "minor" in joined and "overall" in joined and "major" not in joined


# --- branches the sample data never exercises -------------------------------- #
def test_major_only_branch():
    # 150 / 10000 = 1.5% > 1% ; minor 0
    d = evaluate("M", 10_000, 150, 0, CFG)
    assert d.alert and any("major" in r for r in d.reasons)
    assert not any("minor" in r for r in d.reasons)


def test_overall_only_branch():
    # major 0.9% (<1%), minor 2.9% (<3%), overall 3.8% (>3.5%)
    d = evaluate("O", 1000, 9, 29, CFG)
    assert d.alert
    assert any("overall" in r for r in d.reasons)
    assert not any(r.startswith("major") for r in d.reasons)
    assert not any(r.startswith("minor") for r in d.reasons)


# --- strict ">" boundary: exactly on the line must NOT alert ----------------- #
def test_exactly_at_major_threshold_no_alert():
    assert _alert(10_000, 100, 0) is False   # exactly 1.00%


def test_exactly_at_minor_threshold_no_alert():
    assert _alert(1000, 0, 30) is False       # exactly 3.00%


def test_exactly_at_overall_threshold_no_alert():
    # major 10 (1.0%, not >1%) + minor 25 (2.5%, not >3%) => overall exactly 3.50%.
    # Neither individual rule trips, so this isolates the overall boundary.
    assert _alert(1000, 10, 25) is False


def test_just_over_thresholds_alert():
    assert _alert(10_000, 101, 0) is True     # major 1.01%
    assert _alert(10_000, 0, 301) is True     # minor 3.01%
    # overall-only just-over: major 1.0% (not >), minor 2.5% (not >), overall 3.6% (>3.5%)
    assert _alert(1000, 10, 26) is True


def test_zero_total_does_not_crash_or_alert():
    d = evaluate_thresholds("Z", 0, 5, 5,
                            major_threshold=0.01, minor_threshold=0.03, overall_threshold=0.035)
    assert d.alert is False and d.major_pct == 0.0
