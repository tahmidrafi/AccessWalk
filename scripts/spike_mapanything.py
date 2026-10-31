"""MapAnything spike (d6-mapanything), steps 1 and 3. Local, no network, cached SAM only.

  micromamba run -n accesswalk python scripts/spike_mapanything.py dump
  micromamba run -n mapanything python scripts/spike_mapanything_infer.py data/out/spike
  micromamba run -n accesswalk python scripts/spike_mapanything.py analyze

No tape measurements exist, so metric scale is checked against objects of known size, and
repeatability against the same surface seen from several frames.

Criteria, fixed before the first inference:
  scale      US license plates (30.5 cm wide): median within +-20 %, at least 5 plates
  width      sidewalk width on one stretch: spread (IQR / median) <= 15 %, and scale passes
  lift       flat-pavement noise (plane-fit residual, robust std, 1-4 m away) <= 1.0 cm,
             since the barrier is a 1.3 cm (1/2 in) level change
  slope      plane normal of one stretch, in the multi-view world frame: spread <= 1.5 deg,
             since the barriers are 4.8 deg (1:12) and 1.2 deg (1:48) cross-slope
A measure that fails is dropped; the spike is a go only if width passes.
Frames come from sam.mp4 (face-blurred) and stay in data/out/spike (git-ignored).
"""
import json
import statistics
import sys
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from accesswalk import cache, masks  # noqa: E402
from accesswalk.ingest import DEFAULT_OUT_ROOT, ingest  # noqa: E402
from accesswalk.inventory import build_tracks, stitch_ids  # noqa: E402

RAW = REPO_ROOT / "data" / "raw"
OUT = REPO_ROOT / "data" / "out" / "spike"
PLATE_W_M = 0.305
PLATE_CLIPS = ["PXL_20261029_231904710", "PXL_20261029_231822465", "PXL_20261029_233500113"]
STRETCH_CLIPS = ["PXL_20261027_211833467", "PXL_20261027_220842365", "PXL_20261027_225049085"]
STRETCH_VIEWS = 8


def _no_net(*_a, **_k):
    raise SystemExit("phrase not cached")


def _records(meta, phrase):
    return stitch_ids(cache.segment_cached(None, meta, phrase, segment_fn=_no_net, upload_fn=_no_net).records)


def _write_frames(meta, name: str, frames: list[int], multi: bool, extra: dict) -> None:
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(DEFAULT_OUT_ROOT / meta.video_sha256 / "sam.mp4"))
    want, i = set(frames), 0
    while want and i <= max(frames):
        ok, img = cap.read()
        if not ok:
            break
        if i in want:
            cv2.imwrite(str(d / f"f{i:04d}.png"), img)
        i += 1
    cap.release()
    (d / "set.json").write_text(json.dumps({"clip": meta.source.filename[:-4], "multi": multi, **extra}))


def dump() -> int:
    for stem in PLATE_CLIPS:
        meta = ingest(RAW / f"{stem}.mp4")
        boxes = {}
        for t in build_tracks("license plate", _records(meta, "license plate"), meta):
            big = sorted(t.boxes, key=lambda b: b.x2 - b.x1, reverse=True)[:2]
            for b in big:
                if b.x2 - b.x1 >= 40:
                    boxes.setdefault(b.frame_index, []).append([t.track_id, b.x1, b.y1, b.x2, b.y2])
        if boxes:
            _write_frames(meta, f"plates_{stem[-9:]}", sorted(boxes), False, {"plates": boxes})
        print(stem, "plate frames", len(boxes))
    for stem in STRETCH_CLIPS:
        meta = ingest(RAW / f"{stem}.mp4")
        have = sorted({r.frame_index for r in _records(meta, "sidewalk") if r.mask})
        # the longest run of frames with a sidewalk mask, sampled evenly
        runs, cur = [], [have[0]]
        for f in have[1:]:
            if f - cur[-1] <= 2:
                cur.append(f)
            else:
                runs.append(cur)
                cur = [f]
        runs.append(cur)
        run = max(runs, key=len)
        run = run[len(run) // 4: len(run) // 4 + 40]  # ~8 s of one stretch: 8 views, 1 s apart
        pick = run[:: max(1, len(run) // STRETCH_VIEWS)][:STRETCH_VIEWS]
        _write_frames(meta, f"stretch_{stem[-9:]}", pick, True, {})
        print(stem, "stretch frames", pick)
    return 0


def _sidewalk_mask(meta, recs, frame: int, w: int, h: int) -> np.ndarray | None:
    cache_dir = DEFAULT_OUT_ROOT / meta.video_sha256 / "masks"
    out = None
    for r in recs:
        if r.frame_index == frame and r.mask:
            raster = masks.decode_raster(r.mask, cache_dir)
            full = cv2.resize(raster, (w, h), interpolation=cv2.INTER_NEAREST).astype(bool)
            out = full if out is None else out | full
    return out


def _plane(p: np.ndarray, iters: int = 4) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Robust plane fit: (normal, centre, residuals of all points, metres)."""
    keep = np.ones(len(p), bool)
    for _ in range(iters):
        c = np.median(p[keep], axis=0)
        n = np.linalg.svd(p[keep] - c, full_matrices=False)[2][2]
        r = (p - c) @ n
        keep = np.abs(r) < max(2.5 * 1.4826 * np.median(np.abs(r[keep])), 1e-4)
    return n, c, r


def _at(pts: np.ndarray, x: float, y: float, sx: float, sy: float) -> np.ndarray:
    """Median 3D point in a 3x3 window at (x, y) in sam.mp4 pixels."""
    h, w = pts.shape[:2]
    u, v = int(np.clip(x * sx, 1, w - 2)), int(np.clip(y * sy, 1, h - 2))
    return np.median(pts[v - 1:v + 2, u - 1:u + 2].reshape(-1, 3), axis=0)


def plates() -> list[float]:
    widths = []
    for d in sorted(OUT.glob("plates_*")):
        info = json.loads((d / "set.json").read_text())
        for frame, rows in info["plates"].items():
            npz = d / "single" / f"f{int(frame):04d}.npz"
            if not npz.exists():
                continue
            pts = np.load(npz)["pts3d_cam"]
            sx, sy = pts.shape[1] / 720, pts.shape[0] / 1280
            for track, x1, y1, x2, y2 in rows:
                inset = 0.1 * (x2 - x1)  # the box overshoots, and edges mix plate and car depth
                mid = (y1 + y2) / 2
                a, b = _at(pts, x1 + inset, mid, sx, sy), _at(pts, x2 - inset, mid, sx, sy)
                measured = float(np.linalg.norm(a - b)) / 0.8  # undo the inset
                widths.append(measured)
                print(f"  {d.name} f{frame} {track}: {x2 - x1} px, {np.linalg.norm((a + b) / 2):.1f} m away, "
                      f"width {measured * 100:.1f} cm")
    return widths


def stretch(d: Path, mode: str) -> dict:
    info = json.loads((d / "set.json").read_text())
    meta = ingest(RAW / f"{info['clip']}.mp4")
    recs = _records(meta, "sidewalk")
    width, noise, normals = [], [], []
    for f in sorted((d / mode).glob("f*.npz")):
        z = np.load(f)
        world, cam = z["pts3d"], z["pts3d_cam"]
        h, w = cam.shape[:2]
        mask = _sidewalk_mask(meta, recs, int(f.stem[1:]), w, h)
        if mask is None:
            continue
        dist = np.linalg.norm(cam, axis=2)
        near = mask & (dist > 1) & (dist < 4)
        if near.sum() < 200:
            continue
        n, _c, r = _plane(cam[near])
        noise.append(1.4826 * float(np.median(np.abs(r - np.median(r)))))
        normals.append(_plane(world[near])[0])
        # width: across the mask on the row nearest 2.5 m, in 3D
        rows = [v for v in range(h) if mask[v].sum() > 5]
        if rows:
            v = min(rows, key=lambda v: abs(np.median(dist[v][mask[v]]) - 2.5))
            us = np.flatnonzero(mask[v])
            if 0 < us[0] and us[-1] < w - 1:  # clipped by the frame edge: not the full width
                width.append(float(np.linalg.norm(cam[v, us[-1]] - cam[v, us[0]])))
    spread = None
    if len(normals) > 1:
        ref = normals[0]
        aligned = [n if n @ ref > 0 else -n for n in normals]
        mean = np.mean(aligned, axis=0)
        mean /= np.linalg.norm(mean)
        spread = float(np.degrees(np.std([np.arccos(np.clip(n @ mean, -1, 1)) for n in aligned])))
    iqr = float(np.subtract(*np.percentile(width, [75, 25]))) if width else None
    return {"set": d.name, "mode": mode, "frames": len(normals), "width_m": [round(x, 2) for x in width],
            "width_spread": round(iqr / statistics.median(width), 3) if width else None,
            "noise_cm": round(statistics.median(noise) * 100, 2) if noise else None,
            "normal_spread_deg": round(spread, 2) if spread is not None else None}


def analyze() -> int:
    ws = plates()
    if ws:
        med = statistics.median(ws)
        print(f"plates: n={len(ws)} median {med * 100:.1f} cm (true 30.5), error {med / PLATE_W_M - 1:+.0%}, "
              f"range {min(ws) * 100:.0f}-{max(ws) * 100:.0f} cm")
    rows = [stretch(d, m) for d in sorted(OUT.glob("stretch_*"))
            for m in ("single", "multi") if (d / m).exists()]
    for r in rows:
        print(r)
    (OUT / "results.json").write_text(json.dumps({"plate_widths_m": ws, "stretches": rows}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit({"dump": dump, "analyze": analyze}[sys.argv[1]]())
