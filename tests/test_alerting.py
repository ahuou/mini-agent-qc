"""Alerting stub: recipient handling and a readable, faithful alert body."""

from qc_pipeline.alerting import build_alert_email, send_email
from qc_pipeline.rules import evaluate_thresholds


def test_single_string_recipient_is_not_exploded_into_chars():
    msg = send_email("qc@x.com", "ops@x.com", "subj", "body")
    assert msg.recipients == ("ops@x.com",)


def test_tuple_recipients_preserved():
    msg = send_email("qc@x.com", ("ops@x.com", "qa@x.com"), "s", "b")
    assert msg.recipients == ("ops@x.com", "qa@x.com")


def test_odd_content_does_not_break_the_stub():
    # %-signs, braces, unicode, quotes must not trigger interpolation errors.
    msg = send_email("a@x.com", ("b@x.com",), "100% {done}", 'body "q...quote" café %s {x}')
    assert "100%" in msg.subject


def test_alert_body_is_faithful_and_readable():
    d = evaluate_thresholds("NA-CHI-021", 6100, 0, 1300,
                            major_threshold=0.01, minor_threshold=0.03, overall_threshold=0.035)
    subject, body = build_alert_email(d, major_evidence="No critical failures",
                                      minor_evidence="13 hundred", flagged_for_review=True)
    assert "NA-CHI-021" in subject
    assert "minor" in body and "21.31%" in body       # the actual breach figure
    assert "13 hundred" in body                        # evidence is shown
    assert "confirm" in body.lower()                   # review note present
