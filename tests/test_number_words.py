"""The crux: natural-language quantity parsing, including the traps."""

import pytest

from qc_pipeline.extraction.number_words import parse_count


@pytest.mark.parametrize(
    "text, expected",
    [
        ("31 units had minor discoloration of straps.", 31),
        ("45 units had minor dust inside lenses requiring re-cleaning.", 45),
        ("18 units showed cosmetic scratches on casings.", 18),
        ("11 units failed high-voltage isolation tests due to contamination.", 11),
        ("2 boards exhibited lifted pads leading to intermittent connections.", 2),
        # --- the headline trap: multipliers ---
        ("13 hundred units exhibited slight connector misalignment; corrected on line.", 1300),
        ("A hundred units had minor cosmetic blemishes.", 100),
        ("fourteen hundred units were scrapped", 1400),
        ("two thousand units flagged", 2000),
        ("1.5k units showed wear", 1500),
        # --- dozens ---
        ("A dozen units had minor cosmetic blemishes.", 12),
        ("Half a dozen units had loose labels (non-functional).", 6),
        ("two dozen units", 24),
        # --- spelled-out small / single ---
        ("A single unit failed due to sensor calibration drift beyond tolerance.", 1),
        ("nine units showed bent mounting tabs", 9),
        # --- negation / absence -> 0 ---
        ("No critical failures recorded.", 0),
        ("No critical functional defects verified.", 0),
        ("We did not find any critical defects.", 0),
        ("The observation that we did did not find any critical failures observed during teardown.", 0),
        ("None", 0),
        ("No cosmetic issues reported.", 0),
        ("0 critical defects found.", 0),
    ],
)
def test_parse_count_values(text, expected):
    assert parse_count(text).value == expected


def test_thirteen_hundred_is_not_thirteen():
    """The single most important case — a naive reader returns 13 here."""
    assert parse_count("13 hundred units exhibited slight connector misalignment").value == 1300


def test_digits_and_negations_are_high_confidence():
    assert parse_count("31 units").confidence >= 0.9
    assert parse_count("No critical failures recorded.").confidence >= 0.9


def test_fuzzy_quantifiers_are_low_confidence():
    p = parse_count("a few units were marginal")
    assert p.value == 3
    assert p.confidence <= 0.75  # should be flagged for human review


def test_empty_note_is_zero_low_confidence():
    p = parse_count("")
    assert p.value == 0 and p.confidence < 0.5


@pytest.mark.parametrize(
    "text, expected",
    [
        ("sixty five units with major structural cracks", 65),
        ("twenty-five units", 25),
        ("twenty three units", 23),
        ("ninety nine units", 99),
        ("two hundred and fifty units", 250),
        ("two hundred fifty units", 250),
        ("one thousand two hundred units", 1200),
        ("twenty-five hundred units", 2500),
        ("a million units", 1_000_000),
        ("thirteen hundred and fifty", 1350),
    ],
)
def test_compound_numbers_compose(text, expected):
    assert parse_count(text).value == expected


def test_compound_tens_are_confident_not_silently_dropped():
    """Regression for the silent false-negative: 'sixty five' must read 65 at high
    confidence, not collapse to 5 and pass below the review radar."""
    p = parse_count("sixty five units")
    assert p.value == 65 and p.confidence > 0.75


@pytest.mark.parametrize(
    "text, expected",
    [
        ("a couple dozen units", 24),
        ("a couple hundred units", 200),
        ("several thousand units", 4000),
    ],
)
def test_fuzzy_times_scale_is_low_confidence(text, expected):
    p = parse_count(text)
    assert p.value == expected
    assert p.confidence <= 0.75  # imprecise -> routed to human review
