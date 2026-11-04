"""Raw-video baseline (d7-baseline): Muse Spark 1.3 watches the clip once. No SAM, no tools,
no rules beyond the 8 check questions. Eval compares the agent against this.

Input is the published ``proxy.mp4``: faces and plates blurred, metadata stripped. The file
in ``data/raw`` is never sent. Output is a real ``schemas.Report``, the same schema as the
agent's, so eval reads both the same way. The model has no tracks to cite, so each finding gets
a one-box placeholder track (phrase ``BASELINE_PHRASE``) built from the box the model gave;
nothing about it is verified.
"""

from __future__ import annotations

import bisect
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

from . import usage
from .ingest import DEFAULT_OUT_ROOT, IngestMeta
from .rules import Rules
from .schemas import BBox, CheckSummary, Finding, Report, RunInfo, Track, TrackBox, VideoInfo
from .validator import BANNED, strip_box_colours
from .verdict import route_verdict

MODEL = "muse-spark-1.3"
PRICE_IN, PRICE_OUT = 1.25, 4.25  # USD per 1M tokens
MAX_OUTPUT_TOKENS = 8000
BASELINE_PHRASE = "baseline (no SAM track)"
ALLOWED_VIDEO = "proxy.mp4"


class RawFinding(BaseModel):
    check_id: str
    title: str = Field(min_length=3)
    severity: str
    confidence: float = Field(ge=0, le=1)
    frame_ms: int = Field(ge=0)
    bbox: list[int] = Field(min_length=4, max_length=4)
    evidence_note: str = Field(min_length=1)


class RawOutput(BaseModel):
    findings: list[dict] = Field(default_factory=list)
    summary: str = ""


def build_prompt(rules: Rules, width: int, height: int, duration_ms: int) -> str:
    checks = "\n".join(f"- {cid}: {r.question}" for cid, r in rules.checks.items())
    return (
        "You are screening a first-person walkthrough video of a route for wheelchair users. "
        "Report likely barriers only, in plain words; this is not a compliance determination.\n\n"
        f"Checks:\n{checks}\n\n"
        "Severity: high = likely stops a wheelchair; medium = passable with effort or help; "
        "low = minor, worth knowing.\n\n"
        f"The video is {width}x{height} pixels and {duration_ms} ms long. Reply with JSON only, no "
        "markdown fence, exactly this shape:\n"
        '{"findings": [{"check_id": "<one of the checks>", "title": "<one line>", '
        '"severity": "low|medium|high", "confidence": <0 to 1>, "frame_ms": <when it is best seen, '
        'ms from the start>, "bbox": [x1, y1, x2, y2], "evidence_note": "<what you saw and where>"}], '
        '"summary": "<one or two sentences about the route>"}\n'
        'If there are no likely barriers, return an empty "findings" list.'
    )


@dataclass
class RawResponse:
    text: str
    usage: dict
    model_served: str | None


def upload_proxy(client: OpenAI, proxy_mp4: Path) -> str:
    """Refuses anything but ``proxy.mp4``, so a raw clip can never go up."""
    if proxy_mp4.name != ALLOWED_VIDEO:
        raise ValueError(f"refusing to upload {proxy_mp4.name!r}: the baseline may only send {ALLOWED_VIDEO}")
    with proxy_mp4.open("rb") as f:
        return client.files.create(purpose="user_data", file=f).id


def call_model(client: OpenAI, file_id: str, prompt: str) -> RawResponse:
    """Streamed: long clips otherwise risk idle-timeout disconnects (per the docs)."""
    req = dict(
        model=MODEL,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        input=[
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_video", "file_id": file_id},
                ],
            }
        ],
    )
    with client.responses.stream(**req) as stream:
        for _ in stream:
            pass
        final = stream.get_final_response()
    raw_usage = final.usage.model_dump() if getattr(final, "usage", None) is not None else {}
    return RawResponse(getattr(final, "output_text", "") or "", raw_usage, getattr(final, "model", None))


def cost_usd(raw_usage: dict) -> float:
    return (raw_usage.get("input_tokens", 0) * PRICE_IN + raw_usage.get("output_tokens", 0) * PRICE_OUT) / 1e6


def parse_output(text: str) -> RawOutput:
    """Tolerates a markdown fence or text around the JSON object. Raises ValueError if none."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in the model output")
    return RawOutput.model_validate_json(re.sub(r"[\x00-\x1f]", " ", text[start : end + 1]))


def _clean_finding(raw: dict, rules: Rules, meta: IngestMeta) -> RawFinding | None:
    """Same wording and vocabulary gates as the agent. There is no citation to check:
    that is what the baseline lacks."""
    try:
        f = RawFinding.model_validate(raw)
    except ValidationError:
        return None
    rule = rules.checks.get(f.check_id)  # type: ignore[call-overload]
    if rule is None or f.severity not in rule.severity:
        return None
    if BANNED.search(f.title) or BANNED.search(f.evidence_note):
        return None
    w, h = meta.sam.width, meta.sam.height
    x1, x2 = sorted((min(max(f.bbox[0], 0), w), min(max(f.bbox[2], 0), w)))
    y1, y2 = sorted((min(max(f.bbox[1], 0), h), min(max(f.bbox[3], 0), h)))
    return f.model_copy(
        update={"bbox": [x1, y1, x2, y2], "evidence_note": strip_box_colours(f.evidence_note)}
    )


def _nearest_frame(frame_ms: list[int], ms: int) -> int:
    i = bisect.bisect_left(frame_ms, ms)
    if i == 0:
        return 0
    if i == len(frame_ms):
        return len(frame_ms) - 1
    return i if frame_ms[i] - ms < ms - frame_ms[i - 1] else i - 1


def build_report(
    meta: IngestMeta, rules: Rules, output: RawOutput, raw_response: RawResponse, cost: float
) -> tuple[Report, int]:
    """Returns the report and how many of the model's findings failed the gates."""
    kept = [c for c in (_clean_finding(r, rules, meta) for r in output.findings) if c is not None]
    tracks, findings = [], []
    # The eval time is the model's own frame_ms; only the placeholder box snaps to a SAM frame.
    for i, f in enumerate(sorted(kept, key=lambda f: f.frame_ms), start=1):
        idx = _nearest_frame(meta.frame_ms, f.frame_ms)
        x1, y1, x2, y2 = f.bbox
        tid = f"baseline-{i}"
        tracks.append(
            Track(
                track_id=tid,
                phrase=BASELINE_PHRASE,
                object_id=i,
                first_ms=meta.frame_ms[idx],
                last_ms=meta.frame_ms[idx],
                n_frames=1,
                keyframe_index=idx,
                keyframe_ms=meta.frame_ms[idx],
                boxes=[TrackBox(frame_index=idx, frame_ms=meta.frame_ms[idx], x1=x1, y1=y1, x2=x2, y2=y2)],
            )
        )
        findings.append(
            Finding(
                finding_id=f"f{i}",
                check_id=f.check_id,
                title=f.title[:90],
                severity=f.severity,
                confidence=round(f.confidence, 2),
                track_id=tid,
                frame_index=idx,
                frame_ms=f.frame_ms,
                bbox=BBox(x1=x1, y1=y1, x2=x2, y2=y2),
                evidence_note=f.evidence_note,
                verify_manually=rules.checks[f.check_id].verify_manually == "always",
            )
        )
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.check_id] = counts.get(f.check_id, 0) + 1
    m = meta
    report = Report(
        report_id=f"baseline-{m.video_sha256[:12]}",
        title=m.source.filename.rsplit(".", 1)[0],
        video=VideoInfo(
            video_sha256=m.video_sha256,
            duration_ms=round(m.source.duration_s * 1000),
            width=m.sam.width,
            height=m.sam.height,
            sam_fps=m.sam.fps,
            proxy_url=f"/media/{m.video_sha256}/proxy.mp4",
            frame_ms=m.frame_ms,
        ),
        verdict=route_verdict(findings, output.summary),
        findings=findings,
        tracks=tracks,
        checks=[CheckSummary(check_id=c, status="ran", n_findings=counts.get(c, 0)) for c in rules.checks],
        run=RunInfo(
            agent_provider="meta",
            agent_model=raw_response.model_served or MODEL,
            sam_model="none",
            n_model_calls=1,
            cost_usd=round(cost, 4),
            created_at=datetime.now(UTC).isoformat(timespec="seconds"),
            used_closed_fallback=True,
        ),
    )
    return report, len(output.findings) - len(kept)


def cache_path(meta: IngestMeta, rules: Rules, out_root: Path = DEFAULT_OUT_ROOT) -> Path:
    """Where this clip's answer is cached, keyed by (model, output limit, prompt)."""
    import hashlib

    prompt = build_prompt(rules, meta.sam.width, meta.sam.height, round(meta.source.duration_s * 1000))
    key = hashlib.sha256(f"{MODEL}|{MAX_OUTPUT_TOKENS}|{prompt}".encode()).hexdigest()[:20]
    return Path(out_root) / meta.video_sha256 / "baseline" / f"{key}.json"


def run_clip(
    meta: IngestMeta,
    rules: Rules,
    client: OpenAI | None = None,
    out_root: Path = DEFAULT_OUT_ROOT,
    usage_log: str | Path = usage.DEFAULT_USAGE_LOG,
    upload_fn=upload_proxy,
    call_fn=call_model,
) -> tuple[Report, int, dict]:
    """One clip, cached by (clip, model, prompt). Returns (report, findings dropped, usage)."""
    clip_dir = Path(out_root) / meta.video_sha256
    prompt = build_prompt(rules, meta.sam.width, meta.sam.height, round(meta.source.duration_s * 1000))
    cpath = cache_path(meta, rules, out_root)
    key = cpath.stem
    hit = cpath.exists()
    if hit:
        raw = RawResponse(**json.loads(cpath.read_text(encoding="utf-8")))
        cost = 0.0
    else:
        client = client or OpenAI(
            api_key=os.environ["MODEL_API_KEY"], base_url=os.getenv("META_BASE_URL", "https://api.meta.ai/v1")
        )
        raw = call_fn(client, upload_fn(client, clip_dir / ALLOWED_VIDEO), prompt)
        cost = cost_usd(raw.usage)
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_text(json.dumps(raw.__dict__), encoding="utf-8")
    usage.log_call(
        usage.UsageRecord(
            provider="meta",
            model_requested=MODEL,
            model_served=raw.model_served,
            usage=raw.usage,
            cache_hit=hit,
            cost_usd=cost,
            video_sha256=meta.video_sha256,
            extra={"tag": "baseline", "cache_key": key},
        ),
        path=usage_log,
    )
    report, dropped = build_report(meta, rules, parse_output(raw.text), raw, cost_usd(raw.usage))
    return report, dropped, raw.usage
