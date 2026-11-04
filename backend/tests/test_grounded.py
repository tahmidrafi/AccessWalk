"""Single-call grounded review: stills plan, validator gate, cache. Fake model, no network."""
import json

import cv2
import numpy as np
from accesswalk import baseline, grounded
from test_agent import GOOD, _ctx


def test_stills_plan_keyframes_first_then_round_robin_up_to_the_limit():
    tracks = _ctx().inv.kept()
    one = grounded.stills_plan(tracks, 1)
    assert [f for t, f in one] == [t.keyframe_index for t in sorted(tracks, key=lambda t: t.first_ms)]
    many = grounded.stills_plan(tracks, 3)
    assert many[: len(one)] == one and len(many) > len(one)
    assert all(any(b.frame_index == f for b in t.boxes) for t, f in many)  # every still has its box
    assert len({(t.track_id, f) for t, f in many}) == len(many)
    assert len(grounded.stills_plan(tracks, 3, limit=4)) == 4


def _fake_frames(tmp_path, monkeypatch):
    img = np.zeros((1280, 720, 3), np.uint8)
    path = tmp_path / "f.jpg"
    cv2.imwrite(str(path), img)
    def render(meta, idx, plates, out_root=None):
        return {i: path for i in idx}

    monkeypatch.setattr(grounded, "render_frames", render)


def test_only_valid_citations_survive_and_the_answer_is_cached(tmp_path, monkeypatch):
    _fake_frames(tmp_path, monkeypatch)
    (tmp_path / "abc").mkdir()
    (tmp_path / "abc" / "proxy.mp4").write_bytes(b"x")
    answer = {"findings": [
        GOOD,  # slab track, slab check, frame with a box: kept
        {**GOOD, "track_id": "trash-bin-0", "frame_index": 2},  # wrong phrase for the check
        {**GOOD, "track_id": "no-such-track"},
        {**GOOD, "title": "T" * 200},  # too long a title is trimmed, not dropped
    ], "not_applicable": ["round_doorknob", "nonsense"], "summary": "One heaved slab."}
    calls = []

    def call(client, file_id, prompt, stills):
        calls.append((file_id, prompt, len(stills)))
        return baseline.RawResponse(json.dumps(answer), {"input_tokens": 1000, "output_tokens": 100}, "m")

    upload = lambda client, path: "file-1"  # noqa: E731
    monkeypatch.setattr(baseline, "upload_proxy", upload)
    monkeypatch.setattr(grounded.usage, "log_call", lambda rec, path=None: None)
    res = grounded.run_grounded(_ctx(), grounded.CONFIGS["one"], out_root=tmp_path, client=object(),
                                call_fn=call, render=False)
    assert len(calls) == 1 and "raised-sidewalk-slab-0" in calls[0][1] and calls[0][2] == res.n_stills
    assert [f.track_id for f in res.report.findings] == ["raised-sidewalk-slab-0"]  # merged per object
    assert len(res.rejections) == 2 and res.n_proposed == 4
    assert res.report.run.agent_provider == "meta" and res.report.run.used_closed_fallback
    assert [c.status for c in res.report.checks if c.check_id == "round_doorknob"] == ["not_applicable"]
    again = grounded.run_grounded(_ctx(), grounded.CONFIGS["one"], out_root=tmp_path, client=object(),
                                  call_fn=call, render=False)
    assert len(calls) == 1 and again.cache_hit and again.cost_usd == 0.0
