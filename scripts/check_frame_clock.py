"""Check frame_ms against the pixels: for sampled SAM frames, which proxy frame looks most
like it, and how far is that from where frame_ms says? Local only, no network.

  micromamba run -n accesswalk python scripts/check_frame_clock.py PXL_... [PXL_...]

Prints the median and worst error in proxy frames (0 = frame_ms lands on the same scene).
Plate-blur patches differ between the videos but are too small to move the best match.
"""
import statistics
import sys
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from accesswalk.ingest import DEFAULT_OUT_ROOT, ingest  # noqa: E402

RAW_DIR = REPO_ROOT / "data" / "raw"
SEARCH = 6  # proxy frames either side
EVERY = 5  # SAM frames between samples


def _frames(path: Path) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(path))
    out = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        out.append(cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (180, 320)).astype(np.int16))
    cap.release()
    return out


def check(stem: str) -> None:
    meta = ingest(RAW_DIR / f"{stem}.mp4")
    clip = DEFAULT_OUT_ROOT / meta.video_sha256
    sam, proxy = _frames(clip / "sam.mp4"), _frames(clip / "proxy.mp4")
    errors = []
    for i in range(1, len(sam) - 1, EVERY):
        want = round(meta.frame_ms[i] * meta.proxy.fps / 1000)
        lo, hi = max(0, want - SEARCH), min(len(proxy) - 1, want + SEARCH)
        diffs = [np.abs(proxy[j] - sam[i]).mean() for j in range(lo, hi + 1)]
        errors.append(lo + int(np.argmin(diffs)) - want)
    print(f"{stem}: {meta.proxy.fps:.2f} fps, clock {meta.frame_ms_clock}, {len(errors)} samples, "
          f"median error {statistics.median(errors):+.1f} proxy frames, worst "
          f"{max(errors, key=abs):+d}, exact {sum(e == 0 for e in errors) / len(errors):.0%}")


if __name__ == "__main__":
    for s in sys.argv[1:]:
        check(s)
