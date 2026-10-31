"""MapAnything spike, step 2: run the model on the frames from spike_mapanything.py dump.
Runs in its own env (torch + mapanything), on the local GPU or CPU, nothing leaves the machine:

  micromamba run -n mapanything python scripts/spike_mapanything_infer.py data/out/spike [--limit N]

For each frame set: every frame alone (single/<frame>.npz) and, for sets marked multi, all
frames together (multi/<frame>.npz). Done files are skipped. Logs seconds per view.
"""
import argparse
import json
import os
import time
from pathlib import Path

os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

import numpy as np  # noqa: E402
import torch  # noqa: E402
from mapanything.models import MapAnything  # noqa: E402
from mapanything.utils.image import load_images  # noqa: E402


def _save(path: Path, pred: dict) -> None:
    def arr(key):
        return pred[key][0].detach().float().cpu().numpy().squeeze()

    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, pts3d=arr("pts3d").astype(np.float32),
                        pts3d_cam=arr("pts3d_cam").astype(np.float32),
                        conf=arr("conf").astype(np.float32), intrinsics=arr("intrinsics"),
                        pose=arr("camera_poses"), scale=arr("metric_scaling_factor"))


def infer(model, files: list[Path], out: Path) -> float:
    views = load_images([str(f) for f in files])
    start = time.time()
    with torch.no_grad():
        preds = model.infer(views, memory_efficient_inference=True, minibatch_size=1, use_amp=True,
                            amp_dtype="bf16", apply_mask=False, mask_edges=False, apply_confidence_mask=False)
    for f, p in zip(files, preds, strict=True):
        _save(out / f"{f.stem}.npz", p)
    torch.cuda.empty_cache()
    return time.time() - start


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("--limit", type=int, default=0, help="stop after this many frames (smoke test)")
    ap.add_argument("--max-plate-frames", type=int, default=6, help="frames per plate set (CPU is slow)")
    ap.add_argument("--stop-after-min", type=float, default=0, help="start nothing new after this long")
    a = ap.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = MapAnything.from_pretrained("facebook/map-anything-apache").to(device)
    model.eval()
    print("device", device, flush=True)
    log, n, t0 = a.root / "infer_log.jsonl", 0, time.time()

    def out_of_time() -> bool:
        return bool(a.stop_after_min) and time.time() - t0 > a.stop_after_min * 60

    for spec in sorted(a.root.glob("*/set.json")):
        d = spec.parent
        info = json.loads(spec.read_text())
        files = sorted(d.glob("f*.png"))
        if not info.get("multi"):
            files = files[:: max(1, len(files) // a.max_plate_frames)][: a.max_plate_frames]
        for f in files:
            if (d / "single" / f"{f.stem}.npz").exists():
                continue
            if out_of_time():
                print("time limit", flush=True)
                return 0
            s = infer(model, [f], d / "single")
            n += 1
            print(f"{d.name} {f.stem} single {s:.1f} s", flush=True)
            with log.open("a") as g:
                peak = torch.cuda.max_memory_allocated() / 1e9 if device == "cuda" else 0
                g.write(json.dumps({"set": d.name, "frame": f.stem, "mode": "single", "seconds": s,
                                    "peak_gb": peak}) + "\n")
            if a.limit and n >= a.limit:
                return 0
        if info.get("multi") and not (d / "multi" / f"{files[-1].stem}.npz").exists() and not out_of_time():
            try:
                s = infer(model, files, d / "multi")
                print(f"{d.name} multi {len(files)} views {s:.1f} s", flush=True)
                with log.open("a") as g:
                    g.write(json.dumps({"set": d.name, "mode": "multi", "views": len(files),
                                        "seconds": s}) + "\n")
            except torch.cuda.OutOfMemoryError:
                print(f"{d.name} multi OOM", flush=True)
                torch.cuda.empty_cache()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
