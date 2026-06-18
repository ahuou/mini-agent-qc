"""Loader: parses all 12 samples, pulls the right fields, and degrades gracefully."""

import json

import pytest

from qc_pipeline.config import DEFAULT_DATA_DIR
from qc_pipeline.loader import ReportParseError, load_report, load_reports


def test_loads_all_twelve_samples():
    reports, errors = load_reports(DEFAULT_DATA_DIR)
    assert len(reports) == 12
    assert errors == []


def test_pulls_expected_fields():
    reports, _ = load_reports(DEFAULT_DATA_DIR)
    by_site = {r.site_code: r for r in reports}
    chi = by_site["NA-CHI-021"]
    assert chi.total_products == 6100
    assert "13 hundred" in chi.minor_note
    assert by_site["EU-BER-002"].total_products == 7800


def test_malformed_json_raises(tmp_path):
    bad = tmp_path / "broken.json"
    bad.write_text("{ not valid json ", encoding="utf-8")
    with pytest.raises(ReportParseError):
        load_report(bad)


def test_missing_field_raises(tmp_path):
    incomplete = tmp_path / "incomplete.json"
    incomplete.write_text(json.dumps({"header": {}}), encoding="utf-8")
    with pytest.raises(ReportParseError):
        load_report(incomplete)


_GOOD = {
    "header": {"facility_data": {"site_code": "X-1"}},
    "production_run": {"batch_statistics": {"total_products": 100}},
    "quality_assurance": {"human_audit_layer": {"audit_notes": {
        "major_defects_comments": "None", "minor_defects_comments": "5 units"}}},
}


def test_load_reports_collects_errors_without_crashing(tmp_path):
    (tmp_path / "ok.json").write_text(json.dumps(_GOOD), encoding="utf-8")
    (tmp_path / "bad.json").write_text("nonsense", encoding="utf-8")
    reports, errors = load_reports(tmp_path)
    assert len(reports) == 1 and len(errors) == 1


def test_non_dict_audit_notes_is_coverage_gap_not_crash(tmp_path):
    """A non-object audit_notes must become a recorded error, not crash the run."""
    (tmp_path / "ok.json").write_text(json.dumps(_GOOD), encoding="utf-8")
    weird = dict(_GOOD)
    weird["quality_assurance"] = {"human_audit_layer": {"audit_notes": "oops not an object"}}
    (tmp_path / "weird.json").write_text(json.dumps(weird), encoding="utf-8")
    reports, errors = load_reports(tmp_path)  # must NOT raise
    assert len(reports) == 1 and len(errors) == 1


def test_non_dict_facility_raises_parse_error(tmp_path):
    p = tmp_path / "f.json"
    bad = dict(_GOOD)
    bad["header"] = {"facility_data": "nope"}
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ReportParseError):
        load_report(p)


def test_bool_total_products_rejected(tmp_path):
    p = tmp_path / "b.json"
    bad = dict(_GOOD)
    bad["production_run"] = {"batch_statistics": {"total_products": True}}
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ReportParseError):
        load_report(p)
