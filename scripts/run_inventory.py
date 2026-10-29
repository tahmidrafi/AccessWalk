"""Build inventory.json + keyframe JPEGs for every ingested clip from CACHED SAM
results (no network; a phrase missing from the cache is an error).

Run:  micromamba run -n accesswalk python scripts/run_inventory.py [--clip PXL_...]
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from accesswalk import cache  # noqa: E402
from accesswalk.ingest import ingest  # noqa: E402
from accesswalk.inventory import build_inventory  # noqa: E402
from accesswalk.phrases import SAM_PHRASES  # noqa: E402

RAW_DIR = REPO_ROOT / "data" / "raw"


def _no_net(*_a, **_k):
    raise SystemExit("phrase not cached: run d4-samall (scripts/sam_phrases.py --run) first")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", action="append", help="raw clip stem; default: all of data/raw")
    args = ap.parse_args()
    stems = args.clip or sorted(p.stem for p in RAW_DIR.glob("*.mp4"))
    for stem in stems:
        meta = ingest(RAW_DIR / f"{stem}.mp4")
        records = {
            p: cache.segment_cached(None, meta, p, segment_fn=_no_net, upload_fn=_no_net).records
            for p in SAM_PHRASES
        }
        inv = build_inventory(meta, records)
        by_phrase: dict[str, int] = {}
        for t in inv.kept():
            by_phrase[t.phrase] = by_phrase.get(t.phrase, 0) + 1
        summary = ", ".join(f"{p}={n}" for p, n in sorted(by_phrase.items()))
        print(f"{stem}: {len(inv.tracks)} tracks, {len(inv.kept())} kept "
              f"({len(inv.duplicates)} dup) | {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
