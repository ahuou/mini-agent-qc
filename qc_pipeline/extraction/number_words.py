"""Robust natural-language quantity parser.

This is the heart of why the task needs more than a naive regex. Audit notes
phrase counts every which way:

    "31 units"             -> 31      "13 hundred units"     -> 1300  (the trap)
    "a hundred units"      -> 100     "two hundred and fifty"-> 250
    "fourteen hundred"     -> 1400    "twenty-five hundred"  -> 2500
    "sixty five units"     -> 65      "one thousand two hundred" -> 1200
    "a dozen"              -> 12      "half a dozen"         -> 6
    "a single unit"        -> 1       "1.5k units"           -> 1500
    "a couple dozen"       -> 24 (low confidence)
    "No critical failures" -> 0       "did not find any"     -> 0

``parse_count`` returns the value, a confidence in [0, 1] reflecting how
unambiguous the phrasing was (fuzzy quantifiers stay low so they route to human
review), the matched evidence, and the method used.

The composer walks the note left-to-right and accumulates spelled-out numerals
with the standard ones/tens + hundred/thousand algorithm, so compound numbers
("sixty five", "two hundred and fifty") and multipliers ("13 hundred") are read
correctly rather than collapsing to a single token. This robust parser backs the
offline mock extractor (a deterministic stand-in for the LLM); a deliberately
naive baseline lives separately in ``baseline_extractor.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class NumberParse:
    value: int
    confidence: float
    evidence: str
    method: str


_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fourty": 40,  # 'fourty' = common misspelling
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_MUL_SMALL = {"hundred": 100, "dozen": 12}                 # multiply the running group
_MUL_BIG = {"thousand": 1000, "million": 1_000_000, "billion": 1_000_000_000}
# Words that connect/qualify a numeral without contributing a value of their own.
_FILLER = {"a", "an", "and", "of", "the", "single", "sole", "lone"}

_FUZZY_BASE = {"couple": 2, "few": 3, "several": 4, "handful": 5, "bunch": 5, "numerous": 6}

_K_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*k\b")
_HALF_DOZEN_RE = re.compile(r"\bhalf\s+(?:a\s+)?dozen\b")
_SINGLE_RE = re.compile(r"\b(?:a|one)\s+(?:single|sole|lone)\b")
_FUZZY_RE = re.compile(
    r"\b(?:a\s+)?(couple|few|several|handful|bunch|numerous)(?:\s+of)?"
    r"(?:\s+(dozen|hundred|thousand|million))?\b"
)
_ABSENCE_RE = re.compile(r"\b(no|none|not|without|nil|never|zero)\b")
_TOKEN_RE = re.compile(r"[a-z]+|\d[\d,]*")


def _compose(text: str):
    """Accumulate the first spelled/numeric quantity in ``text``.

    Returns (value, used_scale, used_digit, evidence) or None if no numeral
    starts. Hyphens are normalised to spaces so "twenty-five" reads as 25.
    """
    tokens = _TOKEN_RE.findall(text.replace("-", " "))
    result = 0          # accumulated thousands+ groups
    current = 0         # the group currently being built
    used = used_scale = used_digit = False
    consumed: list[str] = []

    for tok in tokens:
        if tok[0].isdigit():
            current += int(tok.replace(",", ""))
            used = used_digit = True
            consumed.append(tok)
        elif tok in _ONES:
            current += _ONES[tok]; used = True; consumed.append(tok)
        elif tok in _TENS:
            current += _TENS[tok]; used = True; consumed.append(tok)
        elif tok in _MUL_SMALL:
            current = (current or 1) * _MUL_SMALL[tok]
            used = used_scale = True; consumed.append(tok)
        elif tok in _MUL_BIG:
            result += (current or 1) * _MUL_BIG[tok]
            current = 0; used = used_scale = True; consumed.append(tok)
        elif tok in _FILLER:
            continue            # connective/qualifier: neither counts nor stops
        else:
            if used:
                break           # a real word after the numeral ends it
            continue            # leading prose before the numeral — skip
    if not used:
        return None
    return result + current, used_scale, used_digit, " ".join(consumed)


def parse_count(text: str) -> NumberParse:
    """Extract a single defect count from a free-text audit note."""
    if not text or not text.strip():
        return NumberParse(0, 0.20, "", "empty")
    t = text.lower()

    # 1. "1.5k" / "2k".
    if (m := _K_RE.search(t)):
        return NumberParse(int(round(float(m.group(1)) * 1000)), 0.90, m.group(0), "k_suffix")

    # 2. "half a dozen" idiom.
    if (m := _HALF_DOZEN_RE.search(t)):
        return NumberParse(6, 0.90, m.group(0), "dozen")

    # 3. Fuzzy quantifiers (only when no explicit digit is present, so an exact
    #    number always wins). Imprecise -> low confidence -> routed to review.
    if not any(c.isdigit() for c in t) and (m := _FUZZY_RE.search(t)):
        base = _FUZZY_BASE[m.group(1)]
        scale_word = m.group(2)
        scale = _MUL_SMALL.get(scale_word) or _MUL_BIG.get(scale_word) or 1
        return NumberParse(base * scale, 0.50, m.group(0), "fuzzy")

    # 4. Exact composition: digits, spelled numerals, multipliers, additive tails.
    composed = _compose(t)
    if composed is not None:
        value, used_scale, used_digit, evidence = composed
        if used_digit and not used_scale and len(evidence.split()) == 1:
            conf, method = 0.99, "digit"        # a bare integer like "31"
        elif used_scale:
            conf, method = 0.92, "scale"        # "13 hundred", "a hundred", "two thousand"
        else:
            conf, method = 0.90, "word"         # "sixty five", "nineteen"
        return NumberParse(value, conf, evidence, method)

    # 5. "a single / a sole / a lone" -> 1 (idiom with no numeric token).
    if (m := _SINGLE_RE.search(t)):
        return NumberParse(1, 0.90, m.group(0), "word")

    # 6. Explicit absence / negation -> 0.
    if (m := _ABSENCE_RE.search(t)):
        return NumberParse(0, 0.96, m.group(0), "absence")

    # 7. Nothing parseable — default to 0 but flag low confidence for review.
    return NumberParse(0, 0.25, "", "none_found")
