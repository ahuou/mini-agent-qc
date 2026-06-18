"""Central configuration for the QC pipeline.

Everything tunable lives here so the rest of the package has no magic numbers.
Values can be overridden from the environment (see ``Config.from_env``) or by
constructing a ``Config`` directly in tests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------- #
# Defect-threshold rules (from the task brief).
#
# An alert is raised if ANY of these fractions of total production is exceeded.
# These are STRICT ">" comparisons: a value sitting exactly on the threshold
# does NOT alert (see qc_pipeline/rules.py).
# --------------------------------------------------------------------------- #
MAJOR_DEFECT_THRESHOLD = 0.01    # major defects   > 1%   of total production
MINOR_DEFECT_THRESHOLD = 0.03    # minor defects   > 3%   of total production
OVERALL_DEFECT_THRESHOLD = 0.035  # (major + minor) > 3.5% of total production

# --------------------------------------------------------------------------- #
# Claude model IDs (canonical, no date suffix). See the claude-api reference.
# The runtime extraction model is configurable; we default to Sonnet 4.6 for a
# strong robustness / cost balance, and expose cheap (Haiku) and max (Opus) tiers.
# --------------------------------------------------------------------------- #
MODEL_TIERS = {
    "cheap": "claude-haiku-4-5",   # fastest / lowest cost
    "balanced": "claude-sonnet-4-6",  # default — robust on the word-number traps
    "max": "claude-opus-4-8",      # highest capability
}
DEFAULT_MODEL_TIER = "balanced"

# Published list prices, USD per 1,000,000 tokens (input, output).
# Source: claude-api reference, cached 2026-06-04. Used only to surface an
# illustrative "cost per report" metric; never affects extraction behaviour.
MODEL_PRICING_PER_MTOK = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-8": (5.00, 25.00),
}

# Confidence at or below which an extracted field is flagged for human review.
REVIEW_CONFIDENCE_CUTOFF = 0.75

# Repo-root-relative default location of the inspection reports.
_PACKAGE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PACKAGE_DIR.parent
DEFAULT_DATA_DIR = _REPO_ROOT / "data" / "inspection_reports"
DEFAULT_RESULTS_DIR = _REPO_ROOT / "reports"


@dataclass
class Config:
    """Runtime configuration for a single pipeline run."""

    # "mock" runs fully offline with a deterministic stand-in for the LLM.
    # "live" calls the Anthropic API (requires ANTHROPIC_API_KEY).
    mode: str = "mock"

    data_dir: Path = field(default_factory=lambda: DEFAULT_DATA_DIR)
    results_dir: Path = field(default_factory=lambda: DEFAULT_RESULTS_DIR)

    model_tier: str = DEFAULT_MODEL_TIER

    major_threshold: float = MAJOR_DEFECT_THRESHOLD
    minor_threshold: float = MINOR_DEFECT_THRESHOLD
    overall_threshold: float = OVERALL_DEFECT_THRESHOLD

    review_confidence_cutoff: float = REVIEW_CONFIDENCE_CUTOFF

    # Stakeholder distribution list for the (stubbed) alert e-mail.
    alert_recipients: tuple[str, ...] = ("quality-ops@example.com",)
    alert_sender: str = "qc-pipeline@example.com"

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        self.results_dir = Path(self.results_dir)
        if self.mode not in ("mock", "live"):
            raise ValueError(f"mode must be 'mock' or 'live', got {self.mode!r}")
        if self.model_tier not in MODEL_TIERS:
            raise ValueError(
                f"model_tier must be one of {sorted(MODEL_TIERS)}, got {self.model_tier!r}"
            )

    @property
    def model_id(self) -> str:
        """Resolve the configured tier to a concrete Claude model ID."""
        return MODEL_TIERS[self.model_tier]

    @classmethod
    def from_env(cls, **overrides) -> "Config":
        """Build a Config from environment variables, with explicit overrides."""
        env_kwargs: dict = {}
        if (mode := os.getenv("QC_MODE")):
            env_kwargs["mode"] = mode
        if (tier := os.getenv("QC_MODEL_TIER")):
            env_kwargs["model_tier"] = tier
        if (data_dir := os.getenv("QC_DATA_DIR")):
            env_kwargs["data_dir"] = Path(data_dir)
        env_kwargs.update(overrides)
        return cls(**env_kwargs)
