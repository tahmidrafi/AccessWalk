"""Eval scoring (d7-eval): reports against ``done`` annotations -> ``EvalResults``.

Pure functions: no model calls and nothing printed, so the owner's annotation stays blind.
The matching rule itself lives in annotations.py. Findings on clips with no ``done``
annotation are never read past the check that skips them.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import get_args

from .annotations import MATCH_TOLERANCE_MS, ClipAnnotation
from .eval_models import CheckScore, ClipScore, Counts, EvalResults, SystemEval, SystemKind
from .schemas import CheckId, Report

ALL_CHECKS: tuple[str, ...] = get_args(CheckId)
_FIELDS = ("hits", "misses", "matched_findings", "false_positives", "unscored")


def _add(into: Counts, other: Counts) -> None:
    for name in _FIELDS:
        setattr(into, name, getattr(into, name) + getattr(other, name))


def _assign(candidates: list[list[int]]) -> set[int]:
    """Barriers hit when each finding may hit at most one barrier, chosen to hit as many
    as possible (augmenting paths: overlapping barriers of one check would otherwise
    let one finding count twice, and first-come assignment can strand a barrier)."""
    owner: dict[int, int] = {}  # barrier -> finding

    def augment(f: int, seen: set[int]) -> bool:
        for b in candidates[f]:
            if b not in seen:
                seen.add(b)
                if b not in owner or augment(owner[b], seen):
                    owner[b] = f
                    return True
        return False

    for f in range(len(candidates)):
        augment(f, set())
    return set(owner)


def score_clip(ann: ClipAnnotation, report: Report | None) -> dict[str, Counts]:
    """Counts per check for one clip. No report: every barrier is a miss.
    A finding inside a barrier's window is a matched finding (so a second finding on a
    barrier already hit is not a false positive), but it hits one barrier at most."""
    out = {c: Counts() for c in ALL_CHECKS}
    findings = report.findings if report else []
    candidates = [ann.matches(f.check_id, f.frame_ms) for f in findings]
    found = _assign(candidates)
    for f, matched in zip(findings, candidates, strict=True):
        if matched:
            out[f.check_id].matched_findings += 1
        elif ann.is_false_positive(f.check_id, f.frame_ms):
            out[f.check_id].false_positives += 1
        else:
            out[f.check_id].unscored += 1
    for i, b in enumerate(ann.barriers):
        if i in found:
            out[b.check].hits += 1
        else:
            out[b.check].misses += 1
    return out


def score_system(
    system: SystemKind,
    run_id: str,
    annotations: Mapping[str, ClipAnnotation],
    reports: Mapping[str, Report],
) -> SystemEval:
    per_check = {c: CheckScore(check_id=c) for c in ALL_CHECKS}
    overall = Counts()
    per_clip: list[ClipScore] = []
    for clip, ann in sorted(annotations.items()):
        report = reports.get(clip)
        row = ClipScore(clip=clip, has_report=report is not None)
        for check, counts in score_clip(ann, report).items():
            _add(per_check[check], counts)
            _add(row, counts)
            _add(overall, counts)
        per_clip.append(row)
    used = [reports[c] for c in annotations if c in reports]
    return SystemEval(
        system=system,
        run_id=run_id,
        provider="+".join(sorted({r.run.agent_provider for r in used})) or "none",
        model="+".join(sorted({r.run.agent_model for r in used})) or "none",
        cost_usd=round(sum(r.run.cost_usd for r in used), 4),
        overall=overall,
        per_check=list(per_check.values()),
        per_clip=per_clip,
    )


WIDTH_CHECKS = ("sidewalk_obstruction", "narrow_passage")  # one "width" check when merged


def merge_width_annotation(ann: ClipAnnotation) -> ClipAnnotation:
    """``ann`` with narrow_passage read as sidewalk_obstruction: whether a car or pole
    'blocks' or 'narrows' the walk is a judgement call, and this score ignores it. The
    merged check is not applicable only where both were."""
    keep, into = WIDTH_CHECKS
    na = [c for c in ann.not_applicable if c != into]
    if keep in na and into not in ann.not_applicable:
        na.remove(keep)
    return ann.model_copy(update={
        "barriers": [b.model_copy(update={"check": keep}) if b.check == into else b for b in ann.barriers],
        "not_applicable": na,
    })


def merge_width_report(report: Report) -> Report:
    keep, into = WIDTH_CHECKS
    return report.model_copy(update={"findings": [
        f.model_copy(update={"check_id": keep}) if f.check_id == into else f for f in report.findings
    ]})


def load_reports(run_dir: str | Path) -> dict[str, Report]:
    """Reports of one run, keyed by clip stem (the file name). ``_``-prefixed files are stats."""
    return {
        p.stem: Report.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(Path(run_dir).glob("*.json"))
        if not p.name.startswith("_")
    }


def evaluate(
    annotations: Mapping[str, ClipAnnotation],
    systems: list[tuple[SystemKind, str, Mapping[str, Report]]],
    note: str | None = None,
) -> EvalResults:
    """``annotations`` must hold only ``done`` files (``annotations.load_all`` does this)."""
    draft = [c for c, a in annotations.items() if a.status != "done"]
    if draft:
        raise ValueError(f"only done annotations are scored; got drafts: {draft}")
    reported = {clip for _, _, reports in systems for clip in reports}
    return EvalResults(
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        match_tolerance_ms=MATCH_TOLERANCE_MS,
        clips_scored=sorted(annotations),
        clips_not_annotated=len(reported - set(annotations)),
        n_barriers=sum(len(a.barriers) for a in annotations.values()),
        systems=[score_system(kind, run, annotations, reports) for kind, run, reports in systems],
        note=note,
    )
