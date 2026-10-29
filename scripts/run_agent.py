"""Run the verification agent on one clip and write its report.

  micromamba run -n accesswalk python scripts/run_agent.py PXL_20261027_211833467 --max-cost 1.0

Writes data/out/reports/<clip>.json (validated Report). Open-weight hosts only
(Baseten, then Fireworks); --allow-closed enables the Muse Spark 1.3 fallback and
marks the report (never for eval or demo runs). Re-runs are free (llm cache).
"""
import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))
load_dotenv(REPO_ROOT / ".env")

from accesswalk import agent  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "out" / "reports"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("clip", help="raw clip stem (PXL_...)")
    ap.add_argument("--max-cost", type=float, required=True, help="stop before exceeding this USD")
    ap.add_argument("--allow-closed", action="store_true", help="allow Muse Spark 1.3 fallback")
    args = ap.parse_args()

    ctx = agent.load_context(args.clip)
    res = agent.run_agent(ctx, allow_closed=args.allow_closed, max_cost_usd=args.max_cost)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{args.clip}.json"
    out.write_text(res.report.model_dump_json(indent=2), encoding="utf-8")

    r = res.report
    print(f"report -> {out.relative_to(REPO_ROOT)}")
    print(f"turns {res.turns}/{agent.MAX_TURNS} | finished {ctx.finished} | hit cap {res.hit_turn_cap} | "
          f"budget stop {res.stopped_for_budget} | cost ${res.cost_usd:.4f}")
    print(f"hosts {r.run.agent_provider} | served {r.run.agent_model} | closed fallback "
          f"{r.run.used_closed_fallback}")
    print(f"tools {res.tool_counts} | views {ctx.views} | rechecks {ctx.rechecks}")
    print(f"verdict {r.verdict.rating}: {r.verdict.summary}")
    for f in r.findings:
        print(f"  {f.finding_id} {f.check_id} {f.severity} conf={f.confidence} {f.track_id} "
              f"f{f.frame_index} ({f.frame_ms / 1000:.1f}s) verify={f.verify_manually} | {f.title}")
        print(f"     {f.evidence_note}")
    for rej in res.rejections:
        print(f"  REJECTED {rej.request.get('check_id')} {rej.request.get('track_id')}: {rej.reason}")
    print("checks: " + ", ".join(f"{c.check_id}={c.status}/{c.n_findings}" for c in r.checks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
