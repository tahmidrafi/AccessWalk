"""Run the agent on many clips under hard spend caps. Prints operational stats only,
never findings or verdicts (the owner annotates blind). Stats also go to
data/out/agent_batch.json; reports to data/out/reports/<clip>.json.

  micromamba run -n accesswalk python scripts/run_agent_batch.py --per-clip 0.5 --total 5
  ... --out data/out/reports_v2 --clip PXL_...   # an eval run: keeps data/out/reports
                                                 # (the pinned sample report) untouched
  ... --proposer open          # hybrid: Muse Spark Open on Baseten proposes from the video;
                               # its own findings go to <out>_proposer/ for scoring
  ... --proposer run:baseline-v1   # hybrid with a frozen run's findings as proposals ($0 extra)

Spend per clip is the agent's calls plus its SAM rechecks (which run_agent's own budget
does not see; RECHECK_MARGIN keeps a clip under its cap anyway) plus a live proposer.
--agent picks the config: "open" (default, Baseten, open-weight) or a Muse Spark 1.3 one.
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

from accesswalk import agent, hybrid, usage  # noqa: E402

RAW_DIR = REPO_ROOT / "data" / "raw"
OUT_DIR = REPO_ROOT / "data" / "out" / "reports"
STATS = REPO_ROOT / "data" / "out" / "agent_batch.json"
RECHECK_MARGIN = 0.10  # two rechecks on a full 50 s clip: 2 x 250 frames x $0.0002
MIN_TO_START = 0.15  # less than one typical clip left: stop


def _rejection_kind(reason: str) -> str:
    """Validator reason without its specifics, which can name the object cited."""
    return " ".join(reason.split()[:4]).split("'")[0].strip()


EVAL_RUNS = REPO_ROOT / "data" / "out" / "eval_runs"


def _propose(ctx, proposer: str, out_dir: Path) -> float:
    """Hybrid runs: give ``ctx`` its proposals before the agent starts. Returns the
    proposer's cost (0 for a frozen run's findings)."""
    cost = 0.0
    if proposer == "open":
        props, who, rep, cost = hybrid.propose_open(ctx.meta, ctx.rules)
        pdir = out_dir.with_name(out_dir.name + "_proposer")
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / f"{ctx.meta.source.filename.rsplit('.', 1)[0]}.json").write_text(
            rep.model_dump_json(indent=2), encoding="utf-8")
    else:
        run = proposer.removeprefix("run:")
        stem = ctx.meta.source.filename.rsplit('.', 1)[0]
        rep = agent.Report.model_validate_json(
            (EVAL_RUNS / run / f"{stem}.json").read_text(encoding="utf-8"))
        props, who = hybrid.proposals_from_report(rep, ctx.meta), hybrid.proposer_of(rep, f"frozen run {run}")
    ctx.proposals, ctx.proposer = props, who
    return cost


def run_clip(stem: str, cap: float, out_dir: Path = OUT_DIR, proposer: str | None = None,
             config: str = "open") -> dict:
    """Costs come from this run's own results (agent calls, SAM rechecks, proposer), not
    from usage.jsonl, so several batches can run at once without mixing their spend."""
    start = time.time()
    row: dict = {"clip": stem, "error": None, "config": config}
    agent_usd = recheck_usd = proposer_usd = 0.0
    ctx = None
    try:
        ctx = agent.load_context(stem)
        ctx.config = agent.CONFIGS[config]
        if proposer:
            proposer_usd = _propose(ctx, proposer, out_dir)
        res = agent.run_agent(ctx, max_cost_usd=max(0.0, cap - proposer_usd - RECHECK_MARGIN))
        agent_usd = res.cost_usd
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{stem}.json").write_text(res.report.model_dump_json(indent=2), encoding="utf-8")
        kinds: dict[str, int] = {}
        for rej in res.rejections:
            k = _rejection_kind(rej.reason)
            kinds[k] = kinds.get(k, 0) + 1
        row.update(turns=res.turns, finished=ctx.finished, turn_cap=res.hit_turn_cap,
                   budget_stop=res.stopped_for_budget, hosts=res.providers,
                   models=sorted(set(res.models_served)), closed=res.report.run.used_closed_fallback,
                   rejections=len(res.rejections), rejection_kinds=kinds, tools=res.tool_counts,
                   views=ctx.views, rechecks=ctx.rechecks, proposals=len(ctx.proposals),
                   verdicts=[v["verdict"] for v in ctx.proposal_verdicts.values()])
    except Exception as e:  # one clip must not stop the batch
        row["error"] = f"{type(e).__name__}: {str(e)[:300]}"
    recheck_usd = ctx.recheck_usd if ctx is not None else 0.0
    row["cost_usd"] = round(agent_usd + recheck_usd + proposer_usd, 4)
    row["recheck_usd"] = round(recheck_usd, 4)
    row["proposer_usd"] = round(proposer_usd, 4)
    row["seconds"] = round(time.time() - start)
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-clip", type=float, required=True)
    ap.add_argument("--total", type=float, required=True)
    ap.add_argument("--clip", action="append", help="raw clip stem; default: all of data/raw")
    ap.add_argument("--out", type=Path, default=OUT_DIR, help="report directory")
    ap.add_argument("--stats", type=Path, default=STATS)
    ap.add_argument("--proposer", help="open | run:<frozen run>: hybrid proposals (default: none)")
    ap.add_argument("--agent", default="open", choices=sorted(agent.CONFIGS),
                    help="agent config: open (v2, Baseten), spark13, spark13-deep")
    args = ap.parse_args()
    stems = args.clip or sorted(p.stem for p in RAW_DIR.glob("*.mp4"))
    rows, spent = [], 0.0
    for stem in stems:
        left = args.total - spent
        if left < MIN_TO_START:
            rows.append({"clip": stem, "error": "not run: total budget reached", "cost_usd": 0.0})
            print(f"{stem}: NOT RUN, ${spent:.4f} of ${args.total} spent", flush=True)
            continue
        row = run_clip(stem, min(args.per_clip, left), args.out, args.proposer, args.agent)
        spent += row["cost_usd"]
        rows.append(row)
        args.stats.write_text(json.dumps({"spent_usd": round(spent, 4), "clips": rows}, indent=2),
                         encoding="utf-8")
        hosts = {h: row.get("hosts", []).count(h) for h in set(row.get("hosts", []))}
        print(f"{stem}: turns {row.get('turns')} finished {row.get('finished')} ${row['cost_usd']:.4f} "
              f"(recheck ${row['recheck_usd']:.4f}) hosts {hosts} rejections {row.get('rejections')} "
              f"{row.get('rejection_kinds') or ''} turn_cap {row.get('turn_cap')} "
              f"budget_stop {row.get('budget_stop')} "
              f"proposals {row.get('proposals')} {row.get('verdicts') or ''} "
              f"{row['seconds']} s error {row['error']} | running ${spent:.4f}", flush=True)
    print(f"TOTAL ${spent:.4f} | Baseten to date ${usage.provider_spend('baseten'):.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
