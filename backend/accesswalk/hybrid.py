"""Hybrid stage (hybrid-proposals): a video-level model proposes candidate barriers with
times, and the verification agent checks each one against the SAM tracks and frames.

A proposal is only a hint. Nothing reaches the report unless the agent cites it with the
usual cite_finding call, so the validator's track + frame rule still decides what is a
finding. The agent gives every proposal a verdict in ``finish``; the report keeps them
(``Report.proposals``) so a reader can see what was proposed and why it was dropped.

Proposers:
  * ``propose_open``: Muse Spark Open on Baseten watches ``proposer.mp4`` (made from the
    blurred proxy.mp4: 2 fps, 480 px wide, no audio, no metadata) as a ``video_url`` part.
    Baseten accepts video for this model (probe, Nov 3: a 4 s clip, $0.0023). Open weight,
    so the whole run stays open-weight. Cached and logged through llm.chat.
  * ``proposals_from_report``: the findings of an existing raw-video report, e.g. the
    frozen baseline-v1 run (Muse Spark 1.3 on proxy.mp4). Free for the eval.

Muse Spark 1.3 is a closed model. A run with its proposals is not open-weight only, so
``RunInfo.proposer_*`` names it and ``RunInfo.proposer_open_weight`` is false.
"""
from __future__ import annotations

import base64
import bisect
import subprocess
from pathlib import Path

from pydantic import BaseModel

from . import llm
from .ingest import DEFAULT_OUT_ROOT, IngestMeta
from .rules import Rules
from .schemas import Report

MAX_PROPOSALS = 12  # keeps the prompt short; raw-video runs give 0-4 per clip
PROPOSER_FPS = 2
PROPOSER_WIDTH = 480
PROPOSER_VIDEO = "proposer.mp4"
PROPOSER_PARAMS = {"temperature": 0, "max_tokens": 8000}


class Proposal(BaseModel):
    n: int  # 1-based, as the agent sees it
    check_id: str
    frame_ms: int
    frame_index: int  # nearest SAM frame, so the agent can view it directly
    title: str
    note: str = ""


class Proposer(BaseModel):
    provider: str
    model: str
    open_weight: bool
    source: str  # "frozen run baseline-v1", "live", ...


def _nearest(frame_ms: list[int], ms: int) -> int:
    i = bisect.bisect_left(frame_ms, ms)
    if i <= 0:
        return 0
    if i >= len(frame_ms):
        return len(frame_ms) - 1
    return i if frame_ms[i] - ms < ms - frame_ms[i - 1] else i - 1


def proposals_from_report(report: Report, meta: IngestMeta) -> list[Proposal]:
    """Candidates from a raw-video report, in time order. Its placeholder tracks and boxes
    are dropped: the agent has to find the object among the SAM tracks itself."""
    fs = sorted(report.findings, key=lambda f: f.frame_ms)[:MAX_PROPOSALS]
    return [
        Proposal(n=i, check_id=f.check_id, frame_ms=f.frame_ms,
                 frame_index=_nearest(meta.frame_ms, f.frame_ms),
                 title=f.title, note=f.evidence_note[:400])
        for i, f in enumerate(fs, start=1)
    ]


def proposer_of(report: Report, source: str) -> Proposer:
    return Proposer(provider=report.run.agent_provider, model=report.run.agent_model,
                    open_weight=report.run.agent_provider in llm.OPEN_PROVIDERS, source=source)


def proposer_video(meta: IngestMeta, out_root: Path = DEFAULT_OUT_ROOT) -> Path:
    """``proposer.mp4``, cut once from the published proxy.mp4 (faces and plates blurred).
    Never from data/raw: the proxy is the only input."""
    clip_dir = Path(out_root) / meta.video_sha256
    out = clip_dir / PROPOSER_VIDEO
    if not out.exists():
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-v", "error", "-y", "-i", str(clip_dir / "proxy.mp4"),
             "-vf", f"fps={PROPOSER_FPS},scale={PROPOSER_WIDTH}:-2", "-an", "-c:v", "libx264",
             "-pix_fmt", "yuv420p", "-crf", "28", "-threads", "1", "-map_metadata", "-1", str(out)],
            check=True,
        )
    return out


def pixel_box(box, w: int, h: int):
    """Muse Spark Open often answers with 0-1 fractions instead of pixels: scale those.
    Anything else is passed on for baseline.py's gates to judge."""
    if not (isinstance(box, list) and len(box) == 4 and all(isinstance(v, int | float) for v in box)):
        return box
    if all(0 <= v <= 1 for v in box) and any(isinstance(v, float) for v in box):
        return [round(box[0] * w), round(box[1] * h), round(box[2] * w), round(box[3] * h)]
    return [round(v) for v in box]


def proposer_prompt(rules: Rules, meta: IngestMeta) -> str:
    from .baseline import build_prompt

    questions = {cid: r.question for cid, r in rules.checks.items()}  # as v3 ran (rules v2)
    duration_ms = round(meta.source.duration_s * 1000)
    return build_prompt(rules, meta.sam.width, meta.sam.height, duration_ms, questions) + (
        f"\nThe video is sampled at {PROPOSER_FPS} frames per second: frame k is at "
        f"{1000 // PROPOSER_FPS}*k ms. Give frame_ms as time from the start."
    )


def propose_open(meta: IngestMeta, rules: Rules, out_root: Path = DEFAULT_OUT_ROOT,
                 chat_fn=llm.chat) -> tuple[list[Proposal], Proposer, Report, float]:
    """Muse Spark Open watches the clip once and proposes candidates. Returns the proposals,
    the proposer, its findings as a raw-video report (scored like the baseline) and the cost."""
    from . import baseline

    url = "data:video/mp4;base64," + base64.b64encode(proposer_video(meta, out_root).read_bytes()).decode()
    messages = [{"role": "user", "content": [
        {"type": "video_url", "video_url": {"url": url}},
        {"type": "text", "text": proposer_prompt(rules, meta)},
    ]}]
    res = chat_fn(messages, video_sha256=meta.video_sha256, params=PROPOSER_PARAMS, tag="proposer")
    raw = baseline.RawResponse(text=res.message.get("content") or "", usage=res.usage,
                               model_served=res.model_served)
    try:
        output = baseline.parse_output(raw.text)
    except ValueError:
        output = baseline.RawOutput()  # unreadable answer: no proposals, the agent reviews as usual
    for f in output.findings:
        f["bbox"] = pixel_box(f.get("bbox"), meta.sam.width, meta.sam.height)
    report, _ = baseline.build_report(meta, rules, output, raw, res.cost_usd)
    report.report_id = f"proposer-{meta.video_sha256[:12]}"
    report.run.agent_provider = res.provider
    report.run.used_closed_fallback = res.provider == llm.CLOSED_PROVIDER
    proposer = Proposer(provider=res.provider, model=res.model_served or "unknown",
                        open_weight=res.provider in llm.OPEN_PROVIDERS, source="live")
    return proposals_from_report(report, meta), proposer, report, res.cost_usd


def proposals_prompt(proposals: list[Proposal]) -> str:
    if not proposals:
        return ("A second model watched the whole video without tracking and proposed no candidate "
                "barriers. That does not mean there are none: review the clip as usual.")
    lines = [
        "A second model watched the whole video without tracking and proposed the candidate barriers "
        "below. They are unverified hints. That model is often right about what is on the route, but "
        "its times can be off by a few seconds and its check can be wrong. For each candidate, look at "
        "the tracks and frames around its time. Cite a finding (under whichever check fits) only if "
        "the tracks and frames support it; otherwise reject it. A candidate is not evidence: never cite "
        "one without a track that has a box on the cited frame. If a candidate looks real in the frames "
        "but no track covers it, spend recheck_with_sam on it (if the first short phrase finds nothing, "
        "try another one for the same object); do not spend rechecks on candidates the frames already "
        "rule out. The candidates do not replace your own review: still check the whole clip. In "
        "finish, give a verdict for every candidate.",
        "Candidates (n | check | time | nearest frame | what it said):",
    ]
    for p in proposals:
        note = f" {p.note}" if p.note else ""
        lines.append(f"{p.n} | {p.check_id} | {p.frame_ms / 1000:.1f} s | f{p.frame_index} | "
                     f"{p.title}.{note}")
    return "\n".join(lines)
