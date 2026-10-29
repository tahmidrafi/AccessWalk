"""Report contract between the pipeline (Session A) and the report UI (Session B).

Frozen on Oct 29 (M3). Only Session A edits this file; every change regenerates
``frontend/src/schema/report.schema.json`` and ``frontend/src/mock/report.json``
in the same commit (``scripts/export_schema.py``). After the freeze, changes are
additive only: new optional fields, never renamed or removed ones.

Conventions:
  * Times are integer milliseconds on the clip timeline (``sam.mp4`` and
    ``proxy.mp4`` share it). ``frame_index`` is an index into ``sam.mp4``.
  * Boxes are pixels in the ``sam.mp4`` frame (``Report.video.width/height``);
    ``proxy.mp4`` has the same dimensions, so they overlay 1:1 on the player.
  * Wording is "likely barrier" / "verify manually", never "violation". This is a
    pre-trip screening tool, not a compliance certification.

Grounding rule (enforced here, not only in the agent): every ``Finding`` must cite
a ``track_id`` present in ``Report.tracks`` and a ``frame_index`` at which that
track has a box. A report that breaks this does not validate.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION = "1.0"

CheckId = Literal[
    "sidewalk_obstruction",
    "surface_damage",
    "missing_curb_ramp",
    "sidewalk_ends",
    "steps_without_ramp",
    "missing_handrail",
    "round_doorknob",
    "narrow_passage",
]
Severity = Literal["low", "medium", "high"]

DISCLAIMER = (
    "Pre-trip screening from a phone video. Findings are likely barriers, not compliance "
    "determinations. Items marked 'verify manually' rest on depth, height or slope judged "
    "from video alone."
)


class BBox(BaseModel):
    """Axis-aligned box in ``sam.mp4`` pixels."""

    x1: int
    y1: int
    x2: int
    y2: int


class TrackBox(BBox):
    """One tracked object on one ``sam.mp4`` frame."""

    frame_index: int
    frame_ms: int
    conf: float | None = Field(default=None, ge=0, le=1)


class Track(BaseModel):
    """One object instance followed across frames by SAM 3.1.

    ``track_id`` is unique within a report: ``<phrase-slug>-<object_id>``, e.g.
    ``trash-bin-0``. ``object_id`` is SAM's ordinal for that phrase request."""

    track_id: str
    phrase: str
    object_id: int
    first_ms: int
    last_ms: int
    n_frames: int
    mean_conf: float | None = Field(default=None, ge=0, le=1)
    keyframe_index: int  # best frame for this object (inventory step)
    keyframe_ms: int
    keyframe_url: str | None = None  # blurred keyframe image with the box drawn
    mask_url: str | None = None  # keyframe mask PNG (transparent background), if rendered
    boxes: list[TrackBox]


class Finding(BaseModel):
    """One likely barrier, cited to a track and a frame."""

    finding_id: str
    check_id: CheckId
    title: str  # one line for the list view, e.g. "Trash bin narrows the sidewalk"
    severity: Severity
    confidence: float = Field(ge=0, le=1)
    track_id: str
    frame_index: int
    frame_ms: int
    bbox: BBox
    evidence_note: str  # what the agent saw, in plain words; says why if verify_manually
    location_tag: str | None = None  # from narration ("bus stop"); None on silent clips
    verify_manually: bool
    reference: str | None = None  # guideline the rule is based on, from the rules YAML
    related_track_ids: list[str] = Field(default_factory=list)  # other objects in the evidence
    frame_url: str | None = None  # blurred evidence frame with the box drawn


class CheckSummary(BaseModel):
    """What happened to each check on this route, so absence of findings is explicit."""

    check_id: CheckId
    status: Literal["ran", "not_applicable", "dropped"]
    n_findings: int = 0
    note: str | None = None  # e.g. "dropped: precision below threshold in eval"


class LocationTag(BaseModel):
    """A stretch of the route named in the narration (Muse Voice Transcribe)."""

    start_ms: int
    end_ms: int
    label: str


class VideoInfo(BaseModel):
    video_sha256: str
    duration_ms: int
    width: int  # sam.mp4 / proxy.mp4 pixel size (box coordinate space)
    height: int
    sam_fps: float
    proxy_url: str | None = None  # H.264 proxy the report page plays
    frame_ms: list[int]  # sam.mp4 frame_index -> ms


class RouteVerdict(BaseModel):
    rating: Literal["no_likely_barriers", "caution", "likely_blocked"]
    summary: str
    key_finding_ids: list[str] = Field(default_factory=list)


class RunInfo(BaseModel):
    """Provenance. ``agent_model`` is what actually served the agent calls (logged
    per call in ``usage.jsonl``); it is shown in the report for open-weight checks."""

    agent_provider: str  # "baseten" | "fireworks" | "meta" | "mock"
    agent_model: str
    sam_model: str
    n_model_calls: int = 0
    cost_usd: float = 0.0
    created_at: str


class Report(BaseModel):
    schema_version: str = SCHEMA_VERSION
    report_id: str
    title: str
    video: VideoInfo
    verdict: RouteVerdict
    findings: list[Finding]
    tracks: list[Track]
    checks: list[CheckSummary]
    location_tags: list[LocationTag] = Field(default_factory=list)
    run: RunInfo
    disclaimer: str = DISCLAIMER

    @model_validator(mode="after")
    def _findings_are_grounded(self) -> Report:
        frames_by_track = {t.track_id: {b.frame_index for b in t.boxes} for t in self.tracks}
        if len(frames_by_track) != len(self.tracks):
            raise ValueError("duplicate track_id in tracks")
        finding_ids = {f.finding_id for f in self.findings}
        if len(finding_ids) != len(self.findings):
            raise ValueError("duplicate finding_id in findings")
        for f in self.findings:
            frames = frames_by_track.get(f.track_id)
            if frames is None:
                raise ValueError(f"finding {f.finding_id} cites unknown track {f.track_id}")
            if f.frame_index not in frames:
                raise ValueError(
                    f"finding {f.finding_id} cites frame {f.frame_index}, "
                    f"where track {f.track_id} has no box"
                )
            for rid in f.related_track_ids:
                if rid not in frames_by_track:
                    raise ValueError(f"finding {f.finding_id} relates unknown track {rid}")
        for fid in self.verdict.key_finding_ids:
            if fid not in finding_ids:
                raise ValueError(f"verdict cites unknown finding {fid}")
        return self
