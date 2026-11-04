"""Score frozen runs against the done annotations. No network, no spend.

  micromamba run -n accesswalk python eval/run_eval.py --agent v1 [--baseline baseline-v1]
  micromamba run -n accesswalk python eval/run_eval.py --agent v1 --synthetic
  ... --system agent:v2+v2-heldout --system baseline:baseline-v1 --clips PXL_20261027_,PXL_20261028_
  ... --merge-width     # obstruction and narrow passage scored as one "width" check

--system KIND:RUN[+RUN...] scores the union of several frozen runs (one per clip set) as one
system; --clips keeps only annotations whose clip name starts with one of the prefixes.

Reads data/out/eval_runs/<run>/, writes data/out/eval/<agent run>.json (git-ignored) and
prints the counts only, never a finding. With no done annotations it says so and scores nothing.

--synthetic scores invented findings on invented annotations and checks the expected counts:
a self-test of the harness that does not touch any real report or annotation.
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from accesswalk.annotations import ClipAnnotation, load_all  # noqa: E402
from accesswalk.scoring import (  # noqa: E402
    evaluate,
    load_reports,
    merge_width_annotation,
    merge_width_report,
)

RUNS = REPO_ROOT / "data" / "out" / "eval_runs"
OUT = REPO_ROOT / "data" / "out" / "eval"


def _pct(x: float | None) -> str:
    return "  n/a" if x is None else f"{x:5.0%}"


def show(results) -> None:
    print(
        f"{len(results.clips_scored)} clips scored, {results.n_barriers} barriers, "
        f"{results.clips_not_annotated} clips with a report but no done annotation"
    )
    for s in results.systems:
        print(f"\n{s.system} {s.run_id} | {s.provider} {s.model} | ${s.cost_usd:.4f}")
        print(f"{'check':24} hits miss  match   fp  unsc  prec  rec")
        for c in [*s.per_check, s.overall]:
            name = getattr(c, "check_id", "OVERALL")
            print(
                f"{name:24} {c.hits:4} {c.misses:4} {c.matched_findings:6} {c.false_positives:4} "
                f"{c.unscored:5} {_pct(c.precision)} {_pct(c.recall)}"
            )
        missing = [c.clip for c in s.per_clip if not c.has_report]
        if missing:
            print(f"no report, barriers counted as misses: {missing}")


def synthetic() -> int:
    """One clip with every outcome once; the expected counts are worked out by hand."""
    from accesswalk.schemas import BBox, Finding, Report, RouteVerdict, RunInfo, Track, TrackBox, VideoInfo

    ann = ClipAnnotation.model_validate(
        {
            "clip": "synthetic",
            "annotator": "test",
            "status": "done",
            "duration_s": 30.0,
            "barriers": [
                {"check": "surface_damage", "t": [10, 12], "sev": "high", "note": "n"},
                {"check": "surface_damage", "t": [20, 22], "sev": "low", "note": "n"},
            ],
            "clean": [[0, 5]],
            "not_applicable": ["round_doorknob"],
        }
    )
    box = dict(x1=0, y1=0, x2=9, y2=9)
    plan = [
        ("surface_damage", 11000),
        ("surface_damage", 12900),  # both match barrier 1
        ("sidewalk_obstruction", 2000),  # clean: FP
        ("round_doorknob", 15000),  # not applicable: FP
        ("narrow_passage", 15000),
    ]  # unlabelled: unscored
    report = Report(
        report_id="s",
        title="s",
        video=VideoInfo(video_sha256="s", duration_ms=30000, width=9, height=9, sam_fps=5, frame_ms=[0]),
        verdict=RouteVerdict(rating="caution", summary="s"),
        tracks=[
            Track(
                track_id="t",
                phrase="p",
                object_id=0,
                first_ms=0,
                last_ms=0,
                n_frames=1,
                keyframe_index=0,
                keyframe_ms=0,
                boxes=[TrackBox(frame_index=0, frame_ms=0, **box)],
            )
        ],
        findings=[
            Finding(
                finding_id=f"f{i}",
                check_id=c,
                title="t",
                severity="low",
                confidence=0.5,
                track_id="t",
                frame_index=0,
                frame_ms=ms,
                bbox=BBox(**box),
                evidence_note="e",
                verify_manually=True,
            )
            for i, (c, ms) in enumerate(plan)
        ],
        checks=[],
        run=RunInfo(agent_provider="mock", agent_model="mock", sam_model="none", created_at="now"),
    )
    res = evaluate({"synthetic": ann}, [("agent", "synthetic", {"synthetic": report})], note="synthetic")
    show(res)
    o = res.systems[0].overall
    got = (o.hits, o.misses, o.matched_findings, o.false_positives, o.unscored, o.precision, o.recall)
    ok = got == (1, 1, 2, 2, 1, 0.5, 0.5)
    print("\nsynthetic self-test:", "PASS" if ok else f"FAIL {got}")
    return 0 if ok else 1


def _load_runs(spec: str) -> dict:
    """Reports of ``run1+run2+...``; a clip in two runs is an error, not a silent pick."""
    out: dict = {}
    for run in spec.split("+"):
        reports = load_reports(RUNS / run)
        twice = out.keys() & reports.keys()
        if twice:
            raise SystemExit(f"{run}: clips already in an earlier run of {spec}: {sorted(twice)}")
        out.update(reports)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="v1")
    ap.add_argument("--baseline")
    ap.add_argument("--system", action="append", help="KIND:RUN[+RUN...]; replaces --agent/--baseline")
    ap.add_argument("--clips", help="comma-separated clip-name prefixes to score")
    ap.add_argument("--merge-width", action="store_true")
    ap.add_argument("--out", help="results file name in data/out/eval/ (default: <agent run>.json)")
    ap.add_argument("--synthetic", action="store_true")
    a = ap.parse_args()
    if a.synthetic:
        return synthetic()
    annotations = load_all()
    if a.clips:
        prefixes = tuple(a.clips.split(","))
        annotations = {c: ann for c, ann in annotations.items() if c.startswith(prefixes)}
    specs = a.system or [f"agent:{a.agent}"] + ([f"baseline:{a.baseline}"] if a.baseline else [])
    systems = []
    for spec in specs:
        kind, run = spec.split(":", 1)
        systems.append((kind, run, _load_runs(run)))
    if a.merge_width:
        annotations = {c: merge_width_annotation(ann) for c, ann in annotations.items()}
        systems = [(k, r, {c: merge_width_report(rep) for c, rep in reps.items()}) for k, r, reps in systems]
    results = evaluate(annotations, systems, note="merged width" if a.merge_width else None)
    show(results)
    if not annotations:
        print("\nno done annotations yet: nothing scored")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / (a.out or f"{a.agent}.json")).write_text(
        json.dumps(results.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
