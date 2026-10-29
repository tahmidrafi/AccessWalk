"""d3-samfirst: first real SAM 3.1 run -- one clip, three noun phrases.

Uploads the derived sam.mp4 once, segments "tree root", "trash bin" and
"handrail", caching each response and logging usage. Prints per-phrase results
and the actual-vs-estimated cost.

Run:  PYTHONPATH=backend micromamba run -n accesswalk python scripts/sam_first.py
"""
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))
load_dotenv(REPO_ROOT / ".env")

from accesswalk import cache, sam  # noqa: E402
from accesswalk.ingest import ingest  # noqa: E402
from accesswalk.sam_parse import to_tracks  # noqa: E402

RAW = REPO_ROOT / "data" / "raw" / "PXL_20261027_211833467.mp4"
PHRASES = ["tree root", "trash bin", "handrail"]


def main() -> int:
    meta = ingest(RAW)  # cached: returns existing meta without re-encoding
    print(f"clip {meta.video_sha256[:12]} | sam.mp4 {meta.sam.n_frames} frames "
          f"@ {meta.sam.fps} fps | estimate ${sam.estimate_cost(meta.sam.n_frames, len(PHRASES)):.4f}")

    client = sam.make_client()
    file_id = None
    total = 0.0
    for phrase in PHRASES:
        res = cache.segment_cached(client, meta, phrase, file_id=file_id)
        file_id = res.file_id
        total += res.cost_usd
        tracks = to_tracks(res.records)
        vfp = res.usage.get("video_frames_processed")
        print(f"  {phrase:>10} | records={len(res.records):3d} tracks={len(tracks):2d} "
              f"| frames_billed={vfp} | served={res.model_served} "
              f"| cost=${res.cost_usd:.4f} | cache_hit={res.cache_hit}")

    print(f"total this run: ${total:.4f} (est ${sam.estimate_cost(meta.sam.n_frames, len(PHRASES)):.4f})")
    print(f"frame-alignment check: expected video_frames_processed == {meta.sam.n_frames}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
