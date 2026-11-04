"""Single-call grounded review: Muse Spark 1.3 watches the clip once, with the SAM track
inventory and still frames of the tracks, and answers with findings that cite a track and
a frame. Every citation then goes through the agent's validator (validator.py): a finding
whose track, phrase or frame does not check out is dropped, exactly as in the agent loop.

What the model gets, in one request (Responses API, like baseline.py):
  * the published ``proxy.mp4`` (faces and plates blurred, metadata stripped; data/raw is
    never sent) as an ``input_video`` file;
  * the inventory text the agent starts from (track id | phrase | seconds | keyframe | where);
  * stills: each a blurred frame with one track's box drawn and labelled. ``per_track=1``
    sends every track's keyframe; ``per_track>1`` adds more frames spread over each track's
    time span, round robin, until ``MAX_STILLS``.

No tools and no retries: a rejected citation is simply gone. Cached by (model, params,
prompt, still bytes) under data/cache/<sha>/grounded/, logged to usage.jsonl.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

import cv2
from openai import OpenAI

from . import baseline, usage
from .agent import AgentContext, build_report, inventory_prompt, rule_lines
from .ingest import DEFAULT_OUT_ROOT
from .inventory import render_frames
from .schemas import Report, Track
from .validator import Rejection, finalize, validate_citation

MODEL = baseline.MODEL  # muse-spark-1.3
MAX_OUTPUT_TOKENS = 16000  # reasoning model: room to think over ~70 stills
MAX_STILLS = 100  # Meta accepted 100 images in one request (probe, Nov 3)
STILL_WIDTH = 512  # ~570 input tokens per still on Muse Spark 1.3
TITLE_MAX, NOTE_MAX = 90, 600  # the validator's length limits


@dataclass(frozen=True)
class GroundedConfig:
    name: str
    per_track: int  # stills per track (the keyframe first)


CONFIGS = {"one": GroundedConfig("one", 1), "many": GroundedConfig("many", 4)}


def _spread(t: Track, n: int) -> list[int]:
    """Up to ``n - 1`` frames of ``t`` other than its keyframe, spread over its span."""
    frames = [b.frame_index for b in sorted(t.boxes, key=lambda b: b.frame_index)]
    picks: list[int] = []
    for q in (0.0, 1.0, 0.5, 0.25, 0.75)[: max(0, n - 1) + 2]:
        f = frames[round(q * (len(frames) - 1))]
        if f != t.keyframe_index and f not in picks:
            picks.append(f)
    return picks[: max(0, n - 1)]


def stills_plan(tracks: list[Track], per_track: int, limit: int = MAX_STILLS) -> list[tuple[Track, int]]:
    """(track, frame_index) pairs: every track's keyframe in time order, then the extra
    frames round robin (each track's second still, then each one's third, ...)."""
    tracks = sorted(tracks, key=lambda t: (t.first_ms, t.track_id))
    plan = [(t, t.keyframe_index) for t in tracks][:limit]
    extras = {t.track_id: _spread(t, per_track) for t in tracks}
    for k in range(per_track - 1):
        for t in tracks:
            if len(plan) >= limit:
                return plan
            if k < len(extras[t.track_id]):
                plan.append((t, extras[t.track_id][k]))
    return plan


def _still(path: Path, t: Track, frame_index: int) -> bytes:
    img = cv2.imread(str(path))
    b = next(b for b in t.boxes if b.frame_index == frame_index)
    cv2.rectangle(img, (b.x1, b.y1), (b.x2, b.y2), (0, 0, 255), 4)
    cv2.putText(img, t.track_id, (b.x1 + 4, max(28, b.y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                (0, 0, 255), 2)
    h, w = img.shape[:2]
    img = cv2.resize(img, (STILL_WIDTH, round(h * STILL_WIDTH / w)))
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()


def build_prompt(ctx: AgentContext, captions: list[str]) -> str:
    return "\n".join([
        "You review a first-person walking video of a route for wheelchair users. SAM 3.1 has already "
        "tracked objects in it. You get the video (faces and plates blurred), the list of tracks, and "
        "still frames, each showing one track's box labelled with its track_id. Watch the whole video, "
        "decide which tracked objects are likely barriers, and cite each one.",
        "Rules: every finding cites a track_id from the list and a frame_index where that track has a "
        "box: the frame of one of its stills is always valid. A barrier with no fitting track cannot be "
        "cited; leave it out. Cite only tracks of the phrases a check accepts. Say 'likely barrier' and "
        "'verify on site', never 'violation' or 'non-compliant'. Heights, slopes and widths judged from "
        "video are estimates. Check the pitfalls before citing. If nothing qualifies for a check, cite "
        "nothing for it. In titles and evidence notes, name the object and where it is in the scene; "
        "never mention boxes, box colours or labels. Titles at most 80 characters; evidence notes "
        "20-500 characters.",
        "Checks:",
        *rule_lines(ctx.rules),
        "",
        inventory_prompt(ctx),
        "",
        f"Stills ({len(captions)}), in the order attached: " + "; ".join(captions),
        "",
        "Reply with JSON only, no markdown fence, exactly this shape:",
        '{"findings": [{"check_id": "<check>", "track_id": "<from the list>", "frame_index": <int>, '
        '"severity": "low|medium|high", "confidence": <0 to 1>, "title": "<one line>", '
        '"evidence_note": "<what you saw and why it is likely a barrier; what to check on site>", '
        '"related_track_ids": []}], "not_applicable": ["<checks that cannot occur on this clip>"], '
        '"summary": "<one or two sentences about the route>"}',
    ])


def _parse(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        out = json.loads(re.sub(r"[\x00-\x1f]", " ", text[start : end + 1]))
    except json.JSONDecodeError:
        return {}
    return out if isinstance(out, dict) else {}


def _call(client: OpenAI, file_id: str, prompt: str, stills: list[tuple[str, bytes]]) -> baseline.RawResponse:
    content: list[dict] = [{"type": "input_text", "text": prompt},
                           {"type": "input_video", "file_id": file_id}]
    for caption, jpg in stills:
        content.append({"type": "input_text", "text": caption})
        content.append({"type": "input_image",
                        "image_url": "data:image/jpeg;base64," + base64.b64encode(jpg).decode()})
    req = dict(model=MODEL, max_output_tokens=MAX_OUTPUT_TOKENS,
               input=[{"type": "message", "role": "user", "content": content}])
    with client.responses.stream(**req) as stream:
        for _ in stream:
            pass
        final = stream.get_final_response()
    raw_usage = final.usage.model_dump() if getattr(final, "usage", None) is not None else {}
    text = getattr(final, "output_text", "") or ""
    return baseline.RawResponse(text, raw_usage, getattr(final, "model", None))


@dataclass
class GroundedResult:
    report: Report
    rejections: list[Rejection]
    n_stills: int
    n_proposed: int
    cost_usd: float
    cache_hit: bool


def run_grounded(ctx: AgentContext, config: GroundedConfig, out_root: Path = DEFAULT_OUT_ROOT,
                 client: OpenAI | None = None, call_fn=_call, render: bool = True) -> GroundedResult:
    m = ctx.meta
    clip_dir = Path(out_root) / m.video_sha256
    plan = stills_plan(ctx.inv.kept(), config.per_track)
    paths = render_frames(m, {f for _, f in plan}, ctx.plate_tracks, out_root)
    captions = [f"still {i}: {t.track_id} on frame {f} ({m.frame_ms[f] / 1000:.1f} s)"
                for i, (t, f) in enumerate(plan, start=1)]
    stills = [(c, _still(paths[f], t, f)) for c, (t, f) in zip(captions, plan, strict=True)]
    prompt = build_prompt(ctx, captions)
    blob = json.dumps({"model": MODEL, "max_output_tokens": MAX_OUTPUT_TOKENS, "prompt": prompt,
                       "stills": [hashlib.sha256(j).hexdigest() for _, j in stills]}, sort_keys=True)
    key = hashlib.sha256(blob.encode()).hexdigest()[:20]
    cpath = clip_dir / "grounded" / f"{key}.json"
    hit = cpath.exists()
    if hit:
        raw = baseline.RawResponse(**json.loads(cpath.read_text(encoding="utf-8")))
        cost = 0.0
    else:
        client = client or OpenAI(api_key=os.environ["MODEL_API_KEY"],
                                  base_url=os.getenv("META_BASE_URL", "https://api.meta.ai/v1"))
        file_id = baseline.upload_proxy(client, clip_dir / baseline.ALLOWED_VIDEO)
        raw = call_fn(client, file_id, prompt, stills)
        cost = baseline.cost_usd(raw.usage)
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_text(json.dumps(raw.__dict__), encoding="utf-8")
    usage.log_call(usage.UsageRecord(
        provider="meta", model_requested=MODEL, model_served=raw.model_served, usage=raw.usage,
        cache_hit=hit, cost_usd=cost, video_sha256=m.video_sha256,
        extra={"tag": f"grounded-{config.name}", "cache_key": key, "stills": len(stills)},
    ))
    out = _parse(raw.text)
    proposed = [f for f in out.get("findings") or [] if isinstance(f, dict)]
    for f in proposed:
        for field_, cap in (("title", TITLE_MAX), ("evidence_note", NOTE_MAX)):
            if isinstance(f.get(field_), str):
                f[field_] = f[field_][:cap]  # length is formatting, not grounding
        res = validate_citation(f, ctx.inv, m, ctx.rules)
        (ctx.rejections if isinstance(res, Rejection) else ctx.findings).append(res)
    findings = finalize(ctx.findings)
    if render and findings:
        render_frames(m, {f.frame_index for f in findings}, ctx.plate_tracks, out_root)
    na = out.get("not_applicable") or []
    ctx.not_applicable = [c for c in na if isinstance(c, str) and c in ctx.rules.checks]
    ctx.summary = str(out.get("summary") or "")
    ctx.finished = bool(out)
    served = [raw.model_served or MODEL]
    report = build_report(ctx, findings, ["meta"], served, baseline.cost_usd(raw.usage), 1)
    report.report_id = f"grounded-{config.name}-{report.report_id}"
    return GroundedResult(report, ctx.rejections, len(stills), len(proposed), cost, hit)
