"""Stage what the Modal deploy (d7-deploy) serves and replays, blurred media only.

  micromamba run -n accesswalk python scripts/deploy_bundle.py PXL_20261029_230808382 \
      --twin data/out/demo/PXL_20261029_230808382.mp4 [--upload]

Per clip, from data/cache/<sha>/ only: meta.json, inventory.json, proxy.mp4 (faces
and plates blurred), proxy_plates.json, frames/*.jpg (faces and plates blurred),
masks/ (PNGs + decoded mask arrays), sam/, llm/, baseline/ and grounded/ (cached model
responses: the two-tier review replays the raw-video pass from baseline/) and the
recheck responses. Never: data/raw, proxy_noplate.mp4 (faces only), sam.mp4 and
recheck clips (plates not blurred), audio.wav, logs. Plus the clip's
report from data/out/reports/<clip>.json.

--twin: a GPS-stripped copy of the clip (ffmpeg -c copy -map_metadata -1), the file
the presenter uploads live. Its cache dir is staged too, so that upload replays
from cache on the server. A cached replay needs no sam.mp4: the SAM cache is keyed
on the sam.mp4 hash in meta.json and every frame it shows is already rendered.

Staged under data/out/deploy_bundle/ (git-ignored, rebuilt each run). --upload then
runs `modal volume put` into the accesswalk-data volume (needs `modal token new`).
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from accesswalk.ingest import DEFAULT_OUT_ROOT, ingest  # noqa: E402

BUNDLE = REPO_ROOT / "data" / "out" / "deploy_bundle"
REPORTS = REPO_ROOT / "data" / "out" / "reports"
VOLUME = "accesswalk-data"
FILES = ["meta.json", "inventory.json", "proxy.mp4", "proxy_plates.json"]
DIRS = {"frames": ("*.jpg", ".plates"), "masks": ("*.png", "*.npy"), "sam": ("*.json",), "llm": ("*.json",),
        "baseline": ("*.json",), "grounded": ("*.json",)}


def stage_clip(sha: str) -> int:
    src, dst = DEFAULT_OUT_ROOT / sha, BUNDLE / "cache" / sha
    n = 0
    for name in FILES:
        if (src / name).exists():
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / name, dst / name)
            n += 1
    for d, patterns in DIRS.items():
        for pat in patterns:
            for f in (src / d).glob(pat):
                (dst / d).mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst / d / f.name)
                n += 1
    for f in (src / "recheck").glob("*/*.json"):  # responses only, not the window clips
        (dst / "recheck" / f.parent.name).mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst / "recheck" / f.parent.name / f.name)
        n += 1
    for bad in ("proxy_noplate.mp4", "sam.mp4", "audio.wav"):
        assert not any(dst.rglob(bad)), bad
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="+", help="clip stems whose report and media are served")
    ap.add_argument("--twin", type=Path, help="GPS-stripped copy of a clip, replayed on upload")
    ap.add_argument("--upload", action="store_true", help="modal volume put the bundle")
    args = ap.parse_args()

    shutil.rmtree(BUNDLE, ignore_errors=True)
    (BUNDLE / "out" / "reports").mkdir(parents=True)
    for clip in args.clips:
        rep = json.loads((REPORTS / f"{clip}.json").read_text(encoding="utf-8"))
        sha = rep["video"]["video_sha256"]
        shutil.copy2(REPORTS / f"{clip}.json", BUNDLE / "out" / "reports" / f"{clip}.json")
        print(f"{clip}: report {rep['report_id']}, {stage_clip(sha)} files from {sha[:12]}")
    if args.twin:
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags:stream_tags",
                                "-of", "json", str(args.twin)], capture_output=True, text=True, check=True)
        if "location" in probe.stdout.lower():
            raise SystemExit(f"{args.twin} still has a location tag: strip it (-map_metadata -1)")
        meta = ingest(args.twin)  # cached: only hashes the file
        print(f"twin {args.twin.name}: {stage_clip(meta.video_sha256)} files from {meta.video_sha256[:12]}")

    size = sum(f.stat().st_size for f in BUNDLE.rglob("*") if f.is_file())
    print(f"staged {BUNDLE.relative_to(REPO_ROOT)}: {size / 1e6:.1f} MB")
    if args.upload:
        for part in ("cache", "out"):
            cmd = ["modal", "volume", "put", "--force", VOLUME, str(BUNDLE / part), f"/{part}"]
            print("$", " ".join(cmd))
            subprocess.run(cmd, check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
