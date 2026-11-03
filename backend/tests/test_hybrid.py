"""Hybrid proposals: a video-level model proposes, the agent verifies. Fake model: no network."""

import json
from types import SimpleNamespace

from accesswalk import agent, hybrid, llm
from accesswalk.rules import load_rules
from test_agent import GOOD, FakeChat, _call, _ctx


def _finding(check, ms, title="t"):
    return SimpleNamespace(check_id=check, frame_ms=ms, title=title, evidence_note="seen at the edge")


def _props(ctx):
    rep = SimpleNamespace(
        findings=[_finding("narrow_passage", 3100, "Pole"), _finding("surface_damage", 2400, "Heaved slab")]
    )
    return hybrid.proposals_from_report(rep, ctx.meta)


def _proposer():
    return hybrid.Proposer(provider="baseten", model="muse-spark-open", open_weight=True, source="test")


def _finish(i, **kw):
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [_call(i, "finish", not_applicable=[], summary="ok", **kw)],
    }


def test_proposals_are_time_ordered_and_snap_to_a_frame():
    ctx = _ctx()
    ps = _props(ctx)
    assert [(p.n, p.check_id) for p in ps] == [(1, "surface_damage"), (2, "narrow_passage")]
    assert all(ctx.meta.frame_ms[p.frame_index] <= p.frame_ms + 200 for p in ps)
    text = hybrid.proposals_prompt(ps)
    assert "unverified" in text and "1 | surface_damage | 2.4 s" in text


def test_classic_run_is_unchanged_without_a_proposer(tmp_path):
    chat = FakeChat([_finish(1)])
    res = agent.run_agent(_ctx(), chat_fn=chat, run_log=tmp_path / "r.jsonl", render=False)
    messages, kw = chat.sent[0]
    assert len(messages) == 2 and kw["tools"] is agent.TOOLS  # same cache key as before
    assert res.report.proposals == [] and res.report.run.proposer_model is None


def test_agent_verifies_each_proposal_and_report_keeps_verdicts(tmp_path):
    ctx = _ctx()
    ctx.proposals, ctx.proposer = _props(ctx), _proposer()
    chat = FakeChat(
        [
            {"role": "assistant", "content": "", "tool_calls": [_call(1, "cite_finding", **GOOD)]},
            _finish(2),  # no verdicts yet: refused once
            _finish(
                3,
                proposals=[
                    {"n": 1, "verdict": "cited", "reason": "slab track lifted"},
                    {"n": 2, "verdict": "rejected", "reason": "pole beside the walk"},
                ],
            ),
        ]
    )
    res = agent.run_agent(ctx, chat_fn=chat, run_log=tmp_path / "r.jsonl", render=False)
    first, kw = chat.sent[0]
    assert kw["tools"] is agent.HYBRID_TOOLS and "Candidates" in first[2]["content"]
    refused = [json.loads(m["content"]) for m in chat.sent[2][0] if m["role"] == "tool"][-1]
    assert refused["ok"] is False and "[1, 2]" in refused["reason"]
    r = res.report
    assert [(p.n, p.verdict) for p in r.proposals] == [(1, "cited"), (2, "rejected")]
    assert r.proposals[0].finding_ids == ["f1"] and r.proposals[1].finding_ids == []
    assert r.run.proposer_model == "muse-spark-open" and r.run.proposer_open_weight is True
    assert [f.finding_id for f in r.findings] == ["f1"]  # a proposal is never a finding by itself


def test_missing_verdicts_end_as_unreviewed_after_one_reminder(tmp_path):
    ctx = _ctx()
    ctx.proposals, ctx.proposer = _props(ctx), _proposer()
    res = agent.run_agent(
        ctx, chat_fn=FakeChat([_finish(1), _finish(2)]), run_log=tmp_path / "r.jsonl", render=False
    )
    assert res.report.verdict and {p.verdict for p in res.report.proposals} == {"unreviewed"}


def test_open_proposer_sends_the_video_and_stays_open_weight(tmp_path, monkeypatch):
    ctx = _ctx()
    video = tmp_path / "proposer.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    monkeypatch.setattr(hybrid, "proposer_video", lambda meta, out_root=None: video)
    answer = {
        "findings": [
            {
                "check_id": "narrow_passage",
                "title": "Pole narrows the walk",
                "severity": "medium",
                "confidence": 0.7,
                "frame_ms": 3000,
                "bbox": [10, 10, 50, 90],
                "evidence_note": "a pole at the edge",
            }
        ],
        "summary": "s",
    }
    sent = []

    def chat(messages, **kw):
        sent.append((messages, kw))
        return llm.ChatResult(
            message={"role": "assistant", "content": json.dumps(answer)},
            finish_reason="stop",
            usage={"prompt_tokens": 900},
            provider="baseten",
            model_served="muse-spark-open",
            cache_hit=False,
            cost_usd=0.002,
        )

    props, who, rep, cost = hybrid.propose_open(ctx.meta, load_rules(), chat_fn=chat)
    part = sent[0][0][0]["content"][0]
    assert part["type"] == "video_url" and part["video_url"]["url"].startswith("data:video/mp4;base64,")
    assert sent[0][1]["tag"] == "proposer" and "allow_closed" not in sent[0][1]
    assert [(p.check_id, p.frame_ms) for p in props] == [("narrow_passage", 3000)]
    assert who.open_weight and rep.run.agent_provider == "baseten" and not rep.run.used_closed_fallback
    assert cost == 0.002


def test_unreadable_proposer_answer_gives_no_proposals(tmp_path, monkeypatch):
    ctx = _ctx()
    video = tmp_path / "proposer.mp4"
    video.write_bytes(b"x")
    monkeypatch.setattr(hybrid, "proposer_video", lambda meta, out_root=None: video)

    def chat(messages, **kw):
        return llm.ChatResult(
            message={"role": "assistant", "content": None},
            finish_reason="length",
            usage={},
            provider="baseten",
            model_served="m",
            cache_hit=False,
            cost_usd=0.0,
        )

    props, _, rep, _ = hybrid.propose_open(ctx.meta, load_rules(), chat_fn=chat)
    assert props == [] and rep.findings == []


def test_fractional_boxes_are_scaled_to_pixels():
    assert hybrid.pixel_box([0.25, 0.5, 0.75, 1.0], 720, 1280) == [180, 640, 540, 1280]
    assert hybrid.pixel_box([10, 20, 30.4, 40], 720, 1280) == [10, 20, 30, 40]
    assert hybrid.pixel_box("x", 720, 1280) == "x"
