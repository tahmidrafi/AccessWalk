"""Annotation helper (d4-annotate5). No network.

  python scripts/annotate.py new PXL_20261027_213504057   # write a blank template
  python scripts/annotate.py check                        # validate every file + summary

Run with:  micromamba run -n accesswalk python scripts/annotate.py ...
"""
import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from accesswalk.annotations import ANNOTATIONS_DIR, load  # noqa: E402
from accesswalk.ingest import probe_source  # noqa: E402

RAW_DIR = REPO_ROOT / "data" / "raw"


def new(clip: str, annotator: str) -> int:
    out = ANNOTATIONS_DIR / f"{clip}.json"
    if out.exists():
        print(f"{out.name} already exists; not overwriting")
        return 1
    duration = probe_source(RAW_DIR / f"{clip}.mp4").duration_s
    template = {
        "clip": clip,
        "annotator": annotator,
        "status": "draft",
        "duration_s": duration,
        "barriers": [
            {"check": "surface_damage", "t": [0.0, 0.0], "sev": "medium", "note": "", "verify": False}
        ],
        "clean": [[0.0, 0.0]],
        "not_applicable": [],
        "notes": "",
    }
    out.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(REPO_ROOT)} ({duration:.1f} s); replace the placeholder rows")
    return 0


def check() -> int:
    files = sorted(ANNOTATIONS_DIR.glob("*.json"))
    bad = done = 0
    for p in files:
        try:
            a = load(p)
            if a.clip != p.stem:
                raise ValueError(f"clip field {a.clip!r} does not match the file name")
        except Exception as e:  # report every bad file, not only the first
            bad += 1
            print(f"FAIL {p.name}: {e}")
            continue
        done += a.status == "done"
        covered = sum(b.t[1] - b.t[0] for b in a.barriers) + sum(c[1] - c[0] for c in a.clean)
        checks = ", ".join(f"{b.check}({b.sev})" for b in a.barriers) or "none"
        print(f"ok   {p.stem} [{a.status}] {len(a.barriers)} barriers: {checks} | "
              f"labelled {covered / a.duration_s:.0%} of {a.duration_s:.0f} s")
    print(f"{len(files)} files, {done} done, {bad} failing")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("clip")
    n.add_argument("--annotator", default="tahmid")
    sub.add_parser("check")
    args = ap.parse_args()
    return new(args.clip, args.annotator) if args.cmd == "new" else check()


if __name__ == "__main__":
    sys.exit(main())
