"""Eval-results contract between the harness (Session A) and the report UI (Session B).

``frontend/src/schema/eval.schema.json`` and ``frontend/src/mock/eval.json`` are generated
from this file by ``scripts/export_schema.py``. Additive changes only once B builds on it.

Counts, per check (see annotations.py for the matching rule):
  hits              annotated barriers with at least one matching finding
  misses            annotated barriers with none
  matched_findings  findings that match a barrier (several can match one barrier)
  false_positives   findings inside a ``clean`` range, or of a ``not_applicable`` check
  unscored          findings in unlabelled stretches: counted in neither metric

  precision = matched_findings / (matched_findings + false_positives)
  recall    = hits / (hits + misses)

Either is null when its denominator is 0: "no evidence", never 0 % or 100 %. Always show
the raw counts next to a percentage; on this few clips one finding moves it a lot.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, computed_field

from .schemas import CheckId

EVAL_SCHEMA_VERSION = "1.0"
SystemKind = Literal["agent", "baseline"]


class Counts(BaseModel):
    hits: int = 0
    misses: int = 0
    matched_findings: int = 0
    false_positives: int = 0
    unscored: int = 0

    @computed_field
    @property
    def precision(self) -> float | None:
        scored = self.matched_findings + self.false_positives
        return round(self.matched_findings / scored, 4) if scored else None

    @computed_field
    @property
    def recall(self) -> float | None:
        barriers = self.hits + self.misses
        return round(self.hits / barriers, 4) if barriers else None


class CheckScore(Counts):
    check_id: CheckId


class ClipScore(Counts):
    clip: str
    has_report: bool = True  # False: no report for this clip, so its barriers all count as misses


class SystemEval(BaseModel):
    """One system's scores on the annotated clips."""

    system: SystemKind
    run_id: str  # frozen run name, e.g. "v1"
    provider: str  # hosts that served it, e.g. "baseten"
    model: str
    cost_usd: float  # model spend on the scored clips
    overall: Counts  # sum over checks
    per_check: list[CheckScore]  # always all 8 checks
    per_clip: list[ClipScore]


class EvalResults(BaseModel):
    schema_version: str = EVAL_SCHEMA_VERSION
    created_at: str
    match_tolerance_ms: int
    clips_scored: list[str]  # annotations with status "done"
    clips_not_annotated: int  # clips with a report but no "done" annotation: not scored
    n_barriers: int
    systems: list[SystemEval]  # agent first, then baseline if run
    note: str | None = None  # e.g. "synthetic mock numbers"
