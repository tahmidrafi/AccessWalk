"""Two-tier and ensemble combination on the mock report. No network."""
from pathlib import Path

from accesswalk.combine import POSSIBLE_PREFIX, ensemble, two_tier
from accesswalk.schemas import Report, Track, TrackBox

REPO_ROOT = Path(__file__).resolve().parents[2]
MOCK = Report.model_validate_json((REPO_ROOT / "frontend" / "src" / "mock" / "report.json").read_text())


def _with(report: Report, *specs) -> Report:
    """Copy of ``report`` whose findings are (check, ms, grounded?) built from its first finding."""
    f0, t0 = report.findings[0], next(t for t in report.tracks if t.track_id == report.findings[0].track_id)
    tracks, findings = [], []
    for i, (check, ms, grounded) in enumerate(specs):
        tid = f"{'obj' if grounded else 'baseline'}-{i}"
        box = TrackBox(frame_index=f0.frame_index, frame_ms=ms, x1=1, y1=1, x2=9, y2=9)
        tracks.append(Track(track_id=tid, phrase="trash bin" if grounded else "baseline (no SAM track)",
                            object_id=i, first_ms=ms, last_ms=ms, n_frames=1, keyframe_index=f0.frame_index,
                            keyframe_ms=ms, boxes=[box]))
        findings.append(f0.model_copy(update={"finding_id": f"f{i}", "check_id": check, "frame_ms": ms,
                                              "track_id": tid}))
    assert t0  # the mock has a cited track to copy from
    return report.model_copy(update={"tracks": tracks, "findings": findings})


def test_two_tier_adds_unmatched_raw_findings_as_possible():
    conf = _with(MOCK, ("surface_damage", 10_000, True))
    poss = _with(MOCK, ("surface_damage", 10_800, False), ("steps_without_ramp", 20_000, False))
    out = two_tier(conf, poss, "e4")
    assert [(f.check_id, f.frame_ms) for f in out.findings] == [("surface_damage", 10_000),
                                                                ("steps_without_ramp", 20_000)]
    possible = out.findings[1]
    assert possible.verify_manually and possible.evidence_note.startswith(POSSIBLE_PREFIX)
    assert out.run.cost_usd == round(conf.run.cost_usd + poss.run.cost_usd, 4)


def test_ensemble_keeps_agreement_and_grounded_singles_only():
    a = _with(MOCK, ("surface_damage", 10_000, True))
    b = _with(MOCK, ("surface_damage", 10_500, True), ("narrow_passage", 30_000, True))
    raw = _with(MOCK, ("steps_without_ramp", 20_000, False), ("narrow_passage", 30_400, False))
    out = ensemble([a, b], raw, "e7")
    assert [(f.check_id, f.frame_ms) for f in out.findings] == [("surface_damage", 10_000),
                                                                ("narrow_passage", 30_000)]
