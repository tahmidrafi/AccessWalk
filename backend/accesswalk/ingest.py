"""Ingest a raw phone clip into the derived files the pipeline consumes.

Per CLAUDE.md "Ingest specifics". For each raw clip we produce, under
``data/cache/<sha256>/``:

  * ``sam.mp4``   H.264, 5 fps, 720x1280 (portrait short side 720), no audio -> SAM
  * ``proxy.mp4`` H.264 + AAC, 720x1280, original fps, +faststart  -> report page
  * ``audio.wav`` mono 24 kHz 16-bit PCM                            -> Voice Transcribe
  * ``meta.json`` source specs, frame-index<->ms map for sam.mp4, video hash

Privacy, done locally, before anything leaves the machine:
  * faces are detected on every (autorotated) source frame with OpenCV YuNet
    (pass 1), implausible boxes (wheels, rocks, pavement) are dropped
    (``face_reject_reason``; small boxes are always kept), the rest are
    padded ~20%, held a few frames and bridged across detector gaps of
    up to 1 s (``plan_blur_boxes``), then Gaussian-blurred (pass 2). Every
    derived video is encoded from the blurred frames, so no unblurred face is
    ever written to a derived file or uploaded.
  * all derived files are written with ``-map_metadata -1 -map_chapters -1`` and
    only the video+audio streams are mapped, so the Pixel GPS location tag and
    the extra Pixel data track are dropped.

The original in ``data/raw/`` is never modified.

CLI:  micromamba run -n accesswalk python -m accesswalk.ingest <raw.mp4> [--out DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
from pydantic import BaseModel

# Bumped whenever a change alters frame timing or geometry (fps, size, trimming);
# part of the SAM cache key so frame indices never silently go stale. Blur-only
# changes don't move frames: re-ingest with --force; the new sam.mp4 hash
# (IngestMeta.sam_sha256, also in the key) then makes SAM see a new input.
INGEST_VERSION = 1
PROXY_NOPLATE = "proxy_noplate.mp4"  # plates.py: face-blurred proxy before plate blur; never served
PROXY_PLATES_JSON = "proxy_plates.json"

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = REPO_ROOT / "models" / "face_detection_yunet_2023mar.onnx"
DEFAULT_OUT_ROOT = REPO_ROOT / "data" / "cache"

SAM_FPS = 5
SHORT_SIDE = 720


class SourceMeta(BaseModel):
    filename: str
    coded_width: int
    coded_height: int
    rotation: int
    display_width: int
    display_height: int
    fps: float
    duration_s: float
    has_audio: bool


class StreamMeta(BaseModel):
    width: int
    height: int
    fps: float
    n_frames: int


class IngestMeta(BaseModel):
    video_sha256: str
    ingest_version: int
    created_at: str
    source: SourceMeta
    sam: StreamMeta
    proxy: StreamMeta
    # sam.mp4 frame index -> timestamp in the (re-encoded) clip, milliseconds.
    frame_ms: list[int]
    faces_frames: int  # number of source frames with >=1 detection
    faces_boxes: int  # total detection boxes blurred (before hold)
    # sha256 of the encoded sam.mp4: part of the SAM cache key, so a re-ingest that
    # changes the pixels (e.g. different blur boxes) is a new SAM input. None on
    # clips ingested before this field existed (their cache keys stay as they were).
    sam_sha256: str | None = None
    faces_rejected: int = 0  # detections dropped by the plausibility filter


# --------------------------------------------------------------------------- #
# probing
# --------------------------------------------------------------------------- #
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _ffprobe_json(path: Path, attempts: int = 3) -> dict:
    # Under heavy parallel load ffprobe occasionally returned malformed JSON here
    # (twice in ~30 runs, never reproducible in isolation): retry before failing.
    for i in range(attempts):
        out = subprocess.run(
            [
                "ffprobe", "-hide_banner", "-v", "error",
                "-show_entries",
                "format=duration:stream=index,codec_type,width,height,avg_frame_rate",
                "-of", "json", str(path),
            ],
            capture_output=True, text=True, check=True,
        ).stdout
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            if i == attempts - 1:
                raise
    raise AssertionError("unreachable")


def _video_rotation(path: Path) -> int:
    """Rotation in degrees from the display matrix / rotate tag (e.g. -90)."""
    out = subprocess.run(
        [
            "ffprobe", "-hide_banner", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream_side_data=rotation:stream_tags=rotate",
            "-of", "default=nw=1:nk=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    return int(out[0]) if out else 0


def _parse_fps(rate: str) -> float:
    num, _, den = rate.partition("/")
    den_f = float(den) if den else 1.0
    return float(num) / den_f if den_f else 0.0


def probe_source(path: Path) -> SourceMeta:
    data = _ffprobe_json(path)
    vstreams = [s for s in data["streams"] if s.get("codec_type") == "video"]
    if not vstreams:
        raise ValueError(f"no video stream in {path}")
    v = vstreams[0]
    has_audio = any(s.get("codec_type") == "audio" for s in data["streams"])
    coded_w, coded_h = int(v["width"]), int(v["height"])
    rotation = _video_rotation(path)
    # ffmpeg autorotates on decode: a +/-90 rotation swaps width and height.
    if abs(rotation) % 180 == 90:
        disp_w, disp_h = coded_h, coded_w
    else:
        disp_w, disp_h = coded_w, coded_h
    return SourceMeta(
        filename=path.name,
        coded_width=coded_w,
        coded_height=coded_h,
        rotation=rotation,
        display_width=disp_w,
        display_height=disp_h,
        fps=round(_parse_fps(v.get("avg_frame_rate", "0/1")), 3),
        duration_s=round(float(data["format"]["duration"]), 3),
        has_audio=has_audio,
    )


def _scaled_dims(disp_w: int, disp_h: int, short_side: int) -> tuple[int, int]:
    """Scale so the short side == short_side, both dims even (yuv420p needs even)."""
    if disp_w <= disp_h:
        w = short_side
        h = round(disp_h * short_side / disp_w)
    else:
        h = short_side
        w = round(disp_w * short_side / disp_h)
    return (w - w % 2, h - h % 2)


# --------------------------------------------------------------------------- #
# face blur
# --------------------------------------------------------------------------- #
DETECT_LONG_SIDE = 960  # run YuNet on a frame no larger than this; scale boxes back up
DETECT_SCORE = 0.5


def make_detector(model: str | Path, size: tuple[int, int]) -> cv2.FaceDetectorYN:
    # Over-blur rather than miss a face: far below the default 0.9. At 0.6 a passer-by on
    # the Oct-27 campus clip scored 0.60-0.76 and dropped out for up to 19 frames.
    return cv2.FaceDetectorYN.create(
        str(model), "", size, score_threshold=DETECT_SCORE, nms_threshold=0.3, top_k=5000,
    )


# Plausibility filter (d6-blur-fp). At the low score threshold YuNet fires on car
# wheels, rock beds, barrels, spray paint and whole stretches of pavement, scoring
# up to 0.83 with face-like landmarks; blurring those erases the evidence we film
# for. Audit of all 13 Oct-27/29 clips with detections (scripts/face_audit.py):
# every real face was <= 26 px wide (a passer-by at 15-26 px, 0.51-0.76), every box
# >= 43 px was a false positive. So small boxes are always blurred (cheap, and
# where real distant faces are); a bigger box must look like a face to be blurred.
SMALL_FACE_FRAC = 0.04  # of frame width: below this, always blur
LARGE_FACE_FRAC = 0.15  # at or above this, a close face: demand a high score
MEDIUM_MIN_SCORE = 0.7
LARGE_MIN_SCORE = 0.85
LOW_IN_FRAME = 0.75  # box centre below this fraction of the height = the ground ahead
MIN_SKIN = 0.2  # share of the inner face region with skin chroma


def skin_fraction(frame: np.ndarray, f) -> float:
    """Share of the inner face region (between eyes and chin) whose YCrCb chroma is
    in the skin range (Cr 135-180, Cb 85-135, which spans light to dark skin).
    Grey wheels and pavement score ~0; real faces, but also rocks and leaves, ~1."""
    x, y, bw, bh = f[:4]
    roi = frame[max(0, int(y + 0.25 * bh)):int(y + 0.85 * bh), max(0, int(x + 0.2 * bw)):int(x + 0.8 * bw)]
    if roi.size == 0:
        return 0.0
    ycc = cv2.cvtColor(roi, cv2.COLOR_BGR2YCrCb)
    cr, cb = ycc[..., 1], ycc[..., 2]
    return float(((cr >= 135) & (cr <= 180) & (cb >= 85) & (cb <= 135)).mean())


def face_reject_reason(f, w: int, h: int, skin: float | None = None) -> str | None:
    """Why a YuNet detection ``f`` (x, y, w, h, 5 landmarks, score; in a frame of
    ``w`` x ``h``) is not a plausible face, or None to blur it. ``skin`` is
    ``skin_fraction`` of the box (None skips that test). Pure, so it is unit-tested."""
    x, y, bw, bh = (float(v) for v in f[:4])
    score = float(f[14])
    if bw < SMALL_FACE_FRAC * w:
        return None
    lm = np.asarray(f[4:14], float).reshape(5, 2)  # r eye, l eye, nose, r mouth, l mouth
    eye_y = (lm[0, 1] + lm[1, 1]) / 2
    mouth_y = (lm[3, 1] + lm[4, 1]) / 2
    eye_dist = float(np.hypot(*(lm[1] - lm[0])))
    roll = abs(np.degrees(np.arctan2(lm[1, 1] - lm[0, 1], lm[1, 0] - lm[0, 0])))
    if score < (LARGE_MIN_SCORE if bw >= LARGE_FACE_FRAC * w else MEDIUM_MIN_SCORE):
        return "score"
    if not (0.25 <= eye_dist / bw <= 0.7 and 0.15 <= (eye_y - y) / bh <= 0.6
            and eye_y < lm[2, 1] < mouth_y <= y + 0.95 * bh and roll <= 35):
        return "landmarks"
    if y + bh / 2 > LOW_IN_FRAME * h:
        return "low_in_frame"
    if skin is not None and skin < MIN_SKIN:
        return "not_skin"
    return None


def detections_to_boxes(
    faces, inv: float, pad: float, w: int, h: int, max_frac: float = 0.5
) -> list[tuple[int, int, int, int]]:
    """Map YuNet detections (Nx15 on the downscaled frame) to padded, clipped
    full-resolution boxes. ``inv`` scales detection coords back to full res.
    Detections wider than ``max_frac`` of the frame are dropped: at the low score
    threshold YuNet sometimes boxes most of a sidewalk frame as a "face", and
    blurring that (then bridging it across frames) would erase the evidence. Pure
    (no OpenCV state) so the scale-back + pad + clip logic can be unit-tested."""
    boxes: list[tuple[int, int, int, int]] = []
    if faces is None:
        return boxes
    for f in faces:
        fx, fy, fw, fh = (v * inv for v in f[:4])
        if fw > max_frac * w:
            continue
        px, py = fw * pad, fh * pad
        x1 = max(0, int(fx - px))
        y1 = max(0, int(fy - py))
        x2 = min(w, int(fx + fw + px))
        y2 = min(h, int(fy + fh + py))
        if x2 > x1 and y2 > y1:
            boxes.append((x1, y1, x2, y2))
    return boxes


Box = tuple[int, int, int, int]


def _center_dist(a: Box, b: Box) -> float:
    return (((a[0] + a[2]) - (b[0] + b[2])) ** 2 + ((a[1] + a[3]) - (b[1] + b[3])) ** 2) ** 0.5 / 2


def plan_blur_boxes(
    dets: dict[int, list[Box]], n_frames: int, hold: int, max_gap: int
) -> dict[int, list[Box]]:
    """Which boxes to blur on each frame, given per-frame face detections.

    YuNet misses a small or turned face on many frames (on the Oct-27 campus clip
    a passer-by was detected on 47 of ~140 frames, gaps up to 17 frames). So:
      * every detection is held ``hold`` frames before and after;
      * between two detections <= ``max_gap`` frames apart, each face is matched to
        the nearest face in the earlier detection and the gap frames get the hull
        of both boxes, which covers the path of a face moving between them.
    Over-blurs rather than misses. Pure, so it is unit-tested."""
    plan: dict[int, list[Box]] = {}
    frames = sorted(t for t, b in dets.items() if b)
    for t in frames:
        for k in range(max(0, t - hold), min(n_frames, t + hold + 1)):
            plan.setdefault(k, []).extend(dets[t])
    for t0, t1 in zip(frames, frames[1:], strict=False):
        if not 1 < t1 - t0 <= max_gap:
            continue
        for b1 in dets[t1]:
            b0 = min(dets[t0], key=lambda b: _center_dist(b, b1))
            size = max(b0[2] - b0[0], b0[3] - b0[1], b1[2] - b1[0], b1[3] - b1[1])
            # a walking face can move a fraction of its size per frame, so allow more
            # movement across longer gaps
            if _center_dist(b0, b1) > size * (1 + 0.25 * (t1 - t0)):
                continue  # a different face; the hold above still covers each one
            hull = (min(b0[0], b1[0]), min(b0[1], b1[1]), max(b0[2], b1[2]), max(b0[3], b1[3]))
            for k in range(t0 + 1, t1):
                plan.setdefault(k, []).append(hull)
    return plan


def _decode(raw: Path, w: int, h: int):
    """Yield autorotated BGR frames of ``raw`` scaled to ``w``x``h``."""
    producer = subprocess.Popen(
        [
            "ffmpeg", "-hide_banner", "-v", "error", "-i", str(raw),
            "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-",
        ],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    frame_bytes = w * h * 3
    assert producer.stdout is not None
    try:
        while True:
            buf = producer.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, w, 3).copy()
    finally:
        producer.stdout.close()
        producer.wait()
    # A decode failure would otherwise just look like a short clip.
    if producer.returncode != 0:
        raise RuntimeError(f"ffmpeg decode of {raw.name} failed (exit {producer.returncode})")


def _detect_faces(
    raw: Path, src: SourceMeta, detector: cv2.FaceDetectorYN, pad: float
) -> tuple[dict[int, list[Box]], int, int]:
    """Pass 1: detect on a downscaled decode (``DETECT_LONG_SIDE``), drop implausible
    faces (``face_reject_reason``); kept boxes are scaled back to full resolution and
    padded. Returns (detections, n_frames, n_rejected)."""
    w, h = src.display_width, src.display_height
    det_scale = min(1.0, DETECT_LONG_SIDE / max(w, h))
    dw = (round(w * det_scale)) & ~1
    dh = (round(h * det_scale)) & ~1
    detector.setInputSize((dw, dh))
    dets: dict[int, list[Box]] = {}
    n = rejected = 0
    for n, small in enumerate(_decode(raw, dw, dh), start=1):
        _, faces = detector.detect(small)
        if faces is None or not len(faces):
            continue
        keep = [f for f in faces if face_reject_reason(f, dw, dh, skin_fraction(small, f)) is None]
        rejected += len(faces) - len(keep)
        if keep:
            dets[n - 1] = detections_to_boxes(np.array(keep), w / dw, pad, w, h)
    return dets, n, rejected


def _blur_faces_stream(
    raw: Path, src: SourceMeta, plan: dict[int, list[Box]], consumer_stdin
) -> int:
    """Pass 2: decode full-res frames, blur the planned boxes, write to
    ``consumer_stdin``. Returns frames written."""
    w, h = src.display_width, src.display_height
    n_frames = 0
    for i, frame in enumerate(_decode(raw, w, h)):
        for x1, y1, x2, y2 in plan.get(i, []):
            roi = frame[y1:y2, x1:x2]
            if roi.size:
                k = max(15, (min(x2 - x1, y2 - y1) // 2) | 1)
                frame[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (k, k), 0)
        consumer_stdin.write(frame.tobytes())
        n_frames += 1
    return n_frames


# --------------------------------------------------------------------------- #
# encode
# --------------------------------------------------------------------------- #
def _encode_from_blurred(
    raw: Path,
    src: SourceMeta,
    out_dir: Path,
    detector: cv2.FaceDetectorYN,
    pad: float,
    hold: int,
    max_gap: int,
    stderr_log: Path,
) -> tuple[int, int, int, int]:
    """Single ffmpeg consumer: blurred BGR frames on stdin -> proxy.mp4 + sam.mp4.
    Audio is pulled from the raw file (input 1). Returns (proxy frames, face counts...)."""
    dets, n_src, rejected = _detect_faces(raw, src, detector, pad)
    plan = plan_blur_boxes(dets, n_src, hold, max_gap)
    w, h = src.display_width, src.display_height
    sw, sh = _scaled_dims(w, h, SHORT_SIDE)
    proxy_out = out_dir / "proxy.mp4"
    sam_out = out_dir / "sam.mp4"

    filtergraph = (
        f"[0:v]split=2[a][b];"
        f"[a]scale={sw}:{sh}:flags=bicubic,setsar=1[proxy];"
        f"[b]scale={sw}:{sh}:flags=bicubic,fps={SAM_FPS},setsar=1[sam]"
    )
    cmd = [
        "ffmpeg", "-hide_banner", "-v", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
        "-r", f"{src.fps}", "-i", "-",          # input 0: blurred frames
        "-i", str(raw),                          # input 1: audio source
        "-filter_complex", filtergraph,
        # proxy.mp4
        "-map", "[proxy]", "-map", "1:a:0?",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", "-map_metadata", "-1", "-map_chapters", "-1",
        str(proxy_out),
        # sam.mp4
        "-map", "[sam]", "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
        "-map_metadata", "-1", "-map_chapters", "-1",
        str(sam_out),
    ]
    with stderr_log.open("wb") as errf:
        consumer = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=errf)
        assert consumer.stdin is not None
        try:
            n_written = _blur_faces_stream(raw, src, plan, consumer.stdin)
        finally:
            consumer.stdin.close()
            ret = consumer.wait()
    if ret != 0:
        raise RuntimeError(
            f"ffmpeg encode failed (exit {ret}); see {stderr_log}:\n"
            + stderr_log.read_text(errors="replace")[-2000:]
        )
    return (n_written, sum(1 for b in dets.values() if b), sum(len(b) for b in dets.values()),
            rejected)


def _extract_audio(raw: Path, out_dir: Path, has_audio: bool) -> None:
    """mono 24 kHz 16-bit PCM WAV, metadata stripped."""
    if not has_audio:
        return
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-v", "error", "-y", "-i", str(raw),
            "-vn", "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le",
            "-map", "0:a:0?", "-map_metadata", "-1", "-map_chapters", "-1",
            str(out_dir / "audio.wav"),
        ],
        check=True,
    )


def _frame_ms_table(sam_mp4: Path) -> list[int]:
    """Real per-frame timestamps (ms) read from the encoded sam.mp4 pts."""
    out = subprocess.run(
        [
            "ffprobe", "-hide_banner", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "frame=pts_time", "-of", "csv=p=0", str(sam_mp4),
        ],
        capture_output=True, text=True, check=True,
    ).stdout
    # csv=p=0 can emit a trailing field separator; strip it before parsing.
    toks = (t.strip().rstrip(",") for t in out.replace(",", " ").split())
    return [round(float(t) * 1000) for t in toks if t]


def _count_frames(mp4: Path) -> int:
    out = subprocess.run(
        [
            "ffprobe", "-hide_banner", "-v", "error", "-select_streams", "v:0",
            "-count_packets", "-show_entries", "stream=nb_read_packets",
            "-of", "csv=p=0", str(mp4),
        ],
        capture_output=True, text=True, check=True,
    ).stdout
    return int(out.strip().rstrip(","))


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
def ingest(
    raw_path: str | Path,
    out_root: str | Path = DEFAULT_OUT_ROOT,
    model_path: str | Path = DEFAULT_MODEL,
    pad: float = 0.2,
    hold: int = 4,
    max_gap: int = 30,
    force: bool = False,
) -> IngestMeta:
    raw = Path(raw_path).resolve()
    if not raw.exists():
        raise FileNotFoundError(raw)
    model = Path(model_path)
    if not model.exists():
        raise FileNotFoundError(
            f"YuNet model not found at {model}. Download face_detection_yunet_2023mar.onnx "
            "from the opencv/opencv_zoo LFS media endpoint into models/."
        )

    digest = sha256_file(raw)
    out_dir = Path(out_root) / digest
    meta_path = out_dir / "meta.json"
    if meta_path.exists() and not force:
        cached = IngestMeta.model_validate_json(meta_path.read_text())
        if cached.ingest_version == INGEST_VERSION:
            if cached.proxy.n_frames == 0 and (out_dir / "proxy.mp4").exists():
                cached.proxy.n_frames = _count_frames(out_dir / "proxy.mp4")
                meta_path.write_text(cached.model_dump_json(indent=2))
            return cached
        # stale ingest: params changed since this clip was processed -> re-ingest
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in (PROXY_NOPLATE, PROXY_PLATES_JSON):  # the plate blur restarts from the new proxy
        (out_dir / stale).unlink(missing_ok=True)

    src = probe_source(raw)
    detector = make_detector(model, (src.display_width, src.display_height))
    proxy_frames, faces_frames, faces_boxes, faces_rejected = _encode_from_blurred(
        raw, src, out_dir, detector, pad, hold, max_gap, out_dir / "ffmpeg.stderr.log"
    )
    _extract_audio(raw, out_dir, src.has_audio)

    sam_mp4 = out_dir / "sam.mp4"
    frame_ms = _frame_ms_table(sam_mp4)
    sw, sh = _scaled_dims(src.display_width, src.display_height, SHORT_SIDE)
    meta = IngestMeta(
        video_sha256=digest,
        ingest_version=INGEST_VERSION,
        created_at=datetime.now(UTC).isoformat(),
        source=src,
        sam=StreamMeta(width=sw, height=sh, fps=float(SAM_FPS), n_frames=len(frame_ms)),
        proxy=StreamMeta(width=sw, height=sh, fps=src.fps, n_frames=proxy_frames),
        frame_ms=frame_ms,
        faces_frames=faces_frames,
        faces_boxes=faces_boxes,
        faces_rejected=faces_rejected,
        sam_sha256=sha256_file(sam_mp4),
    )
    meta_path.write_text(meta.model_dump_json(indent=2))
    (out_dir / "ffmpeg.stderr.log").unlink(missing_ok=True)
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ingest a raw clip (blur faces, strip GPS, derive files).")
    ap.add_argument("raw", help="path to the raw .mp4/.mov")
    ap.add_argument("--out", default=str(DEFAULT_OUT_ROOT), help="cache root (default: data/cache)")
    ap.add_argument("--model", default=str(DEFAULT_MODEL))
    ap.add_argument("--force", action="store_true", help="re-ingest even if meta.json exists")
    args = ap.parse_args(argv)
    meta = ingest(args.raw, out_root=args.out, model_path=args.model, force=args.force)
    out_dir = Path(args.out) / meta.video_sha256
    print(f"ingested -> {out_dir}")
    print(f"  source : {meta.source.display_width}x{meta.source.display_height} "
          f"@ {meta.source.fps} fps, {meta.source.duration_s}s, audio={meta.source.has_audio}")
    print(f"  sam    : {meta.sam.width}x{meta.sam.height} @ {meta.sam.fps} fps, "
          f"{meta.sam.n_frames} frames")
    print(f"  faces  : {meta.faces_frames} frames with detections, {meta.faces_boxes} boxes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
