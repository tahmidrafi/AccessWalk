"""Report contract tests: grounding rule, committed JSON Schema/mock in sync. No network."""
import json
from pathlib import Path

import pytest
from accesswalk.schemas import (
    BBox,
    CheckSummary,
    Finding,
    Report,
    RouteVerdict,
    RunInfo,
    Track,
    TrackBox,
    VideoInfo,
)
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_JSON = REPO_ROOT / "frontend" / "src" / "schema" / "report.schema.json"
MOCK_JSON = REPO_ROOT / "frontend" / "src" / "mock" / "report.json"


def _track() -> Track:
    return Track(
        track_id="trash-bin-0", phrase="trash bin", object_id=0, first_ms=800, last_ms=1000,
        n_frames=2, keyframe_index=4, keyframe_ms=800,
        boxes=[
            TrackBox(frame_index=4, frame_ms=800, x1=1, y1=2, x2=30, y2=40, conf=0.9),
            TrackBox(frame_index=5, frame_ms=1000, x1=1, y1=2, x2=30, y2=40, conf=0.8),
        ],
    )


def _finding(**kw) -> Finding:
    base = dict(
        finding_id="f1", check_id="sidewalk_obstruction", title="Bin on sidewalk", severity="medium",
        confidence=0.7, track_id="trash-bin-0", frame_index=4, frame_ms=800,
        bbox=BBox(x1=1, y1=2, x2=30, y2=40), evidence_note="bin", verify_manually=False,
    )
    return Finding(**{**base, **kw})


def _report(findings, verdict_ids=()) -> Report:
    return Report(
        report_id="r1", title="t",
        video=VideoInfo(video_sha256="x", duration_ms=1000, width=720, height=1280,
                        sam_fps=5.0, frame_ms=[0, 200, 400, 600, 800, 1000]),
        verdict=RouteVerdict(rating="caution", summary="s", key_finding_ids=list(verdict_ids)),
        findings=findings, tracks=[_track()],
        checks=[CheckSummary(check_id="sidewalk_obstruction", status="ran", n_findings=len(findings))],
        run=RunInfo(agent_provider="mock", agent_model="mock", sam_model="sam-3.1", created_at="now"),
    )


def test_grounded_report_validates():
    r = _report([_finding()], verdict_ids=["f1"])
    assert r.findings[0].track_id == "trash-bin-0"


@pytest.mark.parametrize(
    "kw, msg",
    [
        ({"track_id": "nope-0"}, "unknown track"),
        ({"frame_index": 9}, "has no box"),
        ({"related_track_ids": ["nope-0"]}, "relates unknown track"),
    ],
)
def test_ungrounded_finding_rejected(kw, msg):
    with pytest.raises(ValidationError, match=msg):
        _report([_finding(**kw)])


def test_verdict_must_cite_known_finding():
    with pytest.raises(ValidationError, match="verdict cites unknown finding"):
        _report([_finding()], verdict_ids=["f9"])


def test_bad_check_id_and_confidence_rejected():
    with pytest.raises(ValidationError):
        _finding(check_id="ada_violation")
    with pytest.raises(ValidationError):
        _finding(confidence=1.5)


def test_committed_json_schema_matches_models():
    assert json.loads(SCHEMA_JSON.read_text()) == Report.model_json_schema(), (
        "report.schema.json is stale: run scripts/export_schema.py"
    )


def test_committed_mock_validates():
    Report.model_validate_json(MOCK_JSON.read_text())


def test_api_contract_exported_and_mocks_valid():
    from accesswalk import api_models as api
    api_schema = REPO_ROOT / "frontend" / "src" / "schema" / "api.schema.json"
    assert json.loads(api_schema.read_text()) == api.json_schema(), (
        "api.schema.json is stale: run scripts/export_schema.py"
    )
    mocks = REPO_ROOT / "frontend" / "src" / "mock" / "api"
    for name, model in [("health", api.Health), ("job_queued", api.JobStatus),
                        ("job_running", api.JobStatus),
                        ("job_done", api.JobStatus), ("job_failed", api.JobStatus),
                        ("reports", api.ReportList), ("error_not_found", api.ErrorResponse)]:
        model.model_validate_json((mocks / f"{name}.json").read_text())
