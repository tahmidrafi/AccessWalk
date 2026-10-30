"""Baseline parsing, gates, report shape and cache. Fake model call, no network, invented output."""

import json

import pytest
from accesswalk import baseline
from accesswalk.ingest import IngestMeta, SourceMeta, StreamMeta
from accesswalk.rules import load_rules
from accesswalk.schemas import Report


def _meta() -> IngestMeta:
    return IngestMeta(
        video_sha256="abc",
        ingest_version=1,
        created_at="now",
        source=SourceMeta(
            filename="clip.mp4",
            coded_width=1920,
            coded_height=1080,
            rotation=-90,
            display_width=1080,
            display_height=1920,
            fps=30.0,
            duration_s=2.0,
            has_audio=False,
        ),
        sam=StreamMeta(width=720, height=1280, fps=5.0, n_frames=5),
        proxy=StreamMeta(width=720, height=1280, fps=30.0, n_frames=60),
        frame_ms=[0, 200, 400, 600, 800],
        faces_frames=0,
        faces_boxes=0,
    )


def _raw(**kw) -> dict:
    return {
        "check_id": "surface_damage",
        "title": "Broken slab",
        "severity": "high",
        "confidence": 0.7,
        "frame_ms": 450,
        "bbox": [10, 20, 100, 200],
        "evidence_note": "A slab is broken.",
        **kw,
    }


def _resp(**kw) -> baseline.RawResponse:
    return baseline.RawResponse(
        json.dumps({"findings": [_raw(**kw)], "summary": "Route summary."}),
        {"input_tokens": 1000, "output_tokens": 100},
        "muse-spark-1.3",
    )


def _fake_call(resp):
    calls = []

    def call(client, file_id, prompt):
        calls.append((file_id, prompt))
        return resp

    return call, calls


def test_parse_tolerates_a_fence_and_refuses_no_json():
    assert baseline.parse_output('```json\n{"findings": [], "summary": "s"}\n```').summary == "s"
    with pytest.raises(ValueError, match="no JSON"):
        baseline.parse_output("I cannot watch this video.")


def test_report_uses_the_agent_schema_and_says_it_is_closed_and_ungrounded():
    report, dropped = baseline.build_report(
        _meta(), load_rules(), baseline.parse_output(_resp().text), _resp(), 0.01
    )
    Report.model_validate_json(report.model_dump_json())
    f = report.findings[0]
    assert dropped == 0 and f.frame_ms == 450 and f.frame_index == 2  # eval time stays the model's own
    assert report.tracks[0].phrase == baseline.BASELINE_PHRASE and report.run.sam_model == "none"
    assert report.run.agent_provider == "meta" and report.run.used_closed_fallback
    assert report.verdict.rating == "likely_blocked" and f.verify_manually


@pytest.mark.parametrize(
    "bad",
    [
        {"check_id": "nonsense"},
        {"severity": "catastrophic"},
        {"confidence": 7},
        {"bbox": [1, 2]},
        {"evidence_note": "A clear ADA violation here."},
    ],
)
def test_gates_drop_a_bad_finding(bad):
    resp = _resp(**bad)
    report, dropped = baseline.build_report(
        _meta(), load_rules(), baseline.parse_output(resp.text), resp, 0.0
    )
    assert dropped == 1 and report.findings == []


def test_box_is_clamped_to_the_frame():
    resp = _resp(bbox=[-5, 50, 9000, 10])
    report, _ = baseline.build_report(_meta(), load_rules(), baseline.parse_output(resp.text), resp, 0.0)
    b = report.findings[0].bbox
    assert (b.x1, b.y1, b.x2, b.y2) == (0, 10, 720, 50)


def test_only_the_proxy_can_be_uploaded(tmp_path):
    with pytest.raises(ValueError, match="refusing"):
        baseline.upload_proxy(None, tmp_path / "PXL_raw.mp4")


def test_second_run_is_free_and_logged(tmp_path):
    call, calls = _fake_call(_resp())
    log = tmp_path / "usage.jsonl"
    upload = lambda *_a: "file-1"  # noqa: E731
    kw = dict(client=object(), out_root=tmp_path, usage_log=log, upload_fn=upload, call_fn=call)
    baseline.run_clip(_meta(), load_rules(), **kw)
    baseline.run_clip(_meta(), load_rules(), **kw)
    assert len(calls) == 1
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    assert [r["cache_hit"] for r in rows] == [False, True]
    assert rows[0]["cost_usd"] > 0 and rows[1]["cost_usd"] == 0 and rows[0]["extra"]["tag"] == "baseline"
