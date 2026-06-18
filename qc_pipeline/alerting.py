"""Stakeholder alerting.

``send_email`` is a stub: it logs and prints the message instead of talking to a
real mail server, but it returns the structured ``EmailMessage`` so the rest of
the system (and the tests) can treat it like a real dispatch. Swapping in SMTP /
SES later means replacing one function body.

The alert body is written for a non-technical operations reader: which facility,
which rule tripped, the actual numbers, and the audit-note snippet behind them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .config import Config
from .rules import AlertDecision

logger = logging.getLogger("qc_pipeline.alerting")


@dataclass
class EmailMessage:
    sender: str
    recipients: tuple[str, ...]
    subject: str
    body: str


def send_email(sender: str, recipients: tuple[str, ...], subject: str, body: str) -> EmailMessage:
    """STUB mail sender — logs/prints the message and returns it.

    Replace the body of this function with a real transport (SMTP, SES, …) to go
    live; nothing else in the pipeline needs to change.
    """
    # A bare string is a single address, not an iterable of chars.
    recips = (recipients,) if isinstance(recipients, str) else tuple(recipients)
    message = EmailMessage(sender=sender, recipients=recips, subject=subject, body=body)
    logger.info("EMAIL -> %s | %s", ", ".join(message.recipients), subject)
    print(
        "\n".join(
            [
                "=" * 70,
                f"[STUB EMAIL] From: {sender}",
                f"             To:   {', '.join(message.recipients)}",
                f"             Subj: {subject}",
                "-" * 70,
                body,
                "=" * 70,
            ]
        )
    )
    return message


def build_alert_email(
    decision: AlertDecision,
    *,
    major_evidence: str = "",
    minor_evidence: str = "",
    flagged_for_review: bool = False,
) -> tuple[str, str]:
    """Compose a plain-language (subject, body) for one alerting facility."""
    subject = f"[QC ALERT] {decision.site_code}: defect threshold exceeded"
    lines = [
        f"Facility {decision.site_code} breached a quality threshold and needs attention.",
        "",
        "What tripped the alert:",
    ]
    lines += [f"  - {reason}" for reason in decision.reasons]
    lines += [
        "",
        "Reading of this run:",
        f"  - Total units produced : {decision.total_products:,}",
        f"  - Major defects        : {decision.major:,}  ({decision.major_pct:.2%})",
        f"  - Minor defects        : {decision.minor:,}  ({decision.minor_pct:.2%})",
        f"  - Overall defects      : {decision.major + decision.minor:,}  ({decision.overall_pct:.2%})",
    ]
    if major_evidence or minor_evidence:
        lines += [
            "",
            "Source audit-note snippets (for verification):",
            f"  - major: \"{major_evidence}\"" if major_evidence else "",
            f"  - minor: \"{minor_evidence}\"" if minor_evidence else "",
        ]
    if flagged_for_review:
        lines += [
            "",
            "NOTE: the automated reader was uncertain about this run (low confidence "
            "or disagreement with the rule-based cross-check). Please confirm the "
            "counts against the original report before acting.",
        ]
    lines += ["", "— Automated Quality-Control Pipeline"]
    return subject, "\n".join(line for line in lines if line is not None)


def dispatch_alert(
    decision: AlertDecision,
    config: Config,
    *,
    major_evidence: str = "",
    minor_evidence: str = "",
    flagged_for_review: bool = False,
) -> EmailMessage:
    """Build and send the alert e-mail for one decision."""
    subject, body = build_alert_email(
        decision,
        major_evidence=major_evidence,
        minor_evidence=minor_evidence,
        flagged_for_review=flagged_for_review,
    )
    return send_email(config.alert_sender, config.alert_recipients, subject, body)
