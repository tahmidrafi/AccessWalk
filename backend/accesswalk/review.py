"""The review stage of the upload pipeline: what turns a clip's tracked inventory into findings.

Each reviewer takes the agent context (meta, inventory, SAM records, rules) and returns the
report plus the new spend (cache hits are free). They are the systems the eval compares
(eval/runs/*.json, README "Evaluation"); ``jobs.real_pipeline`` runs ``DEFAULT_REVIEW``
unless ``ACCESSWALK_REVIEW`` names another.

  open            v2: the agent on Muse Spark Open (Baseten, Fireworks failover), open weights
  spark13         the same agent, tools, rules and validator on Muse Spark 1.3
  spark13-deep    spark13 with 24 frame views and "recheck with SAM before rejecting"
  hybrid-open     v3: Muse Spark Open watches the clip and proposes; the open agent verifies
  hybrid-spark13  Muse Spark 1.3 watches the clip and proposes; the spark13 agent verifies
  grounded-one    one Muse Spark 1.3 call: video + track inventory + a still per track
  grounded-many   the same with several stills per track
  two-tier        spark13 findings, plus raw-video findings it did not make, as "possible"
  ensemble        spark13 + grounded-one + raw video: agreement, or any grounded finding
"""
from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from . import baseline, combine, grounded, hybrid
from .agent import CONFIGS, AgentContext, run_agent
from .ingest import DEFAULT_OUT_ROOT
from .schemas import Report

DEFAULT_REVIEW = "open"

Review = Callable[[AgentContext, Path, float], tuple[Report, float]]


def _agent(ctx: AgentContext, config: str, budget: float) -> tuple[Report, float]:
    ctx.config = CONFIGS[config]
    res = run_agent(ctx, max_cost_usd=budget)
    return res.report, res.cost_usd + ctx.recheck_spend_usd


def _raw(ctx: AgentContext, out_root: Path) -> tuple[Report, float]:
    """Muse Spark 1.3 on the blurred proxy.mp4, no tracks (baseline.py), cached per clip."""
    cached = baseline.cache_path(ctx.meta, ctx.rules, out_root).exists()
    report, _, _ = baseline.run_clip(ctx.meta, ctx.rules, out_root=out_root)
    return report, 0.0 if cached else report.run.cost_usd  # the report shows the call's cost


def _keep_id(combined: Report, base: Report) -> Report:
    return combined.model_copy(update={"report_id": base.report_id})


def review_open(ctx, out_root, budget):
    return _agent(ctx, "open", budget)


def review_spark13(ctx, out_root, budget):
    return _agent(ctx, "spark13", budget)


def review_spark13_deep(ctx, out_root, budget):
    return _agent(ctx, "spark13-deep", budget)


def review_hybrid(ctx, out_root, budget):
    raw, spent = _raw(ctx, out_root)
    ctx.proposals = hybrid.proposals_from_report(raw, ctx.meta)
    ctx.proposer = hybrid.proposer_of(raw, "live raw-video pass")
    report, more = _agent(ctx, "spark13", max(0.0, budget - spent))
    return report, spent + more


def review_hybrid_open(ctx, out_root, budget):
    """v3: Muse Spark Open watches proposer.mp4 and proposes; the open agent verifies."""
    ctx.proposals, ctx.proposer, _, spent = hybrid.propose_open(ctx.meta, ctx.rules, out_root)
    report, more = _agent(ctx, "open", max(0.0, budget - spent))
    return report, spent + more


def _grounded(ctx, out_root, mode):
    res = grounded.run_grounded(ctx, grounded.CONFIGS[mode], out_root)
    return res.report, res.cost_usd


def review_grounded_one(ctx, out_root, budget):
    return _grounded(ctx, out_root, "one")


def review_grounded_many(ctx, out_root, budget):
    return _grounded(ctx, out_root, "many")


def review_two_tier(ctx, out_root, budget):
    raw, spent = _raw(ctx, out_root)
    report, more = _agent(ctx, "spark13", max(0.0, budget - spent))
    return _keep_id(combine.two_tier(report, raw, "two-tier"), report), spent + more


def review_ensemble(ctx, out_root, budget):
    raw, spent = _raw(ctx, out_root)
    g_ctx = AgentContext(meta=ctx.meta, inv=ctx.inv.model_copy(deep=True), records=ctx.records,
                         rules=ctx.rules, plate_tracks=ctx.plate_tracks)
    g, g_spent = _grounded(g_ctx, out_root, "one")
    report, more = _agent(ctx, "spark13", max(0.0, budget - spent - g_spent))
    return _keep_id(combine.ensemble([report, g], raw, "ensemble"), report), spent + g_spent + more


REVIEWS: dict[str, Review] = {
    "open": review_open,
    "spark13": review_spark13,
    "spark13-deep": review_spark13_deep,
    "hybrid-open": review_hybrid_open,
    "hybrid-spark13": review_hybrid,
    "grounded-one": review_grounded_one,
    "grounded-many": review_grounded_many,
    "two-tier": review_two_tier,
    "ensemble": review_ensemble,
}


def selected() -> str:
    name = os.getenv("ACCESSWALK_REVIEW", "").strip() or DEFAULT_REVIEW
    if name not in REVIEWS:
        raise ValueError(f"ACCESSWALK_REVIEW={name!r}; use one of {sorted(REVIEWS)}")
    return name


def run_review(ctx: AgentContext, out_root: Path = DEFAULT_OUT_ROOT, budget: float = 0.5,
               name: str | None = None) -> tuple[Report, float]:
    return REVIEWS[name or selected()](ctx, Path(out_root), budget)
