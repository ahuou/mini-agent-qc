"""Discover and parse inspection-report JSON files.

The JSON *structure* is stable across reports (only the free text varies), so we
navigate to the known fields but do so defensively: a malformed or incomplete
file raises ``ReportParseError`` for that one path, which the pipeline records as
a coverage gap rather than letting it crash the whole run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


class ReportParseError(ValueError):
    """Raised when a report file can't be parsed into the expected shape."""


@dataclass
class InspectionReport:
    site_code: str
    total_products: int
    major_note: str
    minor_note: str
    path: Path


def discover_report_paths(data_dir: Path | str) -> list[Path]:
    """All ``*.json`` reports in ``data_dir``, sorted for deterministic order."""
    data_dir = Path(data_dir)
    if not data_dir.is_dir():
        raise FileNotFoundError(f"data directory not found: {data_dir}")
    return sorted(data_dir.glob("*.json"))


def _require(d: dict, *keys: str, path: Path):
    """Walk a nested dict, raising a clear ReportParseError on any missing key."""
    cur = d
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            raise ReportParseError(f"{path.name}: missing field {'.'.join(keys)!r}")
        cur = cur[key]
    return cur


def load_report(path: Path | str) -> InspectionReport:
    """Parse a single report file into an ``InspectionReport``."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReportParseError(f"{path.name}: invalid JSON ({exc})") from exc

    facility = _require(data, "header", "facility_data", path=path)
    if not isinstance(facility, dict):
        raise ReportParseError(f"{path.name}: header.facility_data must be an object")
    site_code = facility.get("site_code") or path.stem

    total = _require(data, "production_run", "batch_statistics", "total_products", path=path)
    # Reject bool explicitly: isinstance(True, int) is True in Python.
    if isinstance(total, bool) or not isinstance(total, int) or total <= 0:
        raise ReportParseError(
            f"{path.name}: total_products must be a positive integer, got {total!r}"
        )

    notes = _require(data, "quality_assurance", "human_audit_layer", "audit_notes", path=path)
    if not isinstance(notes, dict):
        raise ReportParseError(f"{path.name}: audit_notes must be an object")
    # Free-text fields: tolerate absence (treat as empty string — extractor reads 0).
    major_note = str(notes.get("major_defects_comments", "") or "")
    minor_note = str(notes.get("minor_defects_comments", "") or "")

    return InspectionReport(
        site_code=str(site_code),
        total_products=total,
        major_note=major_note,
        minor_note=minor_note,
        path=path,
    )


def load_reports(data_dir: Path | str) -> tuple[list[InspectionReport], list[tuple[Path, str]]]:
    """Load every report, returning (reports, errors).

    ``errors`` is a list of ``(path, message)`` for files that failed to parse,
    so the metrics layer can report extraction coverage honestly.
    """
    reports: list[InspectionReport] = []
    errors: list[tuple[Path, str]] = []
    for path in discover_report_paths(data_dir):
        try:
            reports.append(load_report(path))
        except ReportParseError as exc:
            errors.append((path, str(exc)))
    return reports, errors


def iter_reports(data_dir: Path | str) -> Iterator[InspectionReport]:
    reports, _ = load_reports(data_dir)
    yield from reports
