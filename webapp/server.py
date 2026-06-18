"""Thin FastAPI layer over the QC pipeline — serves the dashboard and two JSON APIs.

Nothing here re-implements logic: ``/api/run`` calls ``run_pipeline`` and returns the
same metrics the CLI produces; ``/api/extract`` runs one note through the real
extractor + naive cross-check + threshold rules for the interactive bench test.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

from fastapi import Body, FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from qc_pipeline.cache import CachingExtractor, ExtractionCache
from qc_pipeline.config import DEFAULT_DATA_DIR, Config
from qc_pipeline.extraction.baseline_extractor import NaiveBaselineExtractor
from qc_pipeline.extraction.schema import ExtractedReport
from qc_pipeline.pipeline import _cost_usd, _set_review_flags, make_extractor, run_pipeline
from qc_pipeline.rules import evaluate

HERE = Path(__file__).resolve().parent

# Load the project's .env (live-mode key) by explicit path at import time, so it
# works however the app is launched (python -m webapp OR uvicorn webapp.server:app)
# and regardless of the working directory. Harmless if python-dotenv isn't installed.
try:
    from dotenv import load_dotenv
    load_dotenv(HERE.parent / ".env")
except ImportError:
    pass

DASHBOARD = HERE / "dashboard.html"
# Pipeline runs write results.json somewhere; keep it out of the repo's reports/.
_SCRATCH = Path(tempfile.mkdtemp(prefix="qc_webapp_"))
# The dataset dir of the most recent run, so /api/report can serve the raw files.
_LAST_DATA_DIR = DEFAULT_DATA_DIR
# Persistent extraction cache (survives restarts) so re-running the same notes
# with the same model doesn't burn tokens again. QC_CACHE_DIR overrides the
# location (e.g. /tmp on serverless hosts where only /tmp is writable).
_CACHE = ExtractionCache(os.getenv("QC_CACHE_DIR") or (Path.home() / ".cache" / "qc_pipeline" / "extractions"))

app = FastAPI(title="QC Agent Console", docs_url=None, redoc_url=None)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return DASHBOARD.read_text(encoding="utf-8")


@app.get("/api/status")
def status():
    """Tell the UI whether live mode is reachable (SDK installed, key in env)."""
    return {
        "anthropic_installed": importlib.util.find_spec("anthropic") is not None,
        "env_key": bool(os.getenv("ANTHROPIC_API_KEY")),
    }


def _live_extractor(config: Config, api_key: str | None):
    """Build a cache-wrapped live LLM extractor; api_key (if given) overrides the
    env key. The key is used only to construct the client — never logged or
    persisted. The cache (keyed by model + notes) skips repeat API calls."""
    from qc_pipeline.extraction.llm_extractor import LLMExtractor
    base = LLMExtractor(model=config.model_id, api_key=(api_key or None))
    return CachingExtractor(base, _CACHE, namespace=config.model_id)


@app.get("/api/cache")
def cache_stats():
    return _CACHE.stats()


@app.post("/api/cache/clear")
def cache_clear():
    return {"cleared": _CACHE.clear()}


@app.get("/api/report")
def report(name: str):
    """Return the raw text of one report file from the most recent run's dataset,
    so the UI can show the user exactly what a flagged/failed report contains."""
    safe = os.path.basename(name)  # no path traversal
    path = _LAST_DATA_DIR / safe
    if not path.is_file():
        return JSONResponse(status_code=404, content={"error": f"report '{safe}' not found"})
    raw = path.read_text(encoding="utf-8")
    try:
        json.loads(raw)
        parsed_ok = True
    except Exception:
        parsed_ok = False
    return {"filename": safe, "raw": raw, "parsed_ok": parsed_ok}


def _safe_name(name: str, idx: int) -> str:
    base = re.sub(r"[^A-Za-z0-9_.-]", "_", str(name or f"upload{idx}"))
    if base.endswith(".json"):
        base = base[:-5]
    return f"{idx:03d}_{base}.json"


def _build_dataset(reports: list, include_sample: bool) -> Path:
    """Materialise the chosen reports into a temp dir the pipeline can glob."""
    ddir = Path(tempfile.mkdtemp(prefix="qc_data_", dir=_SCRATCH))
    if include_sample:
        for f in DEFAULT_DATA_DIR.glob("*.json"):
            shutil.copy(f, ddir / f.name)
    idx = 0
    for item in reports or []:
        content = item.get("content") if isinstance(item, dict) else item
        objs = content if isinstance(content, list) else [content]
        name = item.get("name") if isinstance(item, dict) else None
        for obj in objs:
            idx += 1
            # Whatever the upload is, write it out; malformed files are handled by
            # the loader as graceful coverage gaps (no crash) — which the UI shows.
            (ddir / _safe_name(name, idx)).write_text(json.dumps(obj), encoding="utf-8")
    return ddir


@app.post("/api/run")
def api_run(payload: dict | None = Body(default=None)):
    """Run the pipeline and return metrics.

    Body: {mode, tier, reports?: [{name, content}], include_sample?: bool}
    With no uploaded reports and include_sample, runs the bundled 12-report sample.
    Otherwise runs over (sample? + uploaded), so the numbers reflect real input.
    """
    payload = payload or {}
    mode = payload.get("mode", "mock")
    tier = payload.get("tier", "balanced")
    reports = payload.get("reports") or []
    include_sample = payload.get("include_sample", True)
    global _LAST_DATA_DIR
    try:
        if not reports and include_sample:
            config = Config(mode=mode, model_tier=tier, results_dir=_SCRATCH)
            _LAST_DATA_DIR = DEFAULT_DATA_DIR
        else:
            ddir = _build_dataset(reports, include_sample)
            config = Config(mode=mode, model_tier=tier, data_dir=ddir, results_dir=_SCRATCH)
            _LAST_DATA_DIR = ddir
        extractor = _live_extractor(config, payload.get("api_key")) if config.mode == "live" else None
        # Live mode = one network call per report; run them concurrently so a
        # many-report run returns in seconds rather than blocking long enough for
        # the browser to drop the connection.
        workers = 8 if config.mode == "live" else 1
        return run_pipeline(config, extractor=extractor, max_workers=workers)
    except Exception as exc:  # surface a clean message (e.g. live mode w/o key)
        return JSONResponse(status_code=400, content={"error": f"{type(exc).__name__}: {exc}"})


@app.post("/api/extract")
def api_extract(payload: dict = Body(...)):
    """Read one pair of audit notes and return the full verdict (the bench test)."""
    try:
        config = Config(
            mode=payload.get("mode", "mock"),
            model_tier=payload.get("tier", "balanced"),
            results_dir=_SCRATCH,
        )
        total = int(payload.get("total_products") or 0)
        major_note = str(payload.get("major_note") or "")
        minor_note = str(payload.get("minor_note") or "")

        primary = _live_extractor(config, payload.get("api_key")) if config.mode == "live" else make_extractor(config)
        t0 = time.perf_counter()
        extraction, meta = primary.extract(major_note, minor_note,
                                           context={"total_products": total})
        latency_ms = (time.perf_counter() - t0) * 1000.0
        baseline, _ = NaiveBaselineExtractor().extract(major_note, minor_note)

        rep = ExtractedReport(
            site_code="BENCH", total_products=max(total, 0), extraction=extraction,
            baseline_major=baseline.major_defects, baseline_minor=baseline.minor_defects,
            extractor=primary.name, model=meta.model, latency_ms=latency_ms,
            input_tokens=meta.input_tokens, output_tokens=meta.output_tokens,
            cost_usd=_cost_usd(meta),
        )
        _set_review_flags(rep, config)
        decision = evaluate("BENCH", total, rep.major, rep.minor, config)

        return {
            "major": rep.major, "minor": rep.minor,
            "major_confidence": extraction.major_confidence,
            "minor_confidence": extraction.minor_confidence,
            "major_evidence": extraction.major_evidence,
            "minor_evidence": extraction.minor_evidence,
            "baseline_major": rep.baseline_major, "baseline_minor": rep.baseline_minor,
            "baseline_agrees": rep.baseline_agrees,
            "needs_review": rep.needs_review, "review_reasons": rep.review_reasons,
            "alert": decision.alert, "reasons": decision.reasons,
            "major_pct": decision.major_pct, "minor_pct": decision.minor_pct,
            "overall_pct": decision.overall_pct,
            "model": rep.model, "latency_ms": rep.latency_ms, "cost_usd": rep.cost_usd,
        }
    except Exception as exc:
        return JSONResponse(status_code=400, content={"error": f"{type(exc).__name__}: {exc}"})
