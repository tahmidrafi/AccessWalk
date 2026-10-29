"""d4-samall phrase test: run candidate noun phrases on chosen clips, then draw
box overlays on the best frames so a human can judge each phrase.

Estimate only (no network, default):
  PYTHONPATH=backend micromamba run -n accesswalk python scripts/sam_phrases.py \
      --clip PXL_..._A --clip PXL_..._B --phrase "raised sidewalk slab" --phrase "sidewalk"
Run (paid; cached, so re-runs are free):   add --run
Overlays only from the cache (no network): add --draw

Overlays go to data/out/phrase_test/<clip>/<phrase>_f<frame>.png (git-ignored),
drawn on frames of the face-blurred sam.mp4.
"""
import argparse
import subprocess
import sys
from pathlib import Path

import cv2
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))
load_dotenv(REPO_ROOT / ".env")

from accesswalk import cache, sam  # noqa: E402
from accesswalk.ingest import DEFAULT_OUT_ROOT, SAM_FPS, IngestMeta, ingest  # noqa: E402
from accesswalk.sam_parse import SamRecord, to_tracks  # noqa: E402

RAW_DIR = REPO_ROOT / "data" / "raw"
OUT_DIR = REPO_ROOT / "data" / "out" / "phrase_test"
COLORS = [(0, 0, 255), (0, 200, 0), (255, 128, 0), (0, 200, 255), (255, 0, 255), (128, 0, 255)]


def _slug(s: str) -> str:
    return s.strip().lower().replace(" ", "_")


def _best_frames(records: list[SamRecord], k: int) -> list[int]:
    """Up to k frames: each track's highest-confidence frame (largest box if no
    confidence), most confident first, at least 1 s apart."""
    picks: list[tuple[float, int]] = []
    for recs in to_tracks(records).values():
        best = max(recs, key=lambda r: (r.box_conf or 0.0, (r.x2 - r.x1) * (r.y2 - r.y1)))
        picks.append((best.box_conf or 0.0, best.frame_index))
    frames: list[int] = []
    for _, f in sorted(picks, reverse=True):
        if all(abs(f - g) >= SAM_FPS for g in frames):
            frames.append(f)
        if len(frames) == k:
            break
    return frames


def draw(meta: IngestMeta, phrase: str, records: list[SamRecord], out_dir: Path, k: int) -> list[Path]:
    sam_mp4 = DEFAULT_OUT_ROOT / meta.video_sha256 / "sam.mp4"
    out_dir.mkdir(parents=True, exist_ok=True)
    by_frame: dict[int, list[SamRecord]] = {}
    for r in records:
        by_frame.setdefault(r.frame_index, []).append(r)
    written = []
    for fi in _best_frames(records, k):
        tmp = out_dir / f"_tmp_{fi}.png"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-v", "error", "-y", "-i", str(sam_mp4),
             "-vf", f"select=eq(n\\,{fi})", "-frames:v", "1", str(tmp)],
            check=True,
        )
        img = cv2.imread(str(tmp))
        tmp.unlink(missing_ok=True)
        for r in by_frame[fi]:
            c = COLORS[r.object_id % len(COLORS)]
            cv2.rectangle(img, (r.x1, r.y1), (r.x2, r.y2), c, 3)
            label = f"#{r.object_id}" + (f" {r.box_conf:.2f}" if r.box_conf is not None else "")
            cv2.putText(img, label, (r.x1 + 4, max(24, r.y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, c, 2)
        banner = f"{phrase} | f{fi} {meta.frame_ms[fi] / 1000:.1f}s"
        cv2.rectangle(img, (0, 0), (img.shape[1], 40), (0, 0, 0), -1)
        cv2.putText(img, banner, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        out = out_dir / f"{_slug(phrase)}_f{fi}.png"
        cv2.imwrite(str(out), img)
        written.append(out)
    return written


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", action="append", required=True, help="raw clip stem (PXL_...)")
    ap.add_argument("--phrase", action="append", required=True)
    ap.add_argument("--run", action="store_true", help="call SAM (paid) for uncached phrases")
    ap.add_argument("--draw", action="store_true", help="draw overlays from cached results")
    ap.add_argument("--frames", type=int, default=3, help="overlay frames per phrase")
    args = ap.parse_args()

    metas = [ingest(RAW_DIR / f"{c}.mp4") for c in args.clip]
    total = 0.0
    for c, m in zip(args.clip, metas, strict=True):
        est = sam.estimate_cost(m.sam.n_frames, len(args.phrase))
        total += est
        print(f"{c}: {m.sam.n_frames} frames x {len(args.phrase)} phrases = ${est:.4f}")
    print(f"estimate (before cache hits): ${total:.4f}")
    if not (args.run or args.draw):
        return 0

    client = sam.make_client() if args.run else None
    spent = 0.0
    for c, m in zip(args.clip, metas, strict=True):
        file_id = None
        for phrase in args.phrase:
            if args.run:
                res = cache.segment_cached(client, m, phrase, file_id=file_id)
                file_id, records, spent = res.file_id, res.records, spent + res.cost_usd
                hit = res.cache_hit
            else:
                res = cache.segment_cached(None, m, phrase, segment_fn=_no_net, upload_fn=_no_net)
                records, hit = res.records, True
            tracks = to_tracks(records)
            confs = [r.box_conf for r in records if r.box_conf is not None]
            mean_c = f"{sum(confs) / len(confs):.2f}" if confs else "-"
            pngs = draw(m, phrase, records, OUT_DIR / c, args.frames) if records else []
            print(f"  {c} | {phrase:<24} records={len(records):4d} tracks={len(tracks):3d} "
                  f"mean_conf={mean_c} cache_hit={hit} overlays={len(pngs)}")
    print(f"spent this run: ${spent:.4f}")
    return 0


def _no_net(*_a, **_k):
    raise SystemExit("not cached; re-run with --run (paid) after approving the estimate")


if __name__ == "__main__":
    sys.exit(main())
