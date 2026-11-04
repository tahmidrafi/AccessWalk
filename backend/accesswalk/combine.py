"""Combine reports of several systems on one clip, with no model calls.

  two_tier   every finding of the confirmed report, plus each finding of a second report that no
             confirmed finding matches (same check, within 1 s), kept as "possible": marked
             verify_manually, and its note says when it has no SAM track behind it.
  ensemble   a finding is kept when at least two systems agree on check and time (within 1 s),
             plus any single-system finding with a valid track citation. Agreeing findings are
             merged; the first system's copy is kept.

Cost and model fields of the result are the sum and union of the inputs.
"""
from __future__ import annotations

from .annotations import MATCH_TOLERANCE_MS
from .schemas import Finding, Report
from .verdict import route_verdict

POSSIBLE_PREFIX = "Possible barrier, seen by the raw-video pass only (no SAM track behind it). "


def agree(a: Finding, b: Finding) -> bool:
    return a.check_id == b.check_id and abs(a.frame_ms - b.frame_ms) <= MATCH_TOLERANCE_MS


def _is_grounded(r: Report, f: Finding) -> bool:
    t = next((t for t in r.tracks if t.track_id == f.track_id), None)
    return t is not None and not t.phrase.startswith("baseline")


def merge(base: Report, parts: list[tuple[Report, Finding]], run_id: str, sources: list[Report]) -> Report:
    tracks = {t.track_id: t for t in base.tracks}
    for r, f in parts:
        t = next(t for t in r.tracks if t.track_id == f.track_id)
        if t.track_id in tracks and tracks[t.track_id] != t:  # same id, other run: keep both
            t = t.model_copy(update={"track_id": f"{run_id}-{t.track_id}"})
            f = f.model_copy(update={"track_id": t.track_id})
        tracks.setdefault(t.track_id, t)
    findings = sorted([f for _, f in parts], key=lambda f: (f.frame_ms, f.check_id))
    findings = [f.model_copy(update={"finding_id": f"f{i}"}) for i, f in enumerate(findings, start=1)]
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.check_id] = counts.get(f.check_id, 0) + 1
    run = base.run.model_copy(update={
        "agent_provider": "+".join(dict.fromkeys(r.run.agent_provider for r in sources)),
        "agent_model": "+".join(dict.fromkeys(r.run.agent_model for r in sources)),
        "n_model_calls": sum(r.run.n_model_calls for r in sources),
        "cost_usd": round(sum(r.run.cost_usd for r in sources), 4),
        "used_closed_fallback": any(r.run.used_closed_fallback for r in sources),
    })
    return base.model_copy(update={
        "report_id": f"{run_id}-{base.video.video_sha256[:12]}",
        "findings": findings,
        "tracks": list(tracks.values()),
        "checks": [c.model_copy(update={"n_findings": counts.get(c.check_id, 0)}) for c in base.checks],
        "verdict": route_verdict(findings, None, complete=True),
        "run": run,
    })


def two_tier(conf: Report, poss: Report, run_id: str) -> Report:
    parts = [(conf, f) for f in conf.findings]
    for f in poss.findings:
        if any(agree(f, c) for c in conf.findings):
            continue
        note = f.evidence_note
        if not _is_grounded(poss, f):
            note = POSSIBLE_PREFIX + note
        parts.append((poss, f.model_copy(update={"verify_manually": True, "evidence_note": note[:900],
                                                  "tier": "possible"})))
    return merge(conf, parts, run_id, [conf, poss])


def ensemble(grounded: list[Report], other: Report, run_id: str) -> Report:
    systems = [*grounded, other]
    parts: list[tuple[Report, Finding]] = []
    for i, r in enumerate(systems):
        for f in r.findings:
            if any(agree(f, g) for _, g in parts):
                continue  # an earlier system's copy of the same barrier is kept
            votes = sum(any(agree(f, g) for g in s.findings) for s in systems)
            if votes >= 2 or (i < len(grounded) and _is_grounded(r, f)):
                parts.append((r, f))
    return merge(grounded[0], parts, run_id, systems)
