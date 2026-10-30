"""Check plate blur on the published proxy.mp4. Local only, no network, cached SAM only.

For each clip: apply the plate blur, then crop the blurred proxy around every near car
(box at least --min-car of the frame width) at frames between SAM samples, where
interpolation is doing the work. An unblurred plate in a crop is a miss.

  micromamba run -n accesswalk python scripts/plate_audit.py PXL_... [PXL_...]

Sheets: data/out/plate_audit/<clip>.jpg (git-ignored).
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from accesswalk import cache, plates  # noqa: E402
from accesswalk.ingest import DEFAULT_OUT_ROOT, ingest  # noqa: E402
from accesswalk.inventory import build_tracks, stitch_ids  # noqa: E402
from accesswalk.phrases import PLATE_PHRASE  # noqa: E402

RAW_DIR = REPO_ROOT / "data" / "raw"
OUT = REPO_ROOT / "data" / "out" / "plate_audit"


def _no_net(*_a, **_k):
    raise SystemExit("phrase not cached")


def _tracks(meta, phrase):
    recs = cache.segment_cached(None, meta, phrase, segment_fn=_no_net, upload_fn=_no_net).records
    return build_tracks(phrase, stitch_ids(recs), meta)


def audit(stem: str, min_car: float, per_car: int, tile: int) -> None:
    meta = ingest(RAW_DIR / f"{stem}.mp4")
    w = meta.proxy.width
    plate_tracks = _tracks(meta, PLATE_PHRASE)
    n_blur = plates.blur_proxy(meta, plate_tracks)
    plan = plates.plate_plan(plate_tracks, plates.proxy_times_ms(meta), w, meta.proxy.height)
    fps = meta.proxy.fps

    # (proxy frame, crop box, label) for each near car, spread over where it is largest
    wanted: dict[int, list] = {}
    for t in _tracks(meta, "car"):
        near = [b for b in t.boxes if (b.x2 - b.x1) >= min_car * w]
        if not near:
            continue
        step = max(1, len(near) // per_car)
        for b in near[::step][:per_car]:
            i = round((b.frame_ms + 100) * fps / 1000)  # halfway to the next SAM frame
            if i < meta.proxy.n_frames:
                wanted.setdefault(i, []).append((b, f"{t.track_id} {i / fps:.1f}s"))

    tiles = []
    cap = cv2.VideoCapture(str(DEFAULT_OUT_ROOT / meta.video_sha256 / "proxy.mp4"))
    i = 0
    while wanted and i <= max(wanted):
        ok, frame = cap.read()
        if not ok:
            break
        for b, label in wanted.get(i, []):
            crop = frame[max(0, b.y1):b.y2, max(0, b.x1):b.x2]
            scale = tile / max(crop.shape[:2])
            crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            canvas = np.zeros((tile, tile, 3), np.uint8)
            canvas[:crop.shape[0], :crop.shape[1]] = crop
            state = "blur" if i in plan else "none"
            cv2.putText(canvas, f"{label} {state}", (6, tile - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (0, 255, 255), 1)
            tiles.append(canvas)
        i += 1
    cap.release()

    print(f"{stem}: {len(plate_tracks)} plate tracks, {n_blur}/{meta.proxy.n_frames} proxy frames blurred, "
          f"{len(tiles)} near-car crops")
    if tiles:
        cols = 6
        tiles += [np.zeros_like(tiles[0])] * (-len(tiles) % cols)
        OUT.mkdir(parents=True, exist_ok=True)
        grid = np.vstack([np.hstack(tiles[k:k + cols]) for k in range(0, len(tiles), cols)])
        cv2.imwrite(str(OUT / f"{stem}.jpg"), grid, [cv2.IMWRITE_JPEG_QUALITY, 88])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="+")
    ap.add_argument("--min-car", type=float, default=0.2)
    ap.add_argument("--per-car", type=int, default=3)
    ap.add_argument("--tile", type=int, default=280)
    a = ap.parse_args()
    for c in a.clips:
        audit(c, a.min_car, a.per_car, a.tile)
    return 0


if __name__ == "__main__":
    sys.exit(main())
