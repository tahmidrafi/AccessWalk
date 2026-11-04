"""Single-call grounded review (grounded.py) on many clips, under a total spend cap.
Prints operational stats only, never findings.

  micromamba run -n accesswalk python scripts/run_grounded_batch.py --mode one --out DIR --total 4
  ... --mode many            # several stills per track, up to grounded.MAX_STILLS
  ... --dry-run              # stills per clip and an input-token estimate; no model call
"""
import argparse
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))
load_dotenv(REPO_ROOT / ".env")

from accesswalk import agent, grounded  # noqa: E402

RAW_DIR = REPO_ROOT / "data" / "raw"
MIN_TO_START = 0.20  # one large clip with 100 stills is ~$0.10


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=sorted(grounded.CONFIGS), required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--total", type=float, required=True)
    ap.add_argument("--clip", action="append", help="raw clip stem; default: all of data/raw")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cfg = grounded.CONFIGS[args.mode]
    stems = args.clip or sorted(p.stem for p in RAW_DIR.glob("*.mp4"))
    rows, spent = [], 0.0
    for stem in stems:
        ctx = agent.load_context(stem)
        if args.dry_run:
            n = len(grounded.stills_plan(ctx.inv.kept(), cfg.per_track))
            est = (n * 570 + 12000) * 1.25 / 1e6 + 6000 * 4.25 / 1e6
            spent += est
            print(f"{stem}: {len(ctx.inv.kept())} tracks, {n} stills, ~${est:.3f}")
            continue
        if args.total - spent < MIN_TO_START:
            print(f"{stem}: NOT RUN, ${spent:.4f} of ${args.total} spent", flush=True)
            rows.append({"clip": stem, "error": "not run: total budget reached"})
            continue
        start, row = time.time(), {"clip": stem, "error": None}
        try:
            res = grounded.run_grounded(ctx, cfg)
            args.out.mkdir(parents=True, exist_ok=True)
            (args.out / f"{stem}.json").write_text(res.report.model_dump_json(indent=2), encoding="utf-8")
            spent += res.cost_usd
            row.update(stills=res.n_stills, proposed=res.n_proposed, kept=len(res.report.findings),
                       rejected=len(res.rejections), cost_usd=round(res.cost_usd, 4), cache_hit=res.cache_hit,
                       parsed=ctx.finished)
        except Exception as e:  # one clip must not stop the batch
            row["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        row["seconds"] = round(time.time() - start)
        rows.append(row)
        (args.out.parent / f"{args.out.name}_stats.json").write_text(
            json.dumps({"spent_usd": round(spent, 4), "clips": rows}, indent=2), encoding="utf-8")
        print(f"{stem}: stills {row.get('stills')} proposed {row.get('proposed')} kept {row.get('kept')} "
              f"rejected {row.get('rejected')} parsed {row.get('parsed')} ${row.get('cost_usd', 0):.4f} "
              f"{row['seconds']} s error {row['error']} | running ${spent:.4f}", flush=True)
    print(f"TOTAL ${spent:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
