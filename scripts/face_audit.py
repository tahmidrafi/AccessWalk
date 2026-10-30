"""Face-blur audit (d6-blur-fp). Local only: no network, nothing leaves the machine.

  python scripts/face_audit.py dump  PXL_...      # raw YuNet detections -> data/out/face_audit/<clip>.npz
  python scripts/face_audit.py stats PXL_...      # kept/rejected counts + reasons under the current filter
  python scripts/face_audit.py sheet PXL_... [--n 12]
      before/after contact sheet: frames where the blur plan changed, with the old plan
      (every detection) on the left and the filtered plan on the right. Rejected boxes are
      outlined in red and NOT blurred on the right, so check them for real faces.

Outputs are under data/out/ (git-ignored): they contain unblurred source frames.
Run with:  micromamba run -n accesswalk python scripts/face_audit.py ...
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from accesswalk import ingest  # noqa: E402

RAW_DIR = REPO_ROOT / "data" / "raw"
OUT = REPO_ROOT / "data" / "out" / "face_audit"


def dump(clip: str) -> None:
    raw = RAW_DIR / f"{clip}.mp4"
    src = ingest.probe_source(raw)
    w, h = src.display_width, src.display_height
    s = min(1.0, ingest.DETECT_LONG_SIDE / max(w, h))
    dw, dh = round(w * s) & ~1, round(h * s) & ~1
    det = ingest.make_detector(ingest.DEFAULT_MODEL, (dw, dh))
    rows = []
    n = 0
    for n, small in enumerate(ingest._decode(raw, dw, dh), start=1):
        _, faces = det.detect(small)
        if faces is not None:
            for f in faces:
                rows.append([n - 1, *(f[:14] * (w / dw)), f[14], ingest.skin_fraction(small, f)])
    OUT.mkdir(parents=True, exist_ok=True)
    # row: frame, x, y, w, h, 5 landmarks (full-res px), score, skin fraction
    np.savez(OUT / f"{clip}.npz", rows=np.array(rows, np.float32).reshape(-1, 17),
             n_frames=n, w=w, h=h, fps=src.fps)
    print(f"{clip}: {len(rows)} detections on {n} frames")


def _load(clip: str):
    z = np.load(OUT / f"{clip}.npz")
    return z["rows"], int(z["n_frames"]), int(z["w"]), int(z["h"]), float(z["fps"])


def stats(clip: str) -> None:
    rows, n, w, h, fps = _load(clip)
    reasons = Counter(ingest.face_reject_reason(r[1:16], w, h, r[16]) or "kept" for r in rows)
    kept = [r for r in rows if ingest.face_reject_reason(r[1:16], w, h, r[16]) is None]
    big = max((r[3] for r in kept), default=0)
    print(f"{clip}: {len(rows)} dets, {dict(reasons)}; kept on {len({int(r[0]) for r in kept})} frames, "
          f"largest kept {big:.0f}px wide")
    for r in kept:
        print(f"   kept t={r[0] / fps:5.1f}s  {r[3]:4.0f}x{r[4]:<4.0f} at ({r[1]:.0f},{r[2]:.0f}) "
              f"score {r[15]:.2f}")


def _plans(rows, n, w, h, filtered: bool):
    dets: dict[int, list] = {}
    for r in rows:
        if filtered and ingest.face_reject_reason(r[1:16], w, h, r[16]):
            continue
        dets.setdefault(int(r[0]), []).extend(ingest.detections_to_boxes(r[None, 1:16], 1.0, 0.2, w, h))
    return ingest.plan_blur_boxes(dets, n, hold=4, max_gap=30)


def _blur(frame, boxes):
    for x1, y1, x2, y2 in boxes:
        roi = frame[y1:y2, x1:x2]
        if roi.size:
            k = max(15, (min(x2 - x1, y2 - y1) // 2) | 1)
            frame[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (k, k), 0)


def sheet(clip: str, n_show: int) -> None:
    rows, n, w, h, fps = _load(clip)
    before, after = _plans(rows, n, w, h, False), _plans(rows, n, w, h, True)
    changed = [i for i in range(n) if sorted(before.get(i, [])) != sorted(after.get(i, []))]
    rejected = {int(r[0]): [] for r in rows}
    for r in rows:
        if ingest.face_reject_reason(r[1:16], w, h, r[16]):
            rejected[int(r[0])].extend(ingest.detections_to_boxes(r[None, 1:16], 1.0, 0.2, w, h))
    # frames with a rejected detection on them, spread across the clip
    cands = [i for i in changed if rejected.get(i)] or changed
    pick = [cands[round(j * (len(cands) - 1) / max(1, n_show - 1))] for j in range(min(n_show, len(cands)))]
    pick = sorted(set(pick))
    tw = 300
    th = round(h * tw / w)
    tiles = []
    for i, frame in enumerate(ingest._decode(RAW_DIR / f"{clip}.mp4", w, h)):
        if i not in pick:
            continue
        a, b = frame.copy(), frame.copy()
        _blur(a, before.get(i, []))
        _blur(b, after.get(i, []))
        for x1, y1, x2, y2 in rejected.get(i, []):
            cv2.rectangle(b, (x1, y1), (x2, y2), (0, 0, 255), 8)
        gap = np.full((th, 6, 3), 255, np.uint8)
        pair = np.hstack([cv2.resize(a, (tw, th)), gap, cv2.resize(b, (tw, th))])
        cv2.putText(pair, f"{i / fps:.1f}s", (8, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
        tiles.append(pair)
    cols = 3
    blank = np.zeros_like(tiles[0])
    while len(tiles) % cols:
        tiles.append(blank)
    grid = np.vstack([np.hstack([np.pad(t, ((6, 6), (6, 6), (0, 0))) for t in tiles[k:k + cols]])
                      for k in range(0, len(tiles), cols)])
    out = OUT / f"{clip}_sheet.jpg"
    cv2.imwrite(str(out), grid, [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(f"wrote {out.relative_to(REPO_ROOT)}: {len(pick)} frames (of {len(changed)} changed)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["dump", "stats", "sheet"])
    ap.add_argument("clips", nargs="+")
    ap.add_argument("--n", type=int, default=12)
    a = ap.parse_args()
    for c in a.clips:
        {"dump": dump, "stats": stats, "sheet": lambda c: sheet(c, a.n)}[a.cmd](c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
