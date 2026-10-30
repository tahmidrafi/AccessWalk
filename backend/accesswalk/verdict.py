"""Route-level verdict (d6-verdict): one rating for the whole walk, from the cited findings.

A route is a chain: one stretch a wheelchair cannot pass blocks all of it, however good
the rest is. So the rating follows the worst finding, not an average:

  likely_blocked      a high-severity finding with confidence >= ``BLOCK_CONFIDENCE``
  caution             any other finding, or a review that stopped early
  no_likely_barriers  a finished review with no findings

The rating is computed here, never taken from the model, so it cannot disagree with the
findings. Only the agent's free-text summary is the model's, and it follows our own lead
sentence once it passes the same wording rules as a finding.
"""

from __future__ import annotations

from .schemas import Finding, RouteRating, RouteVerdict
from .validator import BANNED, strip_box_colours

BLOCK_CONFIDENCE = 0.5
MAX_KEY_FINDINGS = 3
_SEVERITY_RANK = {"high": 2, "medium": 1, "low": 0}


def _blocks(f: Finding) -> bool:
    return f.severity == "high" and f.confidence >= BLOCK_CONFIDENCE


def _rating(findings: list[Finding], complete: bool) -> RouteRating:
    if any(_blocks(f) for f in findings):
        return "likely_blocked"
    return "caution" if findings or not complete else "no_likely_barriers"


def _where(f: Finding) -> str:
    return f"{f.frame_ms / 1000:.0f} s in" + (f", {f.location_tag}" if f.location_tag else "")


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _lead(rating: RouteRating, findings: list[Finding], key: list[Finding], complete: bool) -> str:
    if not findings:
        if not complete:
            return "The review stopped before it finished, so this route has not been fully checked."
        return ("No likely barriers were found on this route. "
                "This is a screening result from video: conditions can change.")
    first = sorted(
        (f for f in findings if rating != "likely_blocked" or _blocks(f)), key=lambda f: f.frame_ms
    )[0]
    n = _plural(len(findings), "likely barrier")
    if rating == "likely_blocked":
        lead = (
            f"{n} found. A wheelchair may not get past this route: first at {_where(first)} ({first.title})."
        )
    else:
        lead = f"{n} found, none clearly blocking. Top item: {key[0].title} at {_where(key[0])}."
    verify = sum(f.verify_manually for f in key)
    if verify:
        lead += " Check on site before relying on this: height, slope and width are judged from video alone."
    if not complete:
        lead += " The review stopped before it finished, so there may be more."
    return lead


def _agent_text(summary: str | None) -> str:
    text = strip_box_colours((summary or "").strip())
    return "" if not text or BANNED.search(text) else text


def route_verdict(
    findings: list[Finding], agent_summary: str | None = None, complete: bool = True
) -> RouteVerdict:
    """``complete`` is False when the agent hit its turn or budget cap before ``finish``:
    no findings then means not checked, never no barriers."""
    rating = _rating(findings, complete)
    ranked = sorted(
        findings, key=lambda f: (not _blocks(f), -_SEVERITY_RANK[f.severity], -f.confidence, f.frame_ms)
    )
    key = ranked[:MAX_KEY_FINDINGS]
    extra = _agent_text(agent_summary)
    lead = _lead(rating, findings, key, complete)
    return RouteVerdict(
        rating=rating,
        summary=f"{lead} {extra}" if extra else lead,
        key_finding_ids=[f.finding_id for f in key],
    )
