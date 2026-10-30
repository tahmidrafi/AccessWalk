"""Plate blur for the published proxy.mp4 (d6-plateblur-proxy).

SAM ``license plate`` tracks come at 5 fps, the proxy runs at source fps, so each
proxy frame's box is interpolated between the track's SAM boxes. A gap of up to
``MAX_GAP_MS`` is bridged; a track's ends (and either side of a longer gap) hold the
nearest box for ``HOLD_MS`` to cover the frames just before SAM picks a plate up.
Padding grows with the plate's own size, plus a floor for small far-away boxes.

``proxy.mp4`` is the only video the API serves. The face-blurred original moves to
``proxy_noplate.mp4`` (never served) so a re-run starts from it instead of blurring
blurred frames; ``proxy_plates.json`` records the plan's hash so an unchanged plan
is not re-encoded.
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path

import cv2

from .ingest import DEFAULT_OUT_ROOT, PROXY_NOPLATE, PROXY_PLATES_JSON, IngestMeta
from .schemas import Track, TrackBox

PAD = 0.2
MIN_PAD_PX = 6
MAX_GAP_MS = 1000
HOLD_MS = 400

Box = tuple[int, int, int, int]


def _pad(x1: float, y1: float, x2: float, y2: float, w: int, h: int, pad: float) -> Box | None:
    px, py = max(MIN_PAD_PX, (x2 - x1) * pad), max(MIN_PAD_PX, (y2 - y1) * pad)
    box = (max(0, int(x1 - px)), max(0, int(y1 - py)), min(w, int(x2 + px) + 1), min(h, int(y2 + py) + 1))
    return box if box[2] > box[0] and box[3] > box[1] else None


def _box_at(boxes: list[TrackBox], t: int, hold_ms: int, max_gap_ms: int) -> tuple[float, ...] | None:
    """The track's box at time ``t``: its own, interpolated, held, or None."""
    if not boxes or t < boxes[0].frame_ms - hold_ms or t > boxes[-1].frame_ms + hold_ms:
        return None
    for a, b in zip(boxes, boxes[1:], strict=False):
        if a.frame_ms <= t <= b.frame_ms:
            gap = b.frame_ms - a.frame_ms
            if gap <= max_gap_ms:
                u = (t - a.frame_ms) / gap if gap else 0.0
                return (a.x1 + u * (b.x1 - a.x1), a.y1 + u * (b.y1 - a.y1),
                        a.x2 + u * (b.x2 - a.x2), a.y2 + u * (b.y2 - a.y2))
            near = a if t - a.frame_ms <= hold_ms else b if b.frame_ms - t <= hold_ms else None
            return (near.x1, near.y1, near.x2, near.y2) if near else None
    end = boxes[0] if t < boxes[0].frame_ms else boxes[-1]
    return (end.x1, end.y1, end.x2, end.y2)


def plate_plan(
    tracks: list[Track], times_ms: list[int], w: int, h: int,
    pad: float = PAD, hold_ms: int = HOLD_MS, max_gap_ms: int = MAX_GAP_MS,
) -> dict[int, list[Box]]:
    """Proxy frame index -> padded boxes to blur."""
    plan: dict[int, list[Box]] = {}
    for t in tracks:
        boxes = sorted(t.boxes, key=lambda b: b.frame_ms)
        for i, ms in enumerate(times_ms):
            at = _box_at(boxes, ms, hold_ms, max_gap_ms)
            box = _pad(*at, w, h, pad) if at else None
            if box:
                plan.setdefault(i, []).append(box)
    return plan


def proxy_times_ms(meta: IngestMeta) -> list[int]:
    """Each proxy frame's time on the clock of ``frame_ms``. ffmpeg's fps filter gives
    SAM frame n the last source frame before (n + 0.5) / SAM_FPS, so it shows the scene
    just under half a SAM frame after its pts (2 frames at 30 fps, measured on 3 clips)."""
    fps = meta.proxy.fps
    late = (math.ceil(fps * 0.5 / meta.sam.fps) - 1) / fps
    return [round((i / fps - late) * 1000) for i in range(meta.proxy.n_frames)]


def blur_proxy(meta: IngestMeta, plate_tracks: list[Track], out_root: str | Path = DEFAULT_OUT_ROOT) -> int:
    """Re-render proxy.mp4 with plates blurred. Returns frames with a plate blur."""
    clip_dir = Path(out_root) / meta.video_sha256
    proxy, source, sidecar = clip_dir / "proxy.mp4", clip_dir / PROXY_NOPLATE, clip_dir / PROXY_PLATES_JSON
    plan = plate_plan(plate_tracks, proxy_times_ms(meta), meta.proxy.width, meta.proxy.height)
    digest = hashlib.sha256(json.dumps(sorted(plan.items())).encode()).hexdigest()[:16]
    if sidecar.exists() and json.loads(sidecar.read_text())["plan"] == digest and proxy.exists():
        return len(plan)
    if not plan and not source.exists():  # nothing to blur, never blurred: leave the proxy alone
        sidecar.write_text(json.dumps({"plan": digest, "frames": 0}))
        return 0
    if not source.exists():
        proxy.replace(source)
    _encode(source, proxy, plan, meta)
    sidecar.write_text(json.dumps({"plan": digest, "frames": len(plan)}))
    return len(plan)


def _encode(source: Path, proxy: Path, plan: dict[int, list[Box]], meta: IngestMeta) -> None:
    w, h = meta.proxy.width, meta.proxy.height
    tmp = proxy.with_suffix(".tmp.mp4")
    cmd = [
        "ffmpeg", "-hide_banner", "-v", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", f"{meta.proxy.fps}", "-i", "-",
        "-i", str(source), "-map", "0:v:0", "-map", "1:a:0?",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-crf", "20",
        "-c:a", "copy", "-movflags", "+faststart", "-map_metadata", "-1", "-map_chapters", "-1",
        str(tmp),
    ]
    log = proxy.with_suffix(".stderr.log")
    cap = cv2.VideoCapture(str(source))
    n = 0
    with log.open("wb") as errf:
        consumer = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=errf)
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                for x1, y1, x2, y2 in plan.get(n, []):
                    k = max(15, (min(x2 - x1, y2 - y1) // 2) | 1)
                    frame[y1:y2, x1:x2] = cv2.GaussianBlur(frame[y1:y2, x1:x2], (k, k), 0)
                consumer.stdin.write(frame.tobytes())
                n += 1
        finally:
            cap.release()
            consumer.stdin.close()
            ret = consumer.wait()
    if ret != 0 or n != meta.proxy.n_frames:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"plate blur of {proxy} failed (exit {ret}, {n}/{meta.proxy.n_frames} frames): "
                           + log.read_text(errors="replace")[-500:])
    log.unlink(missing_ok=True)
    tmp.replace(proxy)
