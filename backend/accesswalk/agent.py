"""Verification agent (d5-agentloop): Muse Spark Open turns SAM tracks into cited findings.

One run per clip. The model starts from the rules and a text inventory of the
clip's tracks, then works with tools:

  get_track(track_id)                         boxes over time + mask-based on-sidewalk share
  view_frame(frame_index, track_ids)          (added after the image smoke test)
  recheck_with_sam(phrase, start_ms, end_ms, for_check)   new SAM tracks on a window
  cite_finding(...)                           validator.py: a Finding, or a fixable reason
  finish(not_applicable, summary)             ends the run

Several tool calls per turn are allowed and executed in order. Caps: MAX_TURNS
model turns (hitting it is logged and the run ends with what was cited),
MAX_RECHECKS SAM rechecks. Every model call goes through llm.chat (cache + usage
log, open-weight hosts only unless allow_closed).
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from . import cache, llm, masks, usage
from .ingest import DEFAULT_OUT_ROOT, IngestMeta, ingest
from .inventory import Inventory, build_tracks, phrase_slug, render_frames, stitch_ids
from .phrases import PLATE_PHRASE, SAM_PHRASES
from .rules import Rules, load_rules
from .sam_parse import SamRecord, parse_output
from .schemas import CheckSummary, Finding, Report, RouteVerdict, RunInfo, Track, VideoInfo
from .validator import Rejection, finalize, validate_citation

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_LOG = REPO_ROOT / "data" / "out" / "agent_runs.jsonl"
MAX_TURNS = 20
MAX_RECHECKS = 2
SAMPLE_BOXES = 8
PARAMS = {"temperature": 0, "max_tokens": 8000, "parallel_tool_calls": True}


# --------------------------------------------------------------------------- #
# tool schemas (part of the cache key: changing them invalidates cached turns)
# --------------------------------------------------------------------------- #
def _fn(name: str, desc: str, props: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props, "required": required},
    }}


CHECK_ENUM = sorted(load_rules().checks)
TOOLS = [
    _fn("get_track", "Boxes of one tracked object over time, sampled, plus on_sidewalk: the share of "
        "the object's ground-contact points (bottom of its mask) inside the sidewalk mask on that frame "
        "(null = no sidewalk mask there).",
        {"track_id": {"type": "string"}}, ["track_id"]),
    _fn("recheck_with_sam", "Run SAM 3.1 with a new short noun phrase on a time window (>= 10 s is "
        f"billed anyway). New tracks can be cited for for_check. At most {MAX_RECHECKS} per clip.",
        {"phrase": {"type": "string"}, "start_ms": {"type": "integer"}, "end_ms": {"type": "integer"},
         "for_check": {"type": "string", "enum": CHECK_ENUM}},
        ["phrase", "start_ms", "end_ms", "for_check"]),
    _fn("cite_finding", "Record one likely barrier, cited to a track and a frame where it has a box. "
        "Returns ok, or a reason to fix and retry.",
        {"check_id": {"type": "string", "enum": CHECK_ENUM},
         "track_id": {"type": "string"}, "frame_index": {"type": "integer"},
         "severity": {"type": "string", "enum": ["low", "medium", "high"]},
         "confidence": {"type": "number", "minimum": 0, "maximum": 1},
         "title": {"type": "string", "description": "one line, e.g. 'Bin blocks half the sidewalk'"},
         "evidence_note": {"type": "string", "description": "what you saw and why it is likely a "
                           "barrier; say what needs checking on site"},
         "related_track_ids": {"type": "array", "items": {"type": "string"}}},
        ["check_id", "track_id", "frame_index", "severity", "confidence", "title", "evidence_note"]),
    _fn("finish", "End the review. List checks that cannot occur on this clip, and summarize the route.",
        {"not_applicable": {"type": "array", "items": {"type": "string", "enum": CHECK_ENUM}},
         "summary": {"type": "string"}},
        ["not_applicable", "summary"]),
]


# --------------------------------------------------------------------------- #
# context
# --------------------------------------------------------------------------- #
@dataclass
class AgentContext:
    meta: IngestMeta
    inv: Inventory
    records: dict[str, list[SamRecord]]  # phrase -> stitched records (with masks)
    rules: Rules
    plate_tracks: list[Track] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)
    extra_phrases: dict[str, set[str]] = field(default_factory=dict)
    rechecks: int = 0
    finished: bool = False
    not_applicable: list[str] = field(default_factory=list)
    summary: str = ""
    recheck_fn: object = None  # (ctx, phrase, start_ms, end_ms) -> list[SamRecord]


def load_context(clip_stem: str, out_root: Path = DEFAULT_OUT_ROOT) -> AgentContext:
    """Meta + inventory + stitched SAM records for one clip, all from the local cache."""
    meta = ingest(REPO_ROOT / "data" / "raw" / f"{clip_stem}.mp4")
    inv = Inventory.model_validate_json((Path(out_root) / meta.video_sha256 / "inventory.json").read_text())

    def no_net(*_a, **_k):
        raise RuntimeError(f"SAM phrase not cached for {clip_stem}; run d4-samall first")

    records = {
        p: stitch_ids(cache.segment_cached(None, meta, p, segment_fn=no_net, upload_fn=no_net).records)
        for p in SAM_PHRASES
    }
    plates = build_tracks(PLATE_PHRASE, records.pop(PLATE_PHRASE), meta)
    return AgentContext(meta=meta, inv=inv, records=records, rules=load_rules(), plate_tracks=plates)


# --------------------------------------------------------------------------- #
# prompts
# --------------------------------------------------------------------------- #
def _where(b, w: int, h: int) -> str:
    cx, cy = (b.x1 + b.x2) / 2 / w, (b.y1 + b.y2) / 2 / h
    col = "left" if cx < 0.33 else "right" if cx > 0.67 else "center"
    row = "top" if cy < 0.33 else "bottom" if cy > 0.67 else "middle"
    return f"{row}-{col}, {100 * (b.x2 - b.x1) / w:.0f}% wide"


def system_prompt(rules: Rules) -> str:
    parts = [
        "You review a first-person walking video of a route for wheelchair users. SAM 3.1 has already "
        "tracked objects in it; you decide which ones are likely barriers and cite each with a tool call.",
        "Rules: cite only what the tracks and tools show. Every finding cites a track_id and a "
        "frame_index where that track has a box. Say 'likely barrier' and 'verify on site', never "
        "'violation' or 'non-compliant'. Heights, slopes and widths judged from video are estimates. "
        "Check the pitfalls before citing. If nothing qualifies for a check, cite nothing for it. "
        "When done, call finish.",
        "Checks:",
    ]
    for cid, r in rules.checks.items():
        sev = "; ".join(f"{k}: {v}" for k, v in r.severity.items())
        pit = "; ".join(r.pitfalls) or "none"
        parts.append(
            f"- {cid}: {r.question} Cite tracks of: {', '.join(r.evidence_phrases)}. "
            f"Judged from: {r.judged_from}. Severity: {sev}. Pitfalls: {pit}."
        )
    return "\n".join(parts)


def inventory_prompt(ctx: AgentContext) -> str:
    m = ctx.meta
    lines = [
        f"Clip {m.source.filename}: {m.source.duration_s:.1f} s, {m.sam.n_frames} frames at "
        f"{m.sam.fps:g} fps (frame_index i is at i*{1000 / m.sam.fps:g} ms), {m.sam.width}x{m.sam.height}.",
        "No narration on this clip." ,
        "Tracks (track_id | phrase | seconds | frames | mean conf | keyframe | where on the keyframe):",
    ]
    for t in sorted(ctx.inv.kept(), key=lambda t: (t.phrase, t.first_ms)):
        kb = next(b for b in t.boxes if b.frame_index == t.keyframe_index)
        conf = f"{t.mean_conf:.2f}" if t.mean_conf is not None else "-"
        lines.append(
            f"{t.track_id} | {t.phrase} | {t.first_ms / 1000:.1f}-{t.last_ms / 1000:.1f} | {t.n_frames} | "
            f"{conf} | f{t.keyframe_index} | {_where(kb, m.sam.width, m.sam.height)}"
        )
    if not ctx.inv.kept():
        lines.append("(none)")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# tools
# --------------------------------------------------------------------------- #
def _track(ctx: AgentContext, track_id: str) -> Track | None:
    return next((t for t in ctx.inv.tracks if t.track_id == track_id), None)


def _records_of(ctx: AgentContext, t: Track) -> dict[int, SamRecord]:
    return {r.frame_index: r for r in ctx.records.get(t.phrase, []) if r.object_id == t.object_id}


def tool_get_track(ctx: AgentContext, track_id: str) -> dict:
    t = _track(ctx, track_id)
    if t is None:
        return {"error": f"unknown track_id {track_id!r}"}
    step = max(1, len(t.boxes) // SAMPLE_BOXES)
    sample = t.boxes[::step][:SAMPLE_BOXES]
    if t.keyframe_index not in {b.frame_index for b in sample}:
        sample.append(next(b for b in t.boxes if b.frame_index == t.keyframe_index))
    recs = _records_of(ctx, t)
    walks: dict[int, list[SamRecord]] = {}
    for r in ctx.records.get("sidewalk", []):
        walks.setdefault(r.frame_index, []).append(r)
    rows, note = [], None
    for b in sorted(sample, key=lambda b: b.frame_index):
        row = {"frame_index": b.frame_index, "ms": b.frame_ms, "box": [b.x1, b.y1, b.x2, b.y2],
               "conf": b.conf}
        if t.phrase != "sidewalk":
            rec = recs.get(b.frame_index)
            try:
                if rec is not None and rec.mask is not None:
                    side = [(w, masks.decode_raster(w.mask))
                            for w in walks.get(b.frame_index, []) if w.mask]
                    obj = (rec, masks.decode_raster(rec.mask))
                    row["on_sidewalk"] = masks.on_sidewalk_fraction(obj, side)
            except RuntimeError as e:  # decoder missing: say so instead of guessing from boxes
                note = str(e)
        rows.append(row)
    out = {"track_id": t.track_id, "phrase": t.phrase, "seconds": [t.first_ms / 1000, t.last_ms / 1000],
           "n_frames": t.n_frames, "mean_conf": t.mean_conf, "keyframe_index": t.keyframe_index,
           "frames": rows}
    if note:
        out["on_sidewalk_unavailable"] = note
    return out


def tool_recheck(ctx: AgentContext, phrase: str, start_ms: int, end_ms: int, for_check: str) -> dict:
    if ctx.rechecks >= MAX_RECHECKS:
        return {"error": f"recheck limit ({MAX_RECHECKS}) reached"}
    if for_check not in ctx.rules.checks:
        return {"error": f"unknown check {for_check!r}"}
    phrase = phrase.strip().lower()
    if not 0 < len(phrase.split()) <= 4:
        return {"error": "phrase must be a short noun phrase (1-4 words)"}
    if ctx.recheck_fn is None:
        return {"error": "recheck_with_sam is not enabled for this run"}
    ctx.rechecks += 1
    records = ctx.recheck_fn(ctx, phrase, start_ms, end_ms)
    label = f"recheck {phrase}"
    new = build_tracks(label, stitch_ids(records), ctx.meta)
    ctx.records[label] = stitch_ids(records)
    ctx.inv.tracks.extend(new)
    ctx.extra_phrases.setdefault(for_check, set()).add(label)
    return {"new_tracks": [
        {"track_id": t.track_id, "seconds": [t.first_ms / 1000, t.last_ms / 1000],
         "n_frames": t.n_frames, "mean_conf": t.mean_conf, "keyframe_index": t.keyframe_index}
        for t in new
    ] or "no matches"}


def tool_cite(ctx: AgentContext, args: dict) -> dict:
    res = validate_citation(args, ctx.inv, ctx.meta, ctx.rules, ctx.extra_phrases)
    if isinstance(res, Rejection):
        ctx.rejections.append(res)
        return {"ok": False, "reason": res.reason}
    ctx.findings.append(res)
    return {"ok": True, "cited": len(ctx.findings)}


def tool_finish(ctx: AgentContext, not_applicable: list, summary: str) -> dict:
    ctx.not_applicable = [c for c in not_applicable if c in ctx.rules.checks]
    ctx.summary = summary
    ctx.finished = True
    return {"ok": True}


def dispatch(ctx: AgentContext, name: str, arguments: str) -> dict:
    try:
        args = json.loads(arguments or "{}")
    except json.JSONDecodeError as e:
        return {"error": f"arguments are not valid JSON: {e}"}
    try:
        if name == "get_track":
            return tool_get_track(ctx, args["track_id"])
        if name == "recheck_with_sam":
            return tool_recheck(ctx, args["phrase"], int(args["start_ms"]), int(args["end_ms"]),
                                args["for_check"])
        if name == "cite_finding":
            return tool_cite(ctx, args)
        if name == "finish":
            return tool_finish(ctx, args.get("not_applicable", []), args.get("summary", ""))
    except KeyError as e:
        return {"error": f"missing argument {e}"}
    return {"error": f"unknown tool {name!r}"}


# --------------------------------------------------------------------------- #
# SAM recheck on a window (real implementation; tests inject a fake)
# --------------------------------------------------------------------------- #
def sam_recheck(ctx: AgentContext, phrase: str, start_ms: int, end_ms: int,
                out_root: Path = DEFAULT_OUT_ROOT) -> list[SamRecord]:
    from . import sam

    m = ctx.meta
    fms = m.frame_ms
    a = next((i for i, t in enumerate(fms) if t >= start_ms), 0)
    b = max((i for i, t in enumerate(fms) if t <= end_ms), default=len(fms) - 1)
    while b - a + 1 < sam.MIN_BILLED_FRAMES and (a > 0 or b < len(fms) - 1):
        a, b = max(0, a - 1), min(len(fms) - 1, b + 1)  # 50 frames are billed anyway
    win = Path(out_root) / m.video_sha256 / "recheck" / f"{a}_{b}"
    cpath = win / f"{phrase_slug(phrase)}.json"
    if cpath.exists():
        data, hit, cost = json.loads(cpath.read_text()), True, 0.0
    else:
        clip = win / "sam.mp4"  # upload guard only accepts files named sam.mp4
        if not clip.exists():
            win.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-v", "error", "-y", "-i",
                 str(Path(out_root) / m.video_sha256 / "sam.mp4"),
                 "-vf", f"select=between(n\\,{a}\\,{b}),setpts=N/FRAME_RATE/TB", "-an",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", "-map_metadata", "-1", str(clip)],
                check=True,
            )
        client = sam.make_client()
        text, used, served = sam.segment_phrase(client, sam.upload_sam_video(client, clip), phrase)
        if not used:
            raise RuntimeError("SAM recheck returned no usage; not caching a partial result")
        data = {"output_text": text, "usage": used, "model_served": served, "window": [a, b]}
        hit = False
        frames = used.get("video_frames_processed") or sam.billed_frames(b - a + 1)
        cost = frames * sam.PRICE_PER_1K_FRAMES / 1000
        cpath.write_text(json.dumps(data))
    usage.log_call(usage.UsageRecord(
        provider="meta", model_requested=sam.MODEL, model_served=data.get("model_served"),
        usage=data["usage"], cache_hit=hit, cost_usd=cost, video_sha256=m.video_sha256, phrase=phrase,
        extra={"tag": "recheck", "window": [a, b]},
    ))
    recs = parse_output(data["output_text"])
    return [r.model_copy(update={"frame_index": r.frame_index + a}) for r in recs]  # window -> clip index


# --------------------------------------------------------------------------- #
# loop
# --------------------------------------------------------------------------- #
def _clean(msg: dict) -> dict:
    """Assistant message as sent back to the API: role, content, tool_calls only."""
    out = {"role": "assistant", "content": msg.get("content") or ""}
    if msg.get("tool_calls"):
        out["tool_calls"] = [
            {"id": c["id"], "type": "function",
             "function": {"name": c["function"]["name"], "arguments": c["function"].get("arguments", "{}")}}
            for c in msg["tool_calls"]
        ]
    return out


@dataclass
class RunResult:
    report: Report
    turns: int
    hit_turn_cap: bool
    providers: list[str]
    models_served: list[str]
    cost_usd: float
    rejections: list[Rejection]


def run_agent(ctx: AgentContext, *, allow_closed: bool = False, chat_fn=llm.chat,
              run_log: Path = RUN_LOG, render: bool = True) -> RunResult:
    messages: list[dict] = [
        {"role": "system", "content": system_prompt(ctx.rules)},
        {"role": "user", "content": inventory_prompt(ctx)},
    ]
    providers: list[str] = []
    served: list[str] = []
    cost = 0.0
    turns = 0
    nudged = False
    for turns in range(1, MAX_TURNS + 1):  # noqa: B007 (turns is reported after the loop)
        res = chat_fn(messages, video_sha256=ctx.meta.video_sha256, tools=TOOLS, params=PARAMS,
                      allow_closed=allow_closed)
        providers.append(res.provider)
        served.append(res.model_served or "")
        cost += res.cost_usd
        msg = _clean(res.message)
        messages.append(msg)
        calls = msg.get("tool_calls", [])
        if not calls:
            if nudged:
                break  # the model stopped twice without calling finish
            nudged = True
            messages.append({"role": "user", "content": "Use the tools: cite findings, then call finish."})
            continue
        for c in calls:  # parallel calls in one turn run in the order given
            out = dispatch(ctx, c["function"]["name"], c["function"]["arguments"])
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(out)})
        if ctx.finished:
            break
    hit_cap = not ctx.finished and turns >= MAX_TURNS

    findings = finalize(ctx.findings)
    if render and findings:
        render_frames(ctx.meta, {f.frame_index for f in findings}, ctx.plate_tracks)
    report = build_report(ctx, findings, providers, served, cost, len(providers))
    _log_run(run_log, ctx, turns, hit_cap, providers, cost, findings)
    return RunResult(report, turns, hit_cap, providers, served, cost, ctx.rejections)


def build_report(ctx: AgentContext, findings: list[Finding], providers: list[str], served: list[str],
                 cost: float, n_calls: int) -> Report:
    m = ctx.meta
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.check_id] = counts.get(f.check_id, 0) + 1
    checks = [
        CheckSummary(check_id=cid, status="not_applicable" if cid in ctx.not_applicable else "ran",
                     n_findings=counts.get(cid, 0))
        for cid in ctx.rules.checks
    ]
    # Placeholder verdict until d6-verdict: driven only by cited severities.
    high = [f.finding_id for f in findings if f.severity == "high"]
    rating = "likely_blocked" if high else "caution" if findings else "no_likely_barriers"
    used_closed = llm.CLOSED_PROVIDER in providers
    hosts = list(dict.fromkeys(providers)) or ["none"]
    return Report(
        report_id=f"{m.video_sha256[:12]}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}",
        title=m.source.filename.rsplit(".", 1)[0],
        video=VideoInfo(video_sha256=m.video_sha256, duration_ms=round(m.source.duration_s * 1000),
                        width=m.sam.width, height=m.sam.height, sam_fps=m.sam.fps,
                        proxy_url=f"/media/{m.video_sha256}/proxy.mp4", frame_ms=m.frame_ms),
        verdict=RouteVerdict(rating=rating, summary=ctx.summary or "No summary from the agent.",
                             key_finding_ids=high or [f.finding_id for f in findings[:1]]),
        findings=findings,
        tracks=ctx.inv.tracks,
        checks=checks,
        run=RunInfo(agent_provider="+".join(hosts),
                    agent_model="+".join(dict.fromkeys(s for s in served if s)) or "unknown",
                    sam_model="sam-3.1", n_model_calls=n_calls, cost_usd=round(cost, 4),
                    created_at=datetime.now(UTC).isoformat(timespec="seconds"),
                    used_closed_fallback=used_closed),
    )


def _log_run(path: Path, ctx: AgentContext, turns: int, hit_cap: bool, providers: list[str],
             cost: float, findings: list[Finding]) -> None:
    rec = {"ts": datetime.now(UTC).isoformat(), "video_sha256": ctx.meta.video_sha256,
           "clip": ctx.meta.source.filename, "turns": turns, "hit_turn_cap": hit_cap,
           "finished": ctx.finished, "providers": providers, "cost_usd": round(cost, 4),
           "n_findings": len(findings), "n_rejections": len(ctx.rejections), "rechecks": ctx.rechecks}
    if hit_cap:
        rec["warning"] = f"hit the {MAX_TURNS}-turn cap before finish"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
