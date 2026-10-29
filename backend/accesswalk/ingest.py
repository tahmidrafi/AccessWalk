"""Ingest a raw phone clip into the derived files the pipeline consumes.

Per CLAUDE.md "Ingest specifics". For each raw clip we produce, under
``data/cache/<sha256>/``:

  * ``sam.mp4``   H.264, 5 fps, 720x1280 (portrait short side 720), no audio -> SAM
  * ``proxy.mp4`` H.264 + AAC, 720x1280, original fps, +faststart  -> report page
  * ``audio.wav`` mono 24 kHz 16-bit PCM                            -> Voice Transcribe
  * ``meta.json`` source specs, frame-index<->ms map for sam.mp4, video hash

Privacy, done locally, before anything leaves the machine:
  * faces are detected on every (autorotated) source frame with OpenCV YuNet,
    padded ~20%, Gaussian-blurred, and the boxes are held a few frames to cover
    detector misses. Every derived video is encoded from the blurred frames, so
    no unblurred face is ever written to a derived file or uploaded.
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

# Bumped whenever the ingest params/filters change; part of the cache key so that
# frame indices (which depend on the re-encode) never silently go stale.
INGEST_VERSION = 1

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


# --------------------------------------------------------------------------- #
# probing
# --------------------------------------------------------------------------- #
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _ffprobe_json(path: Path) -> dict:
    out = subprocess.run(
        [
            "ffprobe", "-hide_banner", "-v", "error",
            "-show_entries",
            "format=duration:stream=index,codec_type,width,height,avg_frame_rate",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(out)


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


def detections_to_boxes(
    faces, inv: float, pad: float, w: int, h: int
) -> list[tuple[int, int, int, int]]:
    """Map YuNet detections (Nx15 on the downscaled frame) to padded, clipped
    full-resolution boxes. ``inv`` scales detection coords back to full res. Pure
    (no OpenCV state) so the scale-back + pad + clip logic can be unit-tested."""
    boxes: list[tuple[int, int, int, int]] = []
    if faces is None:
        return boxes
    for f in faces:
        fx, fy, fw, fh = (v * inv for v in f[:4])
        px, py = fw * pad, fh * pad
        x1 = max(0, int(fx - px))
        y1 = max(0, int(fy - py))
        x2 = min(w, int(fx + fw + px))
        y2 = min(h, int(fy + fh + py))
        if x2 > x1 and y2 > y1:
            boxes.append((x1, y1, x2, y2))
    return boxes


def _blur_faces_stream(
    raw: Path,
    src: SourceMeta,
    detector: cv2.FaceDetectorYN,
    consumer_stdin,
    pad: float,
    hold: int,
) -> tuple[int, int]:
    """Decode autorotated BGR frames, blur faces, write blurred frames to
    ``consumer_stdin``. Returns (frames_with_detection, total_boxes).

    Detection runs on a downscaled copy (``DETECT_LONG_SIDE``) for speed; boxes
    are scaled back to full resolution and padded, so blurring stays full-res.
    """
    w, h = src.display_width, src.display_height
    frame_bytes = w * h * 3
    det_scale = min(1.0, DETECT_LONG_SIDE / max(w, h))
    dw = (round(w * det_scale)) & ~1
    dh = (round(h * det_scale)) & ~1
    detector.setInputSize((dw, dh))
    inv = 1.0 / det_scale

    producer = subprocess.Popen(
        [
            "ffmpeg", "-hide_banner", "-v", "error", "-i", str(raw),
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-",
        ],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )

    held: list[list[int]] = []  # [x1, y1, x2, y2, ttl]
    faces_frames = 0
    faces_boxes = 0
    assert producer.stdout is not None
    try:
        while True:
            buf = producer.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            frame = np.frombuffer(buf, np.uint8).reshape(h, w, 3).copy()

            small = cv2.resize(frame, (dw, dh)) if det_scale < 1.0 else frame
            _, faces = detector.detect(small)
            if faces is not None and len(faces):
                faces_frames += 1
                faces_boxes += len(faces)
                for x1, y1, x2, y2 in detections_to_boxes(faces, inv, pad, w, h):
                    held.append([x1, y1, x2, y2, hold])

            # Blur every held box (current + recently held), then age them.
            for box in held:
                x1, y1, x2, y2, _ = box
                roi = frame[y1:y2, x1:x2]
                if roi.size:
                    k = max(15, (min(x2 - x1, y2 - y1) // 2) | 1)
                    frame[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (k, k), 0)
            held = [[*b[:4], b[4] - 1] for b in held if b[4] - 1 > 0]

            consumer_stdin.write(frame.tobytes())
    finally:
        producer.stdout.close()
        producer.wait()
    return faces_frames, faces_boxes


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
    stderr_log: Path,
) -> tuple[int, int]:
    """Single ffmpeg consumer: blurred BGR frames on stdin -> proxy.mp4 + sam.mp4.
    Audio is pulled from the raw file (input 1). Returns face-detection counts."""
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
            counts = _blur_faces_stream(raw, src, detector, consumer.stdin, pad, hold)
        finally:
            consumer.stdin.close()
            ret = consumer.wait()
    if ret != 0:
        raise RuntimeError(
            f"ffmpeg encode failed (exit {ret}); see {stderr_log}:\n"
            + stderr_log.read_text(errors="replace")[-2000:]
        )
    return counts


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


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
def ingest(
    raw_path: str | Path,
    out_root: str | Path = DEFAULT_OUT_ROOT,
    model_path: str | Path = DEFAULT_MODEL,
    pad: float = 0.2,
    hold: int = 4,
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
            return cached
        # stale ingest: params changed since this clip was processed -> re-ingest
    out_dir.mkdir(parents=True, exist_ok=True)

    src = probe_source(raw)
    # Over-blur rather than miss a face: lower score threshold than the default 0.9.
    detector = cv2.FaceDetectorYN.create(
        str(model), "", (src.display_width, src.display_height),
        score_threshold=0.6, nms_threshold=0.3, top_k=5000,
    )
    faces_frames, faces_boxes = _encode_from_blurred(
        raw, src, out_dir, detector, pad, hold, out_dir / "ffmpeg.stderr.log"
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
        proxy=StreamMeta(width=sw, height=sh, fps=src.fps, n_frames=0),
        frame_ms=frame_ms,
        faces_frames=faces_frames,
        faces_boxes=faces_boxes,
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
