"""The defect-threshold engine — pure, deterministic, dependency-free.

An alert fires if ANY of these is exceeded (STRICT greater-than; a value sitting
exactly on the threshold does NOT alert):

    major   / total  >  1.0%
    minor   / total  >  3.0%
    (major+minor)/total  >  3.5%

This module has no knowledge of LLMs, files, or e-mail — it takes three numbers
and the thresholds and returns a decision. That keeps it trivially testable and
lets the boundary behaviour be pinned down exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import Config


@dataclass
class AlertDecision:
    site_code: str
    total_products: int
    major: int
    minor: int
    major_pct: float
    minor_pct: float
    overall_pct: float
    alert: bool
    reasons: list[str] = field(default_factory=list)


def evaluate_thresholds(
    site_code: str,
    total_products: int,
    major: int,
    minor: int,
    *,
    major_threshold: float,
    minor_threshold: float,
    overall_threshold: float,
) -> AlertDecision:
    """Apply the three OR-ed threshold rules and explain which (if any) tripped."""
    # Guard against division by zero; a non-positive batch can't exceed any rate.
    if total_products <= 0:
        return AlertDecision(site_code, total_products, major, minor, 0.0, 0.0, 0.0, False,
                             ["non-positive total_products — no rate computable"])

    major_pct = major / total_products
    minor_pct = minor / total_products
    overall_pct = (major + minor) / total_products

    reasons: list[str] = []
    if major_pct > major_threshold:
        reasons.append(
            f"major defects {major_pct:.2%} exceed {major_threshold:.2%} ({major}/{total_products})"
        )
    if minor_pct > minor_threshold:
        reasons.append(
            f"minor defects {minor_pct:.2%} exceed {minor_threshold:.2%} ({minor}/{total_products})"
        )
    if overall_pct > overall_threshold:
        reasons.append(
            f"overall defects {overall_pct:.2%} exceed {overall_threshold:.2%} "
            f"({major + minor}/{total_products})"
        )

    return AlertDecision(
        site_code=site_code,
        total_products=total_products,
        major=major,
        minor=minor,
        major_pct=major_pct,
        minor_pct=minor_pct,
        overall_pct=overall_pct,
        alert=bool(reasons),
        reasons=reasons,
    )


def evaluate(site_code: str, total_products: int, major: int, minor: int, config: Config) -> AlertDecision:
    """Convenience wrapper that pulls thresholds from a ``Config``."""
    return evaluate_thresholds(
        site_code,
        total_products,
        major,
        minor,
        major_threshold=config.major_threshold,
        minor_threshold=config.minor_threshold,
        overall_threshold=config.overall_threshold,
    )
