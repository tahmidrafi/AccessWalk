"""Content-addressed cache for SAM requests + usage logging.

A SAM response is cached by (raw video sha256, model, phrase, mask_encoding,
ingest params). The ingest params are in the key because the frame indices in a
response are indices into the re-encoded ``sam.mp4``: keying on the raw hash alone
would hand back tracks that no longer line up after any ingest change.

The raw response text and usage are written to the cache *before* parsing, so a
parser bug can never force a second paid call. A stream that did not complete
(no usage reported) is not cached. Every call -- hit or miss -- is logged to
``usage.jsonl`` via :mod:`usage`.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from . import sam, usage
from .ingest import DEFAULT_OUT_ROOT, IngestMeta
from .sam_parse import SamRecord, parse_output

CACHE_SCHEMA = 1


class SegmentResult(BaseModel):
    records: list[SamRecord]
    output_text: str
    usage: dict
    model_served: str | None
    cache_hit: bool
    cost_usd: float
    cache_key: str
    file_id: str | None = None


def cache_key(
    model: str, phrase: str, mask_encoding: str,
    ingest_version: int, sam_fps: float, sam_w: int, sam_h: int,
) -> str:
    blob = json.dumps(
        {
            "schema": CACHE_SCHEMA, "model": model, "phrase": phrase,
            "mask_encoding": mask_encoding, "ingest_version": ingest_version,
            "sam_fps": sam_fps, "sam_w": sam_w, "sam_h": sam_h,
        },
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def cache_path(out_root: str | Path, video_sha256: str, key: str) -> Path:
    return Path(out_root) / video_sha256 / "sam" / f"{key}.json"


def _cost_from_usage(usage_dict: dict, meta: IngestMeta) -> float:
    frames = usage_dict.get("video_frames_processed") or sam.billed_frames(meta.sam.n_frames)
    return frames * sam.PRICE_PER_1K_FRAMES / 1000.0


def segment_cached(
    client,
    meta: IngestMeta,
    phrase: str,
    *,
    provider: str = "meta",
    model: str = sam.MODEL,
    mask_encoding: str = "one_bit",
    out_root: str | Path = DEFAULT_OUT_ROOT,
    usage_log: str | Path = usage.DEFAULT_USAGE_LOG,
    file_id: str | None = None,
    force: bool = False,
    segment_fn=sam.segment_phrase,
    upload_fn=sam.upload_sam_video,
) -> SegmentResult:
    """Segment one ``phrase``, using the cache when possible. ``file_id`` lets the
    caller upload the clip once and reuse it across phrases."""
    key = cache_key(
        model, phrase, mask_encoding,
        meta.ingest_version, meta.sam.fps, meta.sam.width, meta.sam.height,
    )
    cpath = cache_path(out_root, meta.video_sha256, key)
    sam_mp4 = Path(out_root) / meta.video_sha256 / "sam.mp4"

    if cpath.exists() and not force:
        payload = json.loads(cpath.read_text())
        text, used, served = payload["output_text"], payload["usage"], payload.get("model_served")
        cache_hit, cost = True, 0.0
    else:
        if file_id is None:
            file_id = upload_fn(client, sam_mp4)
        text, used, served = segment_fn(client, file_id, phrase, mask_encoding=mask_encoding)
        if not used:
            # No usage reported -> treat as an incomplete stream; do not cache.
            raise RuntimeError(f"SAM returned no usage for phrase {phrase!r}; not caching a partial result")
        cost = _cost_from_usage(used, meta)
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_text(
            json.dumps(
                {
                    "schema": CACHE_SCHEMA, "model": model, "phrase": phrase,
                    "mask_encoding": mask_encoding, "output_text": text,
                    "usage": used, "model_served": served,
                    "created_at": datetime.now(UTC).isoformat(),
                },
                indent=2,
            )
        )
        cache_hit = False

    records = parse_output(text)  # parse only after the raw text is safely cached
    usage.log_call(
        usage.UsageRecord(
            provider=provider, model_requested=model, model_served=served,
            usage=used, cache_hit=cache_hit, cost_usd=cost,
            video_sha256=meta.video_sha256, phrase=phrase,
            extra={"cache_key": key, "n_records": len(records)},
        ),
        path=usage_log,
    )
    return SegmentResult(
        records=records, output_text=text, usage=used, model_served=served,
        cache_hit=cache_hit, cost_usd=cost, cache_key=key, file_id=file_id,
    )
