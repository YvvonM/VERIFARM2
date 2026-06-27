"""Deterministic resolution policy for flagged conflicts.

This is the agent's decision core. Given a variance (how far a reported value
strays from ground truth) and the attesting source's reputation + track record,
:func:`recommend` returns a calculated :class:`Recommendation` — action,
severity, confidence and a plain-language rationale.

It is deliberately a **pure function** of its inputs (no I/O, no LLM): every
flag the investigator writes is reproducible and auditable, which is the whole
point of a data-quality control. An LLM may later *rephrase* the rationale for
humans (see :mod:`app.investigator.investigator`), but never changes the verdict.

Ground truth is authoritative by construction, so the reported value is always
the suspect one. The decision is really about the *source*: penalize a
low-trust or repeat offender, escalate a surprising disagreement from a
reliable source, or simply adopt ground truth.
"""

from __future__ import annotations

from app.models.investigation import (
    ConflictSeverity,
    Recommendation,
    ResolutionAction,
    SourceHistory,
)

# Severity cut-offs on relative variance (0.30 == 30% off ground truth).
HIGH_VARIANCE = 0.30
CRITICAL_VARIANCE = 0.50

# Trust bands for the attesting source.
LOW_TRUST = 0.40
HIGH_TRUST = 0.70

# A source is a "repeat offender" at/above this many current conflicts.
REPEAT_OFFENDER_CONFLICTS = 3
# Agreement rate this poor (with enough comparisons) signals an unreliable source.
POOR_AGREEMENT_RATE = 0.50
MIN_COMPARISONS_FOR_RATE = 4


def severity_for(variance: float) -> ConflictSeverity:
    """Bucket a relative variance into a severity band."""
    if variance >= CRITICAL_VARIANCE:
        return ConflictSeverity.CRITICAL
    if variance >= HIGH_VARIANCE:
        return ConflictSeverity.HIGH
    return ConflictSeverity.MODERATE


def _is_unreliable(source: SourceHistory) -> bool:
    """Whether history marks this source as a pattern offender."""
    if source.prior_conflicts >= REPEAT_OFFENDER_CONFLICTS:
        return True
    rate = source.agreement_rate
    return (
        rate is not None
        and source.comparisons >= MIN_COMPARISONS_FOR_RATE
        and rate < POOR_AGREEMENT_RATE
    )


def recommend(
    variance: float,
    source: SourceHistory,
    authoritative_value: float,
    reported_value: float,
    claim_type: str,
) -> Recommendation:
    """Compute the resolution recommendation for one conflict."""
    severity = severity_for(variance)
    unreliable = _is_unreliable(source)
    pct = round(variance * 100)

    # --- choose the action -------------------------------------------------
    if source.trust_score < LOW_TRUST or unreliable:
        action = ResolutionAction.PENALIZE_SOURCE
    elif source.trust_score >= HIGH_TRUST and source.prior_conflicts == 0:
        # A reliable source disagreeing in isolation is surprising, not damning.
        action = ResolutionAction.FLAG_FOR_REVIEW
    elif source.comparisons == 0 and source.prior_conflicts == 0 and severity == ConflictSeverity.MODERATE:
        # Borderline variance from an as-yet-unscored source: not enough to act on.
        action = ResolutionAction.INSUFFICIENT_DATA
    else:
        action = ResolutionAction.TRUST_GROUND_TRUTH

    # --- confidence --------------------------------------------------------
    confidence = 0.5
    if severity == ConflictSeverity.CRITICAL:
        confidence += 0.2
    elif severity == ConflictSeverity.HIGH:
        confidence += 0.1
    if source.comparisons >= MIN_COMPARISONS_FOR_RATE:
        confidence += 0.15
    if source.prior_conflicts >= REPEAT_OFFENDER_CONFLICTS:
        confidence += 0.1
    if action == ResolutionAction.FLAG_FOR_REVIEW:
        confidence -= 0.15  # escalation is inherently less certain
    if action == ResolutionAction.INSUFFICIENT_DATA:
        confidence = min(confidence, 0.4)
    confidence = round(max(0.0, min(0.95, confidence)), 2)

    # --- rationale ---------------------------------------------------------
    rationale = _build_rationale(
        action, severity, source, claim_type,
        authoritative_value, reported_value, pct, unreliable,
    )
    return Recommendation(
        action=action, severity=severity, confidence=confidence, rationale=rationale
    )


def _build_rationale(
    action: ResolutionAction,
    severity: ConflictSeverity,
    source: SourceHistory,
    claim_type: str,
    authoritative_value: float,
    reported_value: float,
    pct: int,
    unreliable: bool,
) -> str:
    """Assemble a deterministic, human-readable justification."""
    name = source.institution_name or source.institution_id
    rate = source.agreement_rate
    rate_txt = f"{round(rate * 100)}% agreement over {source.comparisons} checks" if rate is not None else "no prior ground-truth checks"

    head = (
        f"{name} (trust {source.trust_score:.2f}) reported {reported_value:g} for "
        f"'{claim_type}' vs ground truth {authoritative_value:g} — {pct}% variance "
        f"({severity.value.lower()}). History: {rate_txt}, {source.prior_conflicts} "
        f"current conflict(s)."
    )

    tail = {
        ResolutionAction.PENALIZE_SOURCE: (
            " Source is low-trust or a repeat offender → adopt the authoritative value "
            "and recommend a reputation penalty."
        ),
        ResolutionAction.FLAG_FOR_REVIEW: (
            " Source is generally reliable, so this isolated disagreement likely reflects "
            "a data-entry error or a genuine change → escalate to a human steward."
        ),
        ResolutionAction.TRUST_GROUND_TRUTH: (
            " → Adopt the authoritative value into the gold layer; demote the reported claim."
        ),
        ResolutionAction.INSUFFICIENT_DATA: (
            " Variance is borderline and the source has no track record yet → hold for review "
            "until more evidence accrues."
        ),
    }[action]
    return head + tail
