"""Ground-truth annotations for eval: ``data/annotations/<clip>.json``.

Written by hand while watching the clip, so the format favours typing speed:
times are seconds as shown by a video player (converted to ms here), checks
use the report ``check_id`` names, severity uses the report bins.

Scoring rules (eval, d7):
  * a finding matches a barrier when the check is the same and its frame time
    is inside the barrier's time range, widened by ``MATCH_TOLERANCE_MS``;
  * a finding inside a ``clean`` range, or of a check listed in
    ``not_applicable``, is a false positive;
  * a finding elsewhere (not in any barrier or clean range) is not scored;
  * only files with ``"status": "done"`` count.
See data/annotations/README.md for the how-to.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .schemas import CheckId, Severity

REPO_ROOT = Path(__file__).resolve().parents[2]
ANNOTATIONS_DIR = REPO_ROOT / "data" / "annotations"
MATCH_TOLERANCE_MS = 1000

TimeRange = tuple[float, float]  # seconds, [start, end]


def _ms(s: float) -> int:
    return round(s * 1000)


class Barrier(BaseModel):
    check: CheckId
    t: TimeRange  # seconds while the barrier is visible
    sev: Severity
    note: str = Field(min_length=1)
    verify: bool = False  # you could not judge it from the video either

    @property
    def start_ms(self) -> int:
        return _ms(self.t[0])

    @property
    def end_ms(self) -> int:
        return _ms(self.t[1])


class ClipAnnotation(BaseModel):
    clip: str  # raw file stem, e.g. PXL_20261027_211833467
    annotator: str
    status: Literal["draft", "done"]
    duration_s: float
    barriers: list[Barrier] = Field(default_factory=list)
    clean: list[TimeRange] = Field(default_factory=list)  # stretches with no barrier of any check
    not_applicable: list[CheckId] = Field(default_factory=list)  # checks that cannot occur here
    notes: str = ""

    @model_validator(mode="after")
    def _ranges_are_sane(self) -> ClipAnnotation:
        ranges = [("barrier " + b.check, b.t) for b in self.barriers] + [("clean", c) for c in self.clean]
        for name, (a, b) in ranges:
            if not 0 <= a < b <= self.duration_s + 0.5:
                raise ValueError(f"{name} range {a}-{b} s is not inside 0-{self.duration_s} s")
        for c0, c1 in self.clean:
            for b in self.barriers:
                if b.t[0] < c1 and c0 < b.t[1]:
                    raise ValueError(
                        f"clean range {c0}-{c1} s overlaps barrier {b.check} {b.t[0]}-{b.t[1]} s"
                    )
        for b in self.barriers:
            if b.check in self.not_applicable:
                raise ValueError(f"{b.check} is listed as not_applicable but has a barrier")
        return self

    def matches(self, check_id: str, frame_ms: int) -> list[int]:
        """Indices of barriers a finding (check, time) would match."""
        return [
            i for i, b in enumerate(self.barriers)
            if b.check == check_id
            and b.start_ms - MATCH_TOLERANCE_MS <= frame_ms <= b.end_ms + MATCH_TOLERANCE_MS
        ]

    def is_false_positive(self, check_id: str, frame_ms: int) -> bool:
        if check_id in self.not_applicable:
            return True
        if self.matches(check_id, frame_ms):
            return False
        return any(_ms(a) <= frame_ms <= _ms(b) for a, b in self.clean)


def load(path: str | Path) -> ClipAnnotation:
    return ClipAnnotation.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def load_all(root: str | Path = ANNOTATIONS_DIR, done_only: bool = True) -> dict[str, ClipAnnotation]:
    out = {}
    for p in sorted(Path(root).glob("*.json")):
        ann = load(p)
        if ann.clip != p.stem:
            raise ValueError(f"{p.name}: clip field {ann.clip!r} does not match the file name")
        if ann.status == "done" or not done_only:
            out[ann.clip] = ann
    return out
