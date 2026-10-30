"""Freeze a set of agent reports as a named eval run. No network.

  micromamba run -n accesswalk python scripts/freeze_run.py v1 [--source data/out/reports]
  micromamba run -n accesswalk python scripts/freeze_run.py v1 --verify

Copies the reports to data/out/eval_runs/<name>/ (git-ignored), marks them read-only and
commits only a manifest, eval/runs/<name>.json: file hashes and provenance, no findings.
An existing run is never overwritten.
"""

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = REPO_ROOT / "data" / "out" / "eval_runs"
MANIFESTS = REPO_ROOT / "eval" / "runs"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def freeze(name: str, source: Path) -> int:
    manifest, run_dir = MANIFESTS / f"{name}.json", RUNS_DIR / name
    if manifest.exists():
        print(f"{manifest.name} exists: run {name} is frozen, not overwriting")
        return 1
    run_dir.mkdir(parents=True, exist_ok=True)
    clips = {}
    for src in sorted(source.glob("PXL_*.json")):
        dst = run_dir / src.name
        if dst.exists() and _sha(dst) != _sha(src):
            print(f"{dst} differs from {src}: refusing")
            return 1
        if not dst.exists():
            shutil.copy2(src, dst)
        os.chmod(dst, stat.S_IREAD)
        run = json.loads(dst.read_text(encoding="utf-8"))["run"]
        clips[src.stem] = {
            "sha256": _sha(dst),
            "created_at": run["created_at"],
            "provider": run["agent_provider"],
            "model": run["agent_model"],
            "cost_usd": run["cost_usd"],
            "closed_fallback": run["used_closed_fallback"],
        }
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"run": name, "n_clips": len(clips), "clips": clips}, indent=2) + "\n")
    print(f"froze {len(clips)} reports as {name}: {run_dir}")
    return 0


def verify(name: str) -> int:
    clips = json.loads((MANIFESTS / f"{name}.json").read_text())["clips"]
    bad = [c for c, d in clips.items() if _sha(RUNS_DIR / name / f"{c}.json") != d["sha256"]]
    print(f"{name}: {len(clips) - len(bad)}/{len(clips)} reports match the manifest {bad or ''}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--source", type=Path, default=REPO_ROOT / "data" / "out" / "reports")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    return verify(a.name) if a.verify else freeze(a.name, a.source)


if __name__ == "__main__":
    sys.exit(main())
