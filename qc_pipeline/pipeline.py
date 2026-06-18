"""End-to-end orchestration: load -> extract -> cross-check -> rules -> alert -> measure.

This is the single function the CLI and tests call. It is deliberately linear
and side-effect-light: it returns the metrics dict and writes ``results.json``;
the only outward action is the (stubbed) alert e-mail.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from .alerting import dispatch_alert
from .config import MODEL_PRICING_PER_MTOK, Config
from .extraction.base import CallMeta, Extractor
from .extraction.baseline_extractor import NaiveBaselineExtractor
from .extraction.mock_extractor import MockExtractor
from .extraction.schema import DefectExtraction, ExtractedReport
from .loader import load_reports
from .metrics.evaluation import compute_metrics, write_results
from .rules import evaluate


def make_extractor(config: Config) -> Extractor:
    """Pick the primary extractor for the run mode."""
    if config.mode == "live":
        from .extraction.llm_extractor import LLMExtractor  # lazy: needs anthropic
        return LLMExtractor.from_config(config)
    return MockExtractor()


def _price_for(model: str | None):
    """Look up (input, output) $/MTok, tolerating dated ids the API may return
    (e.g. 'claude-haiku-4-5-20251001' matches the 'claude-haiku-4-5' entry)."""
    if not model:
        return None
    if model in MODEL_PRICING_PER_MTOK:
        return MODEL_PRICING_PER_MTOK[model]
    for key, price in MODEL_PRICING_PER_MTOK.items():
        if model.startswith(key):
            return price
    return None


def _cost_usd(meta: CallMeta) -> float:
    price = _price_for(meta.model)
    if price is None:
        return 0.0
    in_price, out_price = price
    return meta.input_tokens / 1e6 * in_price + meta.output_tokens / 1e6 * out_price


def _estimate_cost(reports, config: Config) -> dict:
    """Projected API cost for this dataset at the selected tier.

    Lets the cost figure stay informative in mock mode (no call is made) and
    change with the chosen model. Tokens are a ~chars/4 estimate, not exact.
    """
    from .extraction.llm_extractor import _SYSTEM_PROMPT  # safe: no SDK import
    in_price, out_price = MODEL_PRICING_PER_MTOK[config.model_id]
    sys_tok = len(_SYSTEM_PROMPT) // 4
    in_tok = sum(sys_tok + (len(r.major_note) + len(r.minor_note) + 60) // 4 for r in reports)
    out_tok = 70 * len(reports)  # a structured extraction is a small JSON object
    est = in_tok / 1e6 * in_price + out_tok / 1e6 * out_price
    return {
        "estimated_usd": round(est, 6),
        "estimated_per_report_usd": round(est / max(len(reports), 1), 6),
        "estimated_input_tokens": in_tok,
        "estimated_output_tokens": out_tok,
        "estimated_model": config.model_id,
    }


def _set_review_flags(rep: ExtractedReport, config: Config) -> None:
    """Decide whether a human should double-check this report, and why.

    Conservative by design for a safety-critical setting: flag on low confidence
    OR any disagreement with the independent rule-based cross-check.
    """
    reasons: list[str] = []
    cutoff = config.review_confidence_cutoff
    if rep.error:
        reasons.append(f"extraction error: {rep.error}")
    if rep.extraction.major_confidence <= cutoff:
        reasons.append(f"low confidence on major reading ({rep.extraction.major_confidence:.2f})")
    if rep.extraction.minor_confidence <= cutoff:
        reasons.append(f"low confidence on minor reading ({rep.extraction.minor_confidence:.2f})")
    if not rep.baseline_agrees:
        reasons.append(
            f"cross-check disagrees: rules-baseline read "
            f"{rep.baseline_major}/{rep.baseline_minor} vs {rep.major}/{rep.minor}"
        )
    rep.needs_review = bool(reasons)
    rep.review_reasons = reasons


def run_pipeline(config: Config, extractor: Extractor | None = None, max_workers: int = 1) -> dict:
    """Run the full pipeline and return the metrics dict.

    ``extractor`` lets a caller inject a pre-built primary extractor (e.g. a live
    LLM client carrying an API key supplied at runtime); otherwise one is built
    from the config. ``max_workers`` > 1 extracts reports concurrently (useful for
    live mode, where each report is a network call); the default of 1 keeps the
    run sequential and deterministic.
    """
    reports, load_errors = load_reports(config.data_dir)
    primary = extractor if extractor is not None else make_extractor(config)
    baseline = NaiveBaselineExtractor()

    extracted: list[ExtractedReport] = []
    decisions = []

    def _extract_one(report):
        """Read one report's notes; never raises — a failure becomes a coverage gap."""
        ctx = {"site_code": report.site_code, "total_products": report.total_products}
        start = time.perf_counter()
        try:
            extraction, meta = primary.extract(report.major_note, report.minor_note, context=ctx)
            error = None
        except Exception as exc:
            extraction = DefectExtraction(
                major_defects=0, minor_defects=0,
                major_confidence=0.0, minor_confidence=0.0,
                major_evidence="", minor_evidence="",
            )
            meta = CallMeta()
            error = f"{type(exc).__name__}: {exc}"
        return report, extraction, meta, (time.perf_counter() - start) * 1000.0, error

    # Extraction is the only slow step (network calls in live mode). Run it
    # concurrently when asked, so a many-report live run finishes in roughly one
    # call's time instead of the sum. ``ThreadPoolExecutor.map`` preserves order,
    # so alerts still dispatch in report order. max_workers=1 (default) keeps the
    # CLI/tests fully sequential and deterministic.
    if max_workers and max_workers > 1 and len(reports) > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(max_workers, len(reports))) as pool:
            results = list(pool.map(_extract_one, reports))
    else:
        results = [_extract_one(r) for r in reports]

    for report, extraction, meta, latency_ms, error in results:
        baseline_extraction, _ = baseline.extract(report.major_note, report.minor_note)

        rep = ExtractedReport(
            site_code=report.site_code,
            total_products=report.total_products,
            extraction=extraction,
            baseline_major=baseline_extraction.major_defects,
            baseline_minor=baseline_extraction.minor_defects,
            extractor=primary.name,
            model=meta.model,
            source=report.path.name,
            latency_ms=latency_ms,
            input_tokens=meta.input_tokens,
            output_tokens=meta.output_tokens,
            cost_usd=_cost_usd(meta),
            cached=meta.cached,
            error=error,
        )
        _set_review_flags(rep, config)
        extracted.append(rep)

        if error is None:
            decision = evaluate(rep.site_code, rep.total_products, rep.major, rep.minor, config)
            decisions.append(decision)
            if decision.alert:
                dispatch_alert(
                    decision,
                    config,
                    major_evidence=rep.extraction.major_evidence,
                    minor_evidence=rep.extraction.minor_evidence,
                    flagged_for_review=rep.needs_review,
                )

    metrics = compute_metrics(extracted, decisions, config=config, load_errors=len(load_errors))
    metrics["run"]["timestamp"] = datetime.now(timezone.utc).isoformat()
    metrics["run"]["load_errors"] = [f"{p.name}: {msg}" for p, msg in load_errors]
    # Structured parse failures (filename + reason) so the UI can list & view them.
    metrics["parse_errors"] = [{"file": p.name, "error": msg} for p, msg in load_errors]
    # Projected cost at the selected tier (informative even in mock mode).
    metrics["cost"].update(_estimate_cost(reports, config))
    write_results(metrics, config.results_dir / "results.json")
    return metrics
