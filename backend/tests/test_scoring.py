"""Eval scoring on synthetic annotations and findings only: no real clip, report or label."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from accesswalk.annotations import ClipAnnotation
from accesswalk.eval_models import EvalResults
from accesswalk.scoring import ALL_CHECKS, evaluate, score_clip, score_system

REPO_ROOT = Path(__file__).resolve().parents[2]


def _ann(clip="c1", status="done", **kw) -> ClipAnnotation:
    return ClipAnnotation.model_validate(
        {"clip": clip, "annotator": "t", "status": status, "duration_s": 60.0, **kw}
    )


def _barrier(check, a, b):
    return {"check": check, "t": [a, b], "sev": "medium", "note": "n"}


def _report(*findings, cost=0.1):
    fs = [SimpleNamespace(check_id=c, frame_ms=ms) for c, ms in findings]
    run = SimpleNamespace(agent_provider="baseten", agent_model="m", cost_usd=cost)
    return SimpleNamespace(findings=fs, run=run)


def test_every_outcome_counted_once():
    ann = _ann(
        barriers=[_barrier("surface_damage", 10, 12), _barrier("surface_damage", 20, 22)],
        clean=[[0, 5]],
        not_applicable=["round_doorknob"],
    )
    c = score_clip(
        ann,
        _report(
            ("surface_damage", 11000),
            ("sidewalk_obstruction", 2000),
            ("round_doorknob", 30000),
            ("narrow_passage", 30000),
        ),
    )
    assert (c["surface_damage"].hits, c["surface_damage"].misses, c["surface_damage"].matched_findings) == (
        1,
        1,
        1,
    )
    assert c["sidewalk_obstruction"].false_positives == 1
    assert c["round_doorknob"].false_positives == 1
    assert c["narrow_passage"].unscored == 1


def test_tolerance_is_one_second_on_either_side():
    ann = _ann(barriers=[_barrier("surface_damage", 10, 12)])
    inside = [("surface_damage", 9000), ("surface_damage", 13000)]
    outside = [("surface_damage", 8999), ("surface_damage", 13001)]
    assert score_clip(ann, _report(*inside))["surface_damage"].matched_findings == 2
    c = score_clip(ann, _report(*outside))["surface_damage"]
    assert (c.matched_findings, c.unscored, c.misses) == (0, 2, 1)


def test_several_findings_on_one_barrier_are_one_hit():
    ann = _ann(barriers=[_barrier("surface_damage", 10, 12)])
    c = score_clip(ann, _report(("surface_damage", 10000), ("surface_damage", 11000)))["surface_damage"]
    assert (c.hits, c.matched_findings, c.precision, c.recall) == (1, 2, 1.0, 1.0)


def test_one_finding_can_hit_two_overlapping_barriers():
    ann = _ann(barriers=[_barrier("surface_damage", 10, 12), _barrier("surface_damage", 11, 14)])
    c = score_clip(ann, _report(("surface_damage", 11500)))["surface_damage"]
    assert (c.hits, c.misses, c.matched_findings) == (2, 0, 1)


def test_finding_of_another_check_on_a_barrier_is_unscored_not_a_hit():
    ann = _ann(barriers=[_barrier("surface_damage", 10, 12)])
    c = score_clip(ann, _report(("narrow_passage", 11000)))
    assert c["narrow_passage"].unscored == 1 and c["surface_damage"].misses == 1


def test_no_evidence_is_null_not_zero():
    s = score_system("agent", "r", {"c1": _ann()}, {"c1": _report()})
    assert all(c.precision is None and c.recall is None for c in s.per_check)
    assert [c.check_id for c in s.per_check] == list(ALL_CHECKS)


def test_all_false_positives_is_zero_precision():
    s = score_system("agent", "r", {"c1": _ann(clean=[[0, 60]])}, {"c1": _report(("surface_damage", 5000))})
    assert s.overall.precision == 0.0 and s.overall.recall is None


def test_missing_report_counts_barriers_as_misses_and_says_so():
    s = score_system("agent", "r", {"c1": _ann(barriers=[_barrier("surface_damage", 10, 12)])}, {})
    assert s.overall.misses == 1 and s.per_clip[0].has_report is False


def test_results_sum_across_clips_and_count_unannotated_reports():
    anns = {
        "c1": _ann("c1", barriers=[_barrier("surface_damage", 10, 12)]),
        "c2": _ann("c2", barriers=[_barrier("surface_damage", 10, 12)], clean=[[0, 5]]),
    }
    reports = {
        "c1": _report(("surface_damage", 11000)),
        "c2": _report(("surface_damage", 1000)),
        "c3": _report(("surface_damage", 1000)),
    }
    r = evaluate(anns, [("agent", "v1", reports)])
    s = r.systems[0]
    assert (s.overall.hits, s.overall.misses, s.overall.false_positives) == (1, 1, 1)
    assert s.cost_usd == 0.2  # c3 has no annotation: neither scored nor costed
    assert (r.clips_scored, r.clips_not_annotated, r.n_barriers) == (["c1", "c2"], 1, 2)


def test_drafts_are_refused():
    with pytest.raises(ValueError, match="only done"):
        evaluate({"c1": _ann(status="draft")}, [("agent", "v1", {})])


def test_eval_contract_exported_and_mock_valid():
    schema = REPO_ROOT / "frontend" / "src" / "schema" / "eval.schema.json"
    assert json.loads(schema.read_text()) == EvalResults.model_json_schema(mode="serialization"), (
        "eval.schema.json is stale: run scripts/export_schema.py"
    )
    mock = EvalResults.model_validate_json(
        (REPO_ROOT / "frontend" / "src" / "mock" / "eval.json").read_text()
    )
    assert "Synthetic" in mock.note and all(c.startswith("mock-") for c in mock.clips_scored)
    for s in mock.systems:
        assert sum(c.hits for c in s.per_clip) == s.overall.hits == sum(c.hits for c in s.per_check)
        assert sum(c.false_positives for c in s.per_clip) == s.overall.false_positives
