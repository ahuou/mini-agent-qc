"""Command-line entry point.

    python -m qc_pipeline                      # offline mock run (default, $0)
    python -m qc_pipeline --mode live --tier balanced
    python -m qc_pipeline --data-dir path/to/reports --results out/
"""

from __future__ import annotations

import argparse
import logging
import sys

from .config import DEFAULT_RESULTS_DIR, MODEL_TIERS, Config
from .metrics.evaluation import render_console_summary
from .pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="qc_pipeline",
        description="Read inspection reports, extract defect counts with an LLM, "
                    "apply thresholds, alert, and measure the tool's own quality.",
    )
    # Defaults are None so we can tell "user passed a flag" from "use env/default".
    p.add_argument("--mode", choices=["mock", "live"], default=None,
                   help="mock = deterministic offline (no API key); live = Anthropic API. "
                        "(default: $QC_MODE or mock)")
    p.add_argument("--tier", choices=sorted(MODEL_TIERS), default=None,
                   help="live model tier: cheap=Haiku, balanced=Sonnet, max=Opus. "
                        "(default: $QC_MODEL_TIER or balanced)")
    p.add_argument("--data-dir", default=None,
                   help="directory of *.json inspection reports. (default: $QC_DATA_DIR or ./data/...)")
    p.add_argument("--results", default=str(DEFAULT_RESULTS_DIR),
                   help="directory to write results.json into.")
    p.add_argument("-v", "--verbose", action="store_true", help="enable INFO logging.")
    return p


def main(argv: list[str] | None = None) -> int:
    # Optionally load a .env file so the documented QC_* / ANTHROPIC_API_KEY skeleton
    # works out of the box; harmless if python-dotenv isn't installed.
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    # Explicit CLI flags win over env vars (QC_MODE/QC_MODEL_TIER/QC_DATA_DIR) win over defaults.
    overrides: dict = {"results_dir": args.results}
    if args.mode:
        overrides["mode"] = args.mode
    if args.tier:
        overrides["model_tier"] = args.tier
    if args.data_dir:
        overrides["data_dir"] = args.data_dir

    try:
        config = Config.from_env(**overrides)
        print(f"Running QC pipeline ({config.mode} mode, model={config.model_id}) "
              f"on {config.data_dir} ...")
        metrics = run_pipeline(config)
    except (FileNotFoundError, ModuleNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    alerts = metrics["alert_quality"]["predicted_alert_sites"]
    print(f"\nProcessed {metrics['run']['n_reports']} reports. "
          f"Alerts raised: {len(alerts)}" + (f" -> {', '.join(alerts)}" if alerts else "."))
    print(render_console_summary(metrics))
    print(f"\nFull machine-readable metrics: {config.results_dir / 'results.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
