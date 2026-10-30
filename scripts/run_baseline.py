"""Run the raw-video baseline under a spend cap. Prints operational stats only, never a
finding or verdict (the owner annotates blind). Stats also go to data/out/baseline_batch.json.

  micromamba run -n accesswalk python scripts/run_baseline.py --calibrate
  micromamba run -n accesswalk python scripts/run_baseline.py --run baseline-v1 --total 10

--calibrate runs the shortest clip and projects the cost for all 22 from its tokens per second.
A run stops before any clip that could pass --total at the highest cost rate seen so far.
Reports go to data/out/eval_runs/<run>/; a clip already there is not re-run or overwritten.
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

from accesswalk import baseline  # noqa: E402
from accesswalk.ingest import ingest  # noqa: E402
from accesswalk.rules import load_rules  # noqa: E402

RAW_DIR = REPO_ROOT / "data" / "raw"
RUNS = REPO_ROOT / "data" / "out" / "eval_runs"
STATS = REPO_ROOT / "data" / "out" / "baseline_batch.json"


def _clips() -> list:
    return sorted((ingest(p) for p in RAW_DIR.glob("*.mp4")), key=lambda m: m.source.duration_s)


def _tokens(u: dict) -> tuple[int, int]:
    return u.get("input_tokens", 0), u.get("output_tokens", 0)


def calibrate() -> int:
    metas, rules = _clips(), load_rules()
    m = metas[0]
    report, dropped, u = baseline.run_clip(m, rules)
    tin, tout = _tokens(u)
    total_s = sum(x.source.duration_s for x in metas)
    in_per_s = tin / m.source.duration_s
    est = (
        in_per_s * total_s * baseline.PRICE_IN + tout / m.source.duration_s * total_s * baseline.PRICE_OUT
    ) / 1e6
    print(
        f"{m.source.filename}: {m.source.duration_s:.1f} s, input {tin}, output {tout} tokens, "
        f"${report.run.cost_usd:.4f}, dropped {dropped}; served by {report.run.agent_model}"
    )
    print(f"projection: {len(metas)} clips, {total_s:.0f} s, {in_per_s:.0f} input tokens/s -> ${est:.2f}")
    print(f"usage keys: {sorted(u)}")
    return 0


def run(name: str, total: float) -> int:
    run_dir, rules = RUNS / name, load_rules()
    run_dir.mkdir(parents=True, exist_ok=True)
    metas = _clips()
    rows, spent, worst_rate = [], 0.0, 0.0
    for m in metas:
        stem = m.source.filename.rsplit(".", 1)[0]
        out = run_dir / f"{stem}.json"
        if out.exists():
            print(f"{stem}: already in {name}, skipped", flush=True)
            continue
        if spent + worst_rate * m.source.duration_s > total:
            print(f"{stem}: NOT RUN, ${spent:.4f} spent, next could pass ${total}", flush=True)
            rows.append({"clip": stem, "error": "not run: budget"})
            continue
        start = time.time()
        row = {"clip": stem, "error": None, "seconds_of_video": m.source.duration_s}
        try:
            report, dropped, u = baseline.run_clip(m, rules)
            out.write_text(report.model_dump_json(indent=2), encoding="utf-8")
            row.update(
                cost_usd=report.run.cost_usd, dropped=dropped, tokens=_tokens(u), model=report.run.agent_model
            )
            spent += report.run.cost_usd
            worst_rate = max(worst_rate, report.run.cost_usd / m.source.duration_s)
        except Exception as e:  # one clip must not stop the batch
            row["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        row["seconds"] = round(time.time() - start)
        rows.append(row)
        STATS.write_text(
            json.dumps({"run": name, "spent_usd": round(spent, 4), "clips": rows}, indent=2), encoding="utf-8"
        )
        print(
            f"{stem}: ${row.get('cost_usd', 0):.4f} tokens {row.get('tokens')} dropped {row.get('dropped')} "
            f"{row['seconds']} s error {row['error']} | running ${spent:.4f}",
            flush=True,
        )
    print(f"TOTAL ${spent:.4f}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--run")
    ap.add_argument("--total", type=float, default=10.0)
    a = ap.parse_args()
    return calibrate() if a.calibrate else run(a.run, a.total)


if __name__ == "__main__":
    sys.exit(main())
