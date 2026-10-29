"""Agent loop, LLM client and mask measure tests. Fake model and hosts: no network."""
import json

import numpy as np
import pytest
from accesswalk import agent, llm, masks
from accesswalk.inventory import Inventory, build_tracks
from accesswalk.rules import load_rules
from accesswalk.sam_parse import SamRecord
from test_inventory import _meta


def _rec(f, oid, x1, y1, x2, y2) -> SamRecord:
    return SamRecord(frame_index=f, object_id=oid, x1=x1, y1=y1, x2=x2, y2=y2,
                     frame_w=720, frame_h=1280, box_conf=0.8)


def _ctx() -> agent.AgentContext:
    m = _meta()
    records = {
        "raised sidewalk slab": [_rec(f, 0, 100, 600, 500, 900) for f in range(10, 15)],
        "trash bin": [_rec(f, 0, 300, 400, 400, 700) for f in range(0, 5)],
        "sidewalk": [_rec(f, 0, 200, 300, 600, 1279) for f in range(0, 20)],
    }
    tracks = [t for p, rs in records.items() for t in build_tracks(p, rs, m)]
    return agent.AgentContext(meta=m, inv=Inventory(video_sha256="abc", tracks=tracks, duplicates={}),
                              records=records, rules=load_rules())


def _call(i, name, **args):
    return {"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


class FakeChat:
    """Plays back scripted assistant turns and records what it was sent."""

    def __init__(self, turns, provider="baseten"):
        self.turns, self.provider, self.sent = list(turns), provider, []

    def __call__(self, messages, **kw):
        self.sent.append((list(messages), kw))
        idle = {"role": "assistant", "content": "",
                "tool_calls": [_call(99, "get_track", track_id="trash-bin-0")]}
        msg = self.turns.pop(0) if self.turns else idle
        return llm.ChatResult(message=msg, finish_reason="tool_calls", usage={"prompt_tokens": 100},
                              provider=self.provider, model_served="muse-spark-open", cache_hit=False,
                              cost_usd=0.001)


GOOD = dict(check_id="surface_damage", track_id="raised-sidewalk-slab-0", frame_index=12, severity="high",
            confidence=0.8, title="Heaved slab", evidence_note="Slab edge lifted well above the next slab.")


def test_parallel_calls_cite_and_finish(tmp_path):
    ctx = _ctx()
    chat = FakeChat([
        {"role": "assistant", "content": None, "tool_calls": [
            _call(1, "get_track", track_id="raised-sidewalk-slab-0"),
            _call(2, "cite_finding", **GOOD),
            _call(3, "cite_finding", **{**GOOD, "track_id": "trash-bin-0", "frame_index": 2}),
        ]},
        {"role": "assistant", "content": "", "tool_calls": [
            _call(4, "finish", not_applicable=["round_doorknob"], summary="One heaved slab.")]},
    ])
    res = agent.run_agent(ctx, chat_fn=chat, run_log=tmp_path / "runs.jsonl", render=False)
    assert res.turns == 2 and not res.hit_turn_cap
    assert [f.finding_id for f in res.report.findings] == ["f1"]
    assert "must cite a track of" in res.rejections[0].reason  # a bin is not surface damage
    tool_msgs = [m for m in chat.sent[1][0] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == ["c1", "c2", "c3"]  # all 3 parallel calls answered
    assert chat.sent[0][1]["params"]["parallel_tool_calls"] is True
    r = res.report
    assert r.verdict.rating == "likely_blocked" and not r.run.used_closed_fallback
    assert {c.check_id: c.status for c in r.checks}["round_doorknob"] == "not_applicable"
    log = json.loads((tmp_path / "runs.jsonl").read_text().splitlines()[0])
    assert log["hit_turn_cap"] is False and log["n_findings"] == 1


def test_turn_cap_is_logged(tmp_path):
    res = agent.run_agent(_ctx(), chat_fn=FakeChat([]), run_log=tmp_path / "runs.jsonl", render=False)
    assert res.turns == agent.MAX_TURNS and res.hit_turn_cap
    log = json.loads((tmp_path / "runs.jsonl").read_text())
    assert log["hit_turn_cap"] is True and "cap" in log["warning"]


def test_closed_model_marked_in_provenance(tmp_path):
    chat = FakeChat([{"role": "assistant", "content": "", "tool_calls": [
        _call(1, "finish", not_applicable=[], summary="ok")]}], provider="meta")
    res = agent.run_agent(_ctx(), chat_fn=chat, run_log=tmp_path / "r.jsonl", render=False, allow_closed=True)
    assert res.report.run.used_closed_fallback is True and chat.sent[0][1]["allow_closed"] is True


def test_recheck_tracks_citable_only_for_their_check(tmp_path):
    ctx = _ctx()
    ctx.recheck_fn = lambda c, phrase, s, e: [_rec(f, 0, 100, 800, 300, 1000) for f in range(5, 8)]
    out = agent.dispatch(ctx, "recheck_with_sam", json.dumps(
        {"phrase": "Curb Cut", "start_ms": 1000, "end_ms": 1600, "for_check": "missing_curb_ramp"}))
    tid = out["new_tracks"][0]["track_id"]
    assert tid == "recheck-curb-cut-0"
    cite = dict(GOOD, track_id=tid, frame_index=6, check_id="missing_curb_ramp")
    assert agent.dispatch(ctx, "cite_finding", json.dumps(cite))["ok"] is True
    other = dict(cite, check_id="sidewalk_obstruction")
    assert agent.dispatch(ctx, "cite_finding", json.dumps(other))["ok"] is False
    for _ in range(agent.MAX_RECHECKS):
        last = agent.dispatch(ctx, "recheck_with_sam", json.dumps(
            {"phrase": "curb cut", "start_ms": 0, "end_ms": 900, "for_check": "missing_curb_ramp"}))
    assert "limit" in last["error"]


def test_get_track_reports_missing_decoder_instead_of_guessing(monkeypatch):
    ctx = _ctx()
    ctx.records["trash bin"] = [r.model_copy(update={"mask": masks.MaskToken(
        height=301, width=101, encoding="one_bit", data="x")}) for r in ctx.records["trash bin"]]

    def boom(_m, _cache=None):
        raise RuntimeError("mask decoding needs Meta's parser")
    monkeypatch.setattr(masks, "decode_raster", boom)
    out = agent.tool_get_track(ctx, "trash-bin-0")
    assert "on_sidewalk_unavailable" in out and "on_sidewalk" not in out["frames"][0]


def test_prompts_list_rules_and_tracks():
    ctx = _ctx()
    sp, ip = agent.system_prompt(ctx.rules), agent.inventory_prompt(ctx)
    assert "never 'violation'" in sp and "missing_curb_ramp" in sp
    assert "trash-bin-0 | trash bin" in ip


# ----------------------------------------------------------------- masks --- #
def test_on_sidewalk_fraction_uses_mask_bottom_edge():
    obj = _rec(0, 0, 10, 10, 19, 29)          # 10 wide x 20 tall object
    raster = np.ones((20, 10), dtype=np.uint8)
    walk = _rec(0, 0, 0, 25, 14, 40)           # sidewalk covers x 0-14 below y 25
    walk_r = np.ones((16, 15), dtype=np.uint8)
    # contacts at y=29 for x=10..19: x 10-14 inside the sidewalk, 15-19 outside
    assert masks.on_sidewalk_fraction((obj, raster), [(walk, walk_r)]) == 0.5
    assert masks.on_sidewalk_fraction((obj, raster), []) is None
    raster[:, 5:] = 0                           # only the left half is object
    assert masks.on_sidewalk_fraction((obj, raster), [(walk, walk_r)]) == 1.0


# ------------------------------------------------------------------- llm --- #
def _providers():
    return {n: llm.Provider(n, "http://x", f"{n}-model", "K") for n in ("baseten", "fireworks", "meta")}


def _ok(p, messages, tools, params):
    return {"message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop",
            "usage": {"prompt_tokens": 1000, "completion_tokens": 100}, "model_served": p.model}


def test_chat_cache_key_covers_provider_and_tools(tmp_path):
    kw = dict(video_sha256="abc", providers=_providers(), out_root=tmp_path, usage_log=tmp_path / "u.jsonl")
    calls = []

    def counting(p, m, t, prm):
        calls.append(p.name)
        return _ok(p, m, t, prm)
    msgs = [{"role": "user", "content": "x"}]
    a = llm.chat(msgs, call_fn=counting, **kw)
    b = llm.chat(msgs, call_fn=counting, **kw)
    c = llm.chat(msgs, call_fn=counting, tools=[{"type": "function", "function": {"name": "f"}}], **kw)
    assert (a.cache_hit, b.cache_hit, c.cache_hit) == (False, True, False) and len(calls) == 2
    p = _providers()
    assert llm.cache_key(p["baseten"], msgs, None, {}) != llm.cache_key(p["fireworks"], msgs, None, {})
    assert a.cost_usd == pytest.approx((1000 * 1.25 + 100 * 4.25) / 1e6)


def test_failover_stays_open_weight_unless_flagged(tmp_path):
    kw = dict(video_sha256="abc", providers=_providers(), out_root=tmp_path, usage_log=tmp_path / "u.jsonl")

    class Down(Exception):
        status_code = 503

    def only(name):
        def fn(p, m, t, prm):
            if p.name != name:
                raise Down(f"{p.name} down")
            return _ok(p, m, t, prm)
        return fn
    msgs = [{"role": "user", "content": "y"}]
    r = llm.chat(msgs, call_fn=only("fireworks"), **kw)
    assert r.provider == "fireworks" and "baseten" in r.errors[0]
    with pytest.raises(llm.ProviderError, match="all providers failed"):
        llm.chat([{"role": "user", "content": "z"}], call_fn=only("meta"), **kw)
    r = llm.chat([{"role": "user", "content": "z"}], call_fn=only("meta"), allow_closed=True, **kw)
    assert r.used_closed_model


@pytest.mark.parametrize("status, fails_over", [(500, True), (503, True), (429, True),
                                                 (400, False), (401, False), (404, False)])
def test_failover_only_on_5xx_429_timeout(tmp_path, status, fails_over):
    kw = dict(video_sha256="abc", providers=_providers(), out_root=tmp_path, usage_log=tmp_path / "u.jsonl")

    class HostError(Exception):
        status_code = status

    def fn(p, m, t, prm):
        if p.name == "baseten":
            raise HostError("Too many images" if status == 400 else "err")
        return _ok(p, m, t, prm)
    msgs = [{"role": "user", "content": f"s{status}"}]
    if fails_over:
        assert llm.chat(msgs, call_fn=fn, **kw).provider == "fireworks"
    else:
        with pytest.raises(llm.ProviderError, match="baseten"):
            llm.chat(msgs, call_fn=fn, **kw)


def test_timeout_fails_over(tmp_path):
    kw = dict(video_sha256="abc", providers=_providers(), out_root=tmp_path, usage_log=tmp_path / "u.jsonl")

    def fn(p, m, t, prm):
        if p.name == "baseten":
            raise TimeoutError("read timed out")
        return _ok(p, m, t, prm)
    assert llm.chat([{"role": "user", "content": "t"}], call_fn=fn, **kw).provider == "fireworks"


def test_at_most_8_images_per_request(tmp_path):
    ctx = _ctx()
    ctx.frame_loader = lambda c, i: np.zeros((1280, 720, 3), dtype=np.uint8)
    views = [{"role": "assistant", "content": "", "tool_calls": [
        _call(10 * t + k, "view_frame", frame_index=t * 3 + k) for k in range(3)]} for t in range(4)]
    chat = FakeChat(views + [{"role": "assistant", "content": "",
                              "tool_calls": [_call(99, "finish", not_applicable=[], summary="s")]}])
    agent.run_agent(ctx, chat_fn=chat, run_log=tmp_path / "r.jsonl", render=False)

    def images(msgs):
        return [p for m in msgs if isinstance(m["content"], list) for p in m["content"]
                if p.get("type") == "image_url"]
    assert [len(images(sent)) for sent, _ in chat.sent] == [0, 3, 6, 8, 8]  # 12 views, never > 8
    last = chat.sent[-1][0]
    captions = [p["text"] for m in last if isinstance(m["content"], list) for p in m["content"]
                if p.get("type") == "text" and p["text"].startswith("frame ")]
    assert len(captions) == 12  # every view keeps its caption
    many = [_call(k, "view_frame", frame_index=k) for k in range(9)]
    ctx2 = _ctx()
    ctx2.frame_loader = ctx.frame_loader
    outs = [agent.dispatch(ctx2, c["function"]["name"], c["function"]["arguments"]) for c in many]
    assert "per turn" in outs[-1]["error"]

def test_view_frame_sends_images_after_tool_results(tmp_path):
    ctx = _ctx()
    ctx.frame_loader = lambda c, i: np.zeros((1280, 720, 3), dtype=np.uint8)
    chat = FakeChat([
        {"role": "assistant", "content": "", "tool_calls": [
            _call(1, "view_frame", frame_index=12, track_ids=["raised-sidewalk-slab-0", "trash-bin-0"]),
            _call(2, "view_frame", frame_index=999)]},
        {"role": "assistant", "content": "",
         "tool_calls": [_call(3, "finish", not_applicable=[], summary="s")]},
    ])
    agent.run_agent(ctx, chat_fn=chat, run_log=tmp_path / "r.jsonl", render=False)
    sent = chat.sent[1][0]
    roles = [m["role"] for m in sent[-3:]]
    assert roles == ["tool", "tool", "user"]  # images only after every tool result of the turn
    t1, t2 = json.loads(sent[-3]["content"]), json.loads(sent[-2]["content"])
    assert t1["ok"] and t1["no_box_on_this_frame"] == ["trash-bin-0"] and "error" in t2
    imgs = [p for p in sent[-1]["content"] if p["type"] == "image_url"]
    assert len(imgs) == 1 and imgs[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert ctx.views == 1


def test_view_frame_cap():
    ctx = _ctx()
    ctx.frame_loader = lambda c, i: np.zeros((1280, 720, 3), dtype=np.uint8)
    for _ in range(agent.MAX_VIEWS):
        assert agent.tool_view_frame(ctx, 1)["ok"]
        ctx.pending_images = []  # the loop clears them after each turn
    assert "limit" in agent.tool_view_frame(ctx, 1)["error"]


def test_budget_cap_stops_before_overspending(tmp_path):
    res = agent.run_agent(_ctx(), chat_fn=FakeChat([]), run_log=tmp_path / "r.jsonl", render=False,
                          max_cost_usd=0.0035)  # each fake turn costs 0.001
    assert res.stopped_for_budget and res.turns == 3 and res.cost_usd <= 0.0035
    assert res.tool_counts == {"get_track": 3}
