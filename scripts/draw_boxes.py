"""Draw a phrase's SAM boxes onto the matching sam.mp4 frame (M2 eyeball check).

Because we upload sam.mp4 itself, the box coordinates come back in sam.mp4 pixel
space, so they map 1:1 onto a frame extracted from sam.mp4 (no scaling). The box
``w``/``h`` reported on each record should therefore equal the sam.mp4 dimensions;
this script asserts that, which is the real test of the coordinate-space
assumption.

Run:  PYTHONPATH=backend micromamba run -n accesswalk python scripts/draw_boxes.py "tree root"
"""
import subprocess
import sys
from pathlib import Path

import cv2

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from accesswalk import cache  # noqa: E402
from accesswalk.ingest import DEFAULT_OUT_ROOT, ingest  # noqa: E402
from accesswalk.sam import MODEL  # noqa: E402
from accesswalk.sam_parse import parse_output, to_tracks  # noqa: E402

RAW = REPO_ROOT / "data" / "raw" / "PXL_20261027_211833467.mp4"


def main(phrase: str, mask_encoding: str = "one_bit", include_confidence: bool = True) -> int:
    meta = ingest(RAW)
    request_metadata = {
        "mask_encoding": mask_encoding,
        "include_confidence": "true" if include_confidence else "false",
    }
    key = cache.cache_key(
        MODEL, phrase, request_metadata,
        meta.ingest_version, meta.sam.fps, meta.sam.width, meta.sam.height, meta.sam_sha256,
    )
    cpath = cache.cache_path(DEFAULT_OUT_ROOT, meta.video_sha256, key)
    if not cpath.exists():
        print(f"no cached response for {phrase!r} at {cpath}")
        return 1

    import json
    text = json.loads(cpath.read_text())["output_text"]
    records = parse_output(text)
    if not records:
        print(f"{phrase!r}: zero matches (valid result) -- nothing to draw")
        return 0

    # coordinate-space check: box w/h should equal the uploaded sam.mp4 dims
    sample = records[0]
    print(f"{phrase!r}: {len(records)} records, {len(to_tracks(records))} tracks; "
          f"box frame dims = {sample.frame_w}x{sample.frame_h}, sam.mp4 = {meta.sam.width}x{meta.sam.height}")
    if (sample.frame_w, sample.frame_h) != (meta.sam.width, meta.sam.height):
        print("  WARNING: box coord space != sam.mp4 dims -- scaling assumption is wrong!")

    # pick the frame with the most boxes
    by_frame: dict[int, list] = {}
    for r in records:
        by_frame.setdefault(r.frame_index, []).append(r)
    frame_index = max(by_frame, key=lambda f: len(by_frame[f]))
    sam_mp4 = DEFAULT_OUT_ROOT / meta.video_sha256 / "sam.mp4"

    out_dir = REPO_ROOT / "data" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    frame_png = out_dir / f"_frame_{frame_index}.png"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-v", "error", "-y", "-i", str(sam_mp4),
         "-vf", f"select=eq(n\\,{frame_index})", "-frames:v", "1", str(frame_png)],
        check=True,
    )
    img = cv2.imread(str(frame_png))
    for r in by_frame[frame_index]:
        cv2.rectangle(img, (r.x1, r.y1), (r.x2, r.y2), (0, 0, 255), 3)
        label = f"#{r.object_id}" + (f" {r.box_conf:.2f}" if r.box_conf is not None else "")
        cv2.putText(img, label, (r.x1, max(0, r.y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    out_png = out_dir / f"boxes_{phrase.replace(' ', '_')}_f{frame_index}.png"
    cv2.imwrite(str(out_png), img)
    frame_png.unlink(missing_ok=True)
    print(f"wrote {out_png} (frame {frame_index}, {len(by_frame[frame_index])} boxes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "tree root"))
