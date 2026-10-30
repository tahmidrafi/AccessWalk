"""Re-ingest clips after a blur change without losing SAM results that still apply.

For each clip: force a re-ingest, compare the new sam.mp4 hash with the old one.
  changed    old frames and mask PNGs are deleted (they show the old pixels); SAM
             responses stay on disk under their old keys, where nothing reads them.
  unchanged  cached SAM responses from a meta.json that had no sam_sha256 are copied
             to their new key, so an identical input never pays SAM twice.
No network. Run:  micromamba run -n accesswalk python scripts/reingest.py PXL_... [PXL_...]
"""
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from accesswalk.cache import cache_key  # noqa: E402
from accesswalk.ingest import DEFAULT_OUT_ROOT, IngestMeta, ingest, sha256_file  # noqa: E402

RAW_DIR = REPO_ROOT / "data" / "raw"


def _carry_cache(clip_dir: Path, old: IngestMeta, new: IngestMeta) -> int:
    n = 0
    for p in (clip_dir / "sam").glob("*.json"):
        d = json.loads(p.read_text())
        args = (d["model"], d["phrase"], d["metadata"], new.ingest_version,
                new.sam.fps, new.sam.width, new.sam.height)
        if cache_key(*args, old.sam_sha256) != p.stem:
            continue  # written under other ingest params: not this input
        target = p.with_name(f"{cache_key(*args, new.sam_sha256)}.json")
        if not target.exists():
            shutil.copy2(p, target)
            n += 1
    return n


def reingest(stem: str) -> None:
    raw = RAW_DIR / f"{stem}.mp4"
    meta_path = DEFAULT_OUT_ROOT / sha256_file(raw) / "meta.json"
    old = IngestMeta.model_validate_json(meta_path.read_text()) if meta_path.exists() else None
    clip_dir = meta_path.parent
    old_sam = sha256_file(clip_dir / "sam.mp4") if (clip_dir / "sam.mp4").exists() else None
    new = ingest(raw, force=True)
    changed = old_sam != new.sam_sha256
    carried = 0
    if changed:
        for pattern in ("frames/*.jpg", "masks/*.png"):
            for p in clip_dir.glob(pattern):
                p.unlink()
    elif old is not None:
        carried = _carry_cache(clip_dir, old, new)
    before = f"{old.faces_boxes} boxes" if old else "new"
    print(f"{stem}: sam.mp4 {'CHANGED' if changed else 'identical'} | faces {before} -> "
          f"{new.faces_boxes} kept, {new.faces_rejected} rejected | frames {new.sam.n_frames} | "
          f"cache entries carried {carried}", flush=True)


if __name__ == "__main__":
    for s in sys.argv[1:]:
        reingest(s)
