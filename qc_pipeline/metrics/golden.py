"""Hand-verified ground truth for the 12 sample inspection reports.

This is the *correctness contract*. Each label was derived by reading the raw
audit notes and resolving the natural-language counts by hand:

    "13 hundred units"  -> 1300   "a hundred units" -> 100   "a dozen" -> 12
    "half a dozen"      -> 6      "a single unit"   -> 1     "None"/"did not find" -> 0

``expected_alert`` is likewise hand-derived against the threshold rules
(major>1%, minor>3%, overall>3.5%) and is cross-checked against the rules
engine in the test-suite — if the engine and this table ever disagree, one of
them is wrong. Exactly one report (NA-CHI-021) should alert.

This golden set lets the metrics layer measure how well the *tool* reads the
notes; it is not used by the extractors themselves (that would be overfitting).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GoldenLabel:
    site_code: str
    total_products: int
    major: int
    minor: int
    expected_alert: bool
    note: str = ""  # what made this case interesting


GOLDEN: dict[str, GoldenLabel] = {
    g.site_code: g
    for g in [
        GoldenLabel("APAC-PN-021", 12000, 11, 0, False, "plain digits; 'None' minor"),
        GoldenLabel("APAC-SGP-003", 9000, 0, 45, False, "negated major; digit minor"),
        GoldenLabel("APAC-TYO-011", 6500, 0, 18, False, "'0 critical' major"),
        GoldenLabel("EU-AMS-019", 7200, 1, 12, False, "'a single'->1; 'a dozen'->12"),
        GoldenLabel("EU-BER-002", 7800, 0, 31, False, "negated major"),
        GoldenLabel("EU-MAD-013", 5000, 0, 23, False, "'did not find any'->0"),
        GoldenLabel("EU-PL-005", 10000, 3, 100, False, "'a hundred'->100 (word-multiplier); minor 1.0% well under 3%"),
        GoldenLabel("NA-ATL-017", 5400, 2, 0, False, "'No cosmetic issues'->0 minor"),
        GoldenLabel("NA-AUS-009", 4200, 5, 6, False, "'half a dozen'->6"),
        GoldenLabel("NA-CHI-021", 6100, 0, 1300, True, "'13 hundred'->1300 — THE alert"),
        GoldenLabel("NA-DEN-006", 3600, 7, 9, False, "plain digits both fields"),
        GoldenLabel("NA-SEA-014", 4800, 0, 12, False, "'did did not find any'->0 (typo-robust)"),
    ]
}

# Convenience views used by tests and the metrics layer.
EXPECTED_ALERT_SITES = {code for code, g in GOLDEN.items() if g.expected_alert}
