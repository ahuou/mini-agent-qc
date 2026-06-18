"""Measure the *tool's* performance — not the factory's defect rates.

Every metric here answers "how good is the agent at its job?":

  * Reading accuracy   — did it read each defect count correctly? (vs golden)
  * Value of the LLM   — how many counts/alerts does the naive baseline miss?
  * Alert quality      — precision/recall on the firing decision (catch the breach,
                         no false alarms).
  * Confidence & review— how sure was it, and how often does a human need to look?
  * Speed              — latency per report, throughput.
  * Cost               — illustrative $/report from token usage and list prices.
  * Coverage           — fraction of files read without error.

Ground truth (``golden.py``) is used ONLY to score the tool; the extractors never
see it. If a run contains reports with no golden label, accuracy is reported as
unavailable while every other (label-free) metric is still produced — so the tool
works on unseen data, it just can't self-grade it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..config import Config
from ..extraction.schema import ExtractedReport
from ..rules import AlertDecision, evaluate
from .golden import GOLDEN


# --------------------------------------------------------------------------- #
# small dependency-free stats helpers
# --------------------------------------------------------------------------- #
def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = int(pos)
    frac = pos - lo
    if lo + 1 < len(s):
        return s[lo] + frac * (s[lo + 1] - s[lo])
    return s[lo]


def _safe_div(num: float, den: float, default: float = 0.0) -> float:
    return num / den if den else default


def _accuracy_block(reports: list[ExtractedReport], use_baseline: bool) -> Optional[dict]:
    """Accuracy of the primary (or baseline) reading vs golden, over labelled reports."""
    labelled = [r for r in reports if r.site_code in GOLDEN and r.error is None]
    if not labelled:
        return None
    fields_total = 2 * len(labelled)
    fields_correct = 0
    reports_correct = 0
    abs_err_sum = 0
    major_correct = minor_correct = 0
    for r in labelled:
        g = GOLDEN[r.site_code]
        maj = r.baseline_major if use_baseline else r.major
        minr = r.baseline_minor if use_baseline else r.minor
        mc = maj == g.major
        nc = minr == g.minor
        fields_correct += int(mc) + int(nc)
        major_correct += int(mc)
        minor_correct += int(nc)
        reports_correct += int(mc and nc)
        abs_err_sum += abs(maj - g.major) + abs(minr - g.minor)
    return {
        "field_accuracy": round(_safe_div(fields_correct, fields_total), 4),
        "fields_correct": fields_correct,
        "fields_total": fields_total,
        "report_accuracy": round(_safe_div(reports_correct, len(labelled)), 4),
        "reports_correct": reports_correct,
        "reports_total": len(labelled),
        "major_accuracy": round(_safe_div(major_correct, len(labelled)), 4),
        "minor_accuracy": round(_safe_div(minor_correct, len(labelled)), 4),
        "mean_absolute_error": round(_safe_div(abs_err_sum, fields_total), 4),
    }


def _confusion(predicted: dict[str, bool], expected: dict[str, bool]) -> dict:
    tp = fp = fn = tn = 0
    for site, exp in expected.items():
        pred = predicted.get(site, False)
        if pred and exp:
            tp += 1
        elif pred and not exp:
            fp += 1
        elif not pred and exp:
            fn += 1
        else:
            tn += 1
    precision = _safe_div(tp, tp + fp, default=1.0)
    recall = _safe_div(tp, tp + fn, default=1.0)
    f1 = _safe_div(2 * precision * recall, precision + recall, default=0.0)
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round(_safe_div(tp + tn, tp + fp + fn + tn), 4),
    }


def compute_metrics(
    extracted: list[ExtractedReport],
    decisions: list[AlertDecision],
    *,
    config: Config,
    load_errors: int = 0,
) -> dict:
    """Build the full results dict from the per-report records."""
    by_site_decision = {d.site_code: d for d in decisions}
    ok = [r for r in extracted if r.error is None]
    n_ok = len(ok)
    files_seen = len(extracted) + load_errors
    seen_sites = {r.site_code for r in extracted}  # includes reports that errored

    # --- extraction quality (primary vs baseline) --------------------------- #
    primary_acc = _accuracy_block(ok, use_baseline=False)
    baseline_acc = _accuracy_block(ok, use_baseline=True)

    # --- alert quality ------------------------------------------------------ #
    # Ground-truth expectation covers every report we SAW that has a golden
    # label — including ones whose extraction errored. A report we failed to read
    # has no alert decision, so a breach we couldn't read counts as a MISS (false
    # negative), never silently as a correct no-alert. This is the safety-critical
    # invariant: an unread breach must not be reported as a perfect run.
    expected = {code: g.expected_alert for code, g in GOLDEN.items() if code in seen_sites}
    predicted_primary = {r.site_code: by_site_decision[r.site_code].alert
                         for r in ok if r.site_code in by_site_decision}
    # What would the naive baseline have decided? (baseline counts exist even when
    # the primary extraction errored, so compute over all seen reports.)
    predicted_baseline = {
        r.site_code: evaluate(r.site_code, r.total_products, r.baseline_major,
                              r.baseline_minor, config).alert
        for r in extracted
    }
    alert_primary = _confusion(predicted_primary, expected) if expected else None
    alert_baseline = _confusion(predicted_baseline, expected) if expected else None

    # alerts/counts the baseline got wrong but the tool got right
    baseline_missed_alerts = sorted(
        site for site, exp in expected.items()
        if exp and not predicted_baseline.get(site, False)
        and predicted_primary.get(site, False)
    )

    # --- confidence, agreement, human-in-the-loop --------------------------- #
    confidences: list[float] = []
    for r in ok:
        confidences.extend([r.extraction.major_confidence, r.extraction.minor_confidence])
    agreeing_fields = sum(
        int(r.baseline_major == r.major) + int(r.baseline_minor == r.minor) for r in ok
    )
    total_fields = 2 * n_ok
    flagged = [r for r in extracted if r.needs_review]  # errored reports flag too
    cutoff = config.review_confidence_cutoff

    # --- performance -------------------------------------------------------- #
    latencies = [r.latency_ms for r in ok]
    total_latency = sum(latencies)

    # --- cost --------------------------------------------------------------- #
    total_cost = sum(r.cost_usd for r in ok)
    total_in = sum(r.input_tokens for r in ok)
    total_out = sum(r.output_tokens for r in ok)
    cache_hits = sum(1 for r in ok if r.cached)

    # --- per-report detail -------------------------------------------------- #
    per_report = []
    for r in extracted:
        d = by_site_decision.get(r.site_code)
        g = GOLDEN.get(r.site_code)
        row = {
            "site_code": r.site_code,
            "source": r.source,
            "total_products": r.total_products,
            "major": r.major,
            "minor": r.minor,
            "major_confidence": round(r.extraction.major_confidence, 3),
            "minor_confidence": round(r.extraction.minor_confidence, 3),
            "baseline_major": r.baseline_major,
            "baseline_minor": r.baseline_minor,
            "baseline_agrees": r.baseline_agrees,
            "needs_review": r.needs_review,
            "review_reasons": r.review_reasons,
            "cached": r.cached,
            "error": r.error,
            "alert": d.alert if d else None,
            "alert_reasons": d.reasons if d else [],
            "latency_ms": round(r.latency_ms, 3),
            "cost_usd": round(r.cost_usd, 6),
            "major_evidence": r.extraction.major_evidence,
            "minor_evidence": r.extraction.minor_evidence,
        }
        if g is not None:
            row.update({
                "golden_major": g.major,
                "golden_minor": g.minor,
                "golden_alert": g.expected_alert,
                "major_correct": r.major == g.major,
                "minor_correct": r.minor == g.minor,
            })
        per_report.append(row)

    metrics = {
        "run": {
            "mode": config.mode,
            "model_tier": config.model_tier,
            "model": config.model_id if config.mode == "live" else "mock (offline)",
            "n_reports": n_ok,
            "n_files": files_seen,
        },
        "extraction_quality": {
            "ground_truth_available": primary_acc is not None,
            "primary": primary_acc,
            "baseline": baseline_acc,
            "llm_value": (
                {
                    "field_accuracy_gain": round(
                        primary_acc["field_accuracy"] - baseline_acc["field_accuracy"], 4
                    ),
                    "baseline_missed_alert_sites": baseline_missed_alerts,
                }
                if primary_acc and baseline_acc else None
            ),
        },
        "alert_quality": {
            "primary": alert_primary,
            "baseline": alert_baseline,
            "expected_alert_sites": sorted(s for s, e in expected.items() if e),
            "predicted_alert_sites": sorted(s for s, p in predicted_primary.items() if p),
        },
        "confidence_and_review": {
            "review_confidence_cutoff": cutoff,
            "mean_confidence": round(_safe_div(sum(confidences), len(confidences)), 4),
            "min_confidence": round(min(confidences), 4) if confidences else None,
            "fields_below_cutoff": sum(1 for c in confidences if c <= cutoff),
            "baseline_agreement_rate": round(_safe_div(agreeing_fields, total_fields), 4),
            "n_field_disagreements": total_fields - agreeing_fields,
            "reports_flagged_for_review": len(flagged),
            "review_rate": round(_safe_div(len(flagged), n_ok), 4),
            "flagged_sites": sorted(r.site_code for r in flagged),
        },
        "performance": {
            "total_latency_ms": round(total_latency, 3),
            "mean_latency_ms": round(_safe_div(total_latency, n_ok), 3),
            "p50_latency_ms": round(_percentile(latencies, 0.50), 3),
            "p95_latency_ms": round(_percentile(latencies, 0.95), 3),
            "throughput_reports_per_s": round(_safe_div(n_ok, total_latency / 1000.0), 2)
            if total_latency > 0 else None,
        },
        "cost": {
            "model": config.model_id if config.mode == "live" else None,
            "total_usd": round(total_cost, 6),
            "per_report_usd": round(_safe_div(total_cost, n_ok), 6),
            "total_input_tokens": total_in,
            "total_output_tokens": total_out,
            "cache_hits": cache_hits,
            "api_calls": (n_ok - cache_hits) if config.mode == "live" else 0,
            "note": "offline mock — no API calls, $0"
            if config.mode == "mock" else "live API list-price estimate",
        },
        "coverage": {
            "files_seen": files_seen,
            "reports_extracted": n_ok,
            "load_errors": load_errors,
            "extraction_errors": len(extracted) - n_ok,
            "coverage_rate": round(_safe_div(n_ok, files_seen), 4),
        },
        "per_report": per_report,
    }
    metrics["stakeholder_summary"] = _stakeholder_summary(metrics)
    return metrics


def _stakeholder_summary(m: dict) -> dict:
    """Plain-language sentences a non-technical reader can act on."""
    eq = m["extraction_quality"]
    aq = m["alert_quality"]
    cr = m["confidence_and_review"]
    perf = m["performance"]
    cost = m["cost"]
    cov = m["coverage"]
    out: dict[str, str] = {}

    if eq["ground_truth_available"]:
        p = eq["primary"]
        out["reading_accuracy"] = (
            f"The tool read {p['fields_correct']} of {p['fields_total']} defect counts "
            f"correctly ({p['field_accuracy']:.0%})."
        )
        if eq["llm_value"] and eq["llm_value"]["baseline_missed_alert_sites"]:
            missed = ", ".join(eq["llm_value"]["baseline_missed_alert_sites"])
            out["value_of_ai"] = (
                f"A rules-only reader (no LLM) reads only {eq['baseline']['field_accuracy']:.0%} "
                f"of counts correctly and would have MISSED the breach at {missed} "
                f"(it misreads phrasing like '13 hundred' as 13)."
            )
    else:
        out["reading_accuracy"] = (
            "No ground-truth labels for this dataset, so reading accuracy is not scored; "
            "confidence, speed and coverage below are still measured, and alerts are still "
            "decided (their accuracy can't be scored without labels)."
        )

    if aq["primary"]:
        ap = aq["primary"]
        out["alerts"] = (
            f"It correctly flagged {ap['tp']} of {ap['tp'] + ap['fn']} facilities that "
            f"breached limits, with {ap['fp']} false alarm(s) "
            f"(precision {ap['precision']:.0%}, recall {ap['recall']:.0%})."
        )

    out["human_in_the_loop"] = (
        f"{cr['reports_flagged_for_review']} of {m['run']['n_reports']} reports were flagged "
        f"for a human to double-check ({cr['review_rate']:.0%}), based on low confidence or "
        f"disagreement with the cross-check."
    )
    out["speed"] = (
        f"Average {perf['mean_latency_ms']:.2f} ms per report"
        + (f" (~{perf['throughput_reports_per_s']:.0f} reports/sec)."
           if perf["throughput_reports_per_s"] else ".")
    )
    if cost["total_usd"] > 0:
        out["cost"] = (
            f"About ${cost['per_report_usd']:.4f} per report "
            f"(~${cost['per_report_usd'] * 10000:,.0f} to process 10,000 reports)."
        )
    else:
        out["cost"] = "Ran fully offline at $0 (deterministic mock extractor)."
    out["coverage"] = (
        f"Read {cov['reports_extracted']} of {cov['files_seen']} report files without error "
        f"({cov['coverage_rate']:.0%})."
    )
    unread = cov["extraction_errors"] + cov["load_errors"]
    if unread:
        out["unread"] = (
            f"WARNING: {unread} report(s) could NOT be read and were NOT evaluated against "
            f"limits — treat these as needing manual review (a breach we cannot read is "
            f"counted as a missed alert, not a pass)."
        )
    return out


def write_results(metrics: dict, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return path


def render_console_summary(metrics: dict) -> str:
    """A compact, human-readable digest for the end of a CLI run."""
    s = metrics["stakeholder_summary"]
    order = ["reading_accuracy", "value_of_ai", "alerts", "human_in_the_loop",
             "speed", "cost", "coverage", "unread"]
    lines = ["", "Tool-quality summary (how well the agent did its job):", "-" * 60]
    lines += [f"  • {s[k]}" for k in order if k in s]
    return "\n".join(lines)
