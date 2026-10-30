"""Citation validator (d5-validator): the gate between the agent and the report.

The agent proposes a finding through ``cite_finding``; this module turns the
proposal into a ``schemas.Finding`` or rejects it with a reason the agent can
act on. A finding survives only if it is grounded:

  * the check exists in rules.yaml;
  * the cited track exists in this clip's inventory (plate tracks never do);
  * the track's phrase is one of the check's ``evidence_phrases`` (no citing a
    car as surface damage);
  * the track has a box on the cited frame -- the box is copied from the track,
    never taken from the model, so a finding's overlay is always SAM's box;
  * related tracks exist;
  * the wording says "likely barrier", never "violation" / "non-compliant".

``verify_manually`` comes from the rule, not the model. ``finalize`` merges
repeat citations of the same object for the same check and numbers findings in
time order. Findings that never pass validation are dropped from the report.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field, ValidationError

from .ingest import IngestMeta
from .inventory import Inventory
from .rules import Rules
from .schemas import BBox, Finding

BANNED = re.compile(
    r"\b(violat\w*|non-?complian\w*|illegal|unlawful|out of compliance|ada compliant)\b", re.I
)

# The agent sees view_frame's coloured boxes; the report draws its own overlay, so a
# note like "the slab in the red box" points at nothing. Strip such references.
_COLOR = r"(?:red|green|blue|orange|yellow|cyan|magenta|purple|pink|white|black|grey|gray)"
_SHAPE = r"(?:box(?:es)?|rectangles?|outlines?|bounding boxes|highlights?|markers?)"
_BOX_REFS = [
    # " in the red box", " (inside the green rectangle)", " shown in the blue outline"
    re.compile(rf"\s*\(?\b(?:shown\s+|marked\s+|seen\s+)?(?:in|inside|within|by|at|under)\s+the\s+"
               rf"{_COLOR}(?:[- ]{_COLOR})?\s+{_SHAPE}\)?", re.I),
    # " boxed in red", " outlined in yellow", " highlighted in green"
    re.compile(rf"\s*\b(?:boxed|outlined|highlighted|marked)\s+in\s+{_COLOR}\b", re.I),
    # "red-boxed slab" -> "slab"
    re.compile(rf"\b{_COLOR}[- ](?:boxed|outlined|highlighted)\s+", re.I),
]
# "the red box shows" -> "the marked area shows"
_BOX_SUBJECT = re.compile(rf"\bthe\s+{_COLOR}\s+{_SHAPE}\b", re.I)


def strip_box_colours(text: str) -> str:
    """Remove references to box colours from model-written text."""
    for pat in _BOX_REFS:
        text = pat.sub("", text)
    text = _BOX_SUBJECT.sub("the marked area", text)
    text = re.sub(r"\s+([,.;:)])", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text[:1].upper() + text[1:]  # keep sentence case after a leading removal


class CitationRequest(BaseModel):
    """Arguments of the agent's ``cite_finding`` tool call."""

    check_id: str
    track_id: str
    frame_index: int
    severity: str
    confidence: float = Field(ge=0, le=1)
    title: str = Field(min_length=3, max_length=90)
    evidence_note: str = Field(min_length=20, max_length=600)
    related_track_ids: list[str] = Field(default_factory=list)
    location_tag: str | None = None


class Rejection(BaseModel):
    request: dict
    reason: str


def validate_citation(
    raw: dict, inv: Inventory, meta: IngestMeta, rules: Rules,
    extra_phrases: dict[str, set[str]] | None = None,
) -> Finding | Rejection:
    """``extra_phrases`` (check_id -> phrases) admits tracks the agent made with
    ``recheck_with_sam`` for that check, on top of the rule's evidence phrases."""
    try:
        req = CitationRequest.model_validate(raw)
    except ValidationError as e:
        return Rejection(request=raw, reason=f"bad arguments: {e.errors()[0]['loc']}: {e.errors()[0]['msg']}")
    req = req.model_copy(update={"title": strip_box_colours(req.title),
                                 "evidence_note": strip_box_colours(req.evidence_note)})
    if len(req.evidence_note) < 20:
        return Rejection(request=raw, reason="evidence_note is too short once box colours are removed: "
                                             "describe the object and where it is")

    rule = rules.checks.get(req.check_id)  # type: ignore[call-overload]
    if rule is None:
        return Rejection(
            request=raw, reason=f"unknown check_id {req.check_id!r}; use one of {sorted(rules.checks)}"
        )
    tracks = {t.track_id: t for t in inv.tracks}
    track = tracks.get(req.track_id)
    if track is None:
        return Rejection(request=raw, reason=f"track {req.track_id!r} is not in this clip's inventory")
    allowed = set(rule.evidence_phrases) | (extra_phrases or {}).get(req.check_id, set())
    if track.phrase not in allowed:
        return Rejection(
            request=raw,
            reason=f"{req.check_id} must cite a track of {sorted(allowed)}, not {track.phrase!r}",
        )
    box = next((b for b in track.boxes if b.frame_index == req.frame_index), None)
    if box is None:
        frames = [b.frame_index for b in track.boxes]
        return Rejection(
            request=raw,
            reason=f"track {req.track_id} has no box on frame {req.frame_index}; "
                   f"it is visible on frames {frames[0]}-{frames[-1]} (keyframe {track.keyframe_index})",
        )
    unknown = [r for r in req.related_track_ids if r not in tracks]
    if unknown:
        return Rejection(request=raw, reason=f"related tracks not in inventory: {unknown}")
    if req.severity not in rule.severity:
        return Rejection(request=raw, reason=f"severity must be one of {sorted(rule.severity)}")
    for text in (req.title, req.evidence_note):
        hit = BANNED.search(text)
        if hit:
            return Rejection(
                request=raw,
                reason=f"wording {hit.group(0)!r} is not allowed: describe a likely barrier, not a violation",
            )

    return Finding(
        finding_id="pending",
        check_id=req.check_id,  # type: ignore[arg-type]
        title=req.title,
        severity=req.severity,  # type: ignore[arg-type]
        confidence=round(req.confidence, 2),
        track_id=track.track_id,
        frame_index=box.frame_index,
        frame_ms=meta.frame_ms[box.frame_index],
        bbox=BBox(x1=box.x1, y1=box.y1, x2=box.x2, y2=box.y2),
        evidence_note=req.evidence_note,
        location_tag=req.location_tag,
        verify_manually=rule.verify_manually == "always",
        reference=rule.reference,
        related_track_ids=req.related_track_ids,
        frame_url=f"/media/{meta.video_sha256}/frames/{box.frame_index}.jpg",
    )


def finalize(findings: list[Finding]) -> list[Finding]:
    """One finding per (check, object): keep the most confident citation. Then
    number them f1..fn in time order."""
    best: dict[tuple[str, str], Finding] = {}
    for f in findings:
        key = (f.check_id, f.track_id)
        if key not in best or f.confidence > best[key].confidence:
            best[key] = f
    ordered = sorted(best.values(), key=lambda f: (f.frame_ms, f.check_id))
    return [f.model_copy(update={"finding_id": f"f{i}"}) for i, f in enumerate(ordered, start=1)]
