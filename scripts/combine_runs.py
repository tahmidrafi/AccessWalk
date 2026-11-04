"""Combine frozen runs into a new report set with no model calls (eval experiments E4, E7).

  two-tier  --confirmed RUN --possible RUN    every finding of the first run, plus each finding of
            the second that no confirmed finding matches (same check, within 1 s), marked
            "possible" (verify_manually, and the note says it has no SAM track behind it when the
            second run is a raw-video one).
  ensemble  --grounded RUN [RUN...] --other RUN   a finding is kept when at least two systems agree
            on check and time (within 1 s), plus any single-system finding with a valid track
            citation (every finding of a grounded run passed the validator). Agreeing findings are
            merged; the first grounded run's copy is kept.

Writes one report per clip to --out (then scripts/freeze_run.py freezes it). Cost and model
fields are the sum and union of the inputs. Prints counts only.
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from accesswalk.combine import ensemble, two_tier  # noqa: E402
from accesswalk.schemas import Report  # noqa: E402
from accesswalk.scoring import load_reports  # noqa: E402

RUNS = REPO_ROOT / "data" / "out" / "eval_runs"


def _load(run: str) -> dict[str, Report]:
    out: dict[str, Report] = {}
    for part in run.split("+"):
        out |= load_reports(RUNS / part)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["two-tier", "ensemble"])
    ap.add_argument("--name", required=True, help="run id prefix for report ids")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--confirmed")
    ap.add_argument("--possible")
    ap.add_argument("--grounded", nargs="+")
    ap.add_argument("--other")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    if a.mode == "two-tier":
        conf, poss = _load(a.confirmed), _load(a.possible)
        clips = sorted(conf.keys() & poss.keys())
        reports = {c: two_tier(conf[c], poss[c], a.name) for c in clips}
    else:
        gs, other = [_load(g) for g in a.grounded], _load(a.other)
        clips = sorted(set.intersection(*(set(g) for g in gs)) & other.keys())
        reports = {c: ensemble([g[c] for g in gs], other[c], a.name) for c in clips}
    n = 0
    for c, r in reports.items():
        (a.out / f"{c}.json").write_text(r.model_dump_json(indent=2), encoding="utf-8")
        n += len(r.findings)
    print(f"{a.mode}: {len(reports)} clips, {n} findings -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
