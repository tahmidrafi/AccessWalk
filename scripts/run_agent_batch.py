"""Run the agent on many clips under hard spend caps. Prints operational stats only,
never findings or verdicts (the owner annotates blind). Stats also go to
data/out/agent_batch.json; reports to data/out/reports/<clip>.json.

  micromamba run -n accesswalk python scripts/run_agent_batch.py --per-clip 0.5 --total 5

Spend is read back from usage.jsonl, so it includes the agent's SAM rechecks, which
run_agent's own budget does not see; RECHECK_MARGIN keeps a clip under its cap anyway.
Open-weight hosts only.
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

from accesswalk import agent, usage  # noqa: E402

RAW_DIR = REPO_ROOT / "data" / "raw"
OUT_DIR = REPO_ROOT / "data" / "out" / "reports"
STATS = REPO_ROOT / "data" / "out" / "agent_batch.json"
RECHECK_MARGIN = 0.10  # two rechecks on a full 50 s clip: 2 x 250 frames x $0.0002
MIN_TO_START = 0.15  # less than one typical clip left: stop


def _usage_since(offset: int) -> tuple[list[dict], int]:
    path = Path(usage.DEFAULT_USAGE_LOG)
    with path.open("rb") as f:
        f.seek(offset)
        raw = f.read()
    return [json.loads(line) for line in raw.splitlines() if line.strip()], offset + len(raw)


def _rejection_kind(reason: str) -> str:
    """Validator reason without its specifics, which can name the object cited."""
    return " ".join(reason.split()[:4]).split("'")[0].strip()


def run_clip(stem: str, cap: float) -> dict:
    path = Path(usage.DEFAULT_USAGE_LOG)
    offset = path.stat().st_size if path.exists() else 0
    start = time.time()
    row: dict = {"clip": stem, "error": None}
    try:
        ctx = agent.load_context(stem)
        res = agent.run_agent(ctx, allow_closed=False, max_cost_usd=max(0.0, cap - RECHECK_MARGIN))
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / f"{stem}.json").write_text(res.report.model_dump_json(indent=2), encoding="utf-8")
        kinds: dict[str, int] = {}
        for rej in res.rejections:
            k = _rejection_kind(rej.reason)
            kinds[k] = kinds.get(k, 0) + 1
        row.update(turns=res.turns, finished=ctx.finished, turn_cap=res.hit_turn_cap,
                   budget_stop=res.stopped_for_budget, hosts=res.providers,
                   models=sorted(set(res.models_served)), closed=res.report.run.used_closed_fallback,
                   rejections=len(res.rejections), rejection_kinds=kinds, tools=res.tool_counts,
                   views=ctx.views, rechecks=ctx.rechecks)
    except Exception as e:  # one clip must not stop the batch
        row["error"] = f"{type(e).__name__}: {str(e)[:300]}"
    calls, _ = _usage_since(offset)
    row["cost_usd"] = round(sum(c.get("cost_usd") or 0.0 for c in calls), 4)
    row["recheck_usd"] = round(sum(c.get("cost_usd") or 0.0 for c in calls
                                   if (c.get("extra") or {}).get("tag") == "recheck"), 4)
    row["failovers"] = [m for c in calls for m in (c.get("extra") or {}).get("failed_before", [])]
    row["seconds"] = round(time.time() - start)
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-clip", type=float, required=True)
    ap.add_argument("--total", type=float, required=True)
    ap.add_argument("--clip", action="append", help="raw clip stem; default: all of data/raw")
    args = ap.parse_args()
    stems = args.clip or sorted(p.stem for p in RAW_DIR.glob("*.mp4"))
    rows, spent = [], 0.0
    for stem in stems:
        left = args.total - spent
        if left < MIN_TO_START:
            rows.append({"clip": stem, "error": "not run: total budget reached", "cost_usd": 0.0})
            print(f"{stem}: NOT RUN, ${spent:.4f} of ${args.total} spent", flush=True)
            continue
        row = run_clip(stem, min(args.per_clip, left))
        spent += row["cost_usd"]
        rows.append(row)
        STATS.write_text(json.dumps({"spent_usd": round(spent, 4), "clips": rows}, indent=2),
                         encoding="utf-8")
        hosts = {h: row.get("hosts", []).count(h) for h in set(row.get("hosts", []))}
        print(f"{stem}: turns {row.get('turns')} finished {row.get('finished')} ${row['cost_usd']:.4f} "
              f"(recheck ${row['recheck_usd']:.4f}) hosts {hosts} rejections {row.get('rejections')} "
              f"{row.get('rejection_kinds') or ''} turn_cap {row.get('turn_cap')} "
              f"budget_stop {row.get('budget_stop')} failovers {len(row['failovers'])} "
              f"{row['seconds']} s error {row['error']} | running ${spent:.4f}", flush=True)
    print(f"TOTAL ${spent:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
