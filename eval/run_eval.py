"""Score frozen runs against the done annotations. No network, no spend.

  micromamba run -n accesswalk python eval/run_eval.py --agent v1 [--baseline baseline-v1]
  micromamba run -n accesswalk python eval/run_eval.py --agent v1 --synthetic

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
from accesswalk.scoring import evaluate, load_reports  # noqa: E402

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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="v1")
    ap.add_argument("--baseline")
    ap.add_argument("--synthetic", action="store_true")
    a = ap.parse_args()
    if a.synthetic:
        return synthetic()
    annotations = load_all()
    systems = [("agent", a.agent, load_reports(RUNS / a.agent))]
    if a.baseline:
        systems.append(("baseline", a.baseline, load_reports(RUNS / a.baseline)))
    results = evaluate(annotations, systems)
    show(results)
    if not annotations:
        print("\nno done annotations yet: nothing scored")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{a.agent}.json").write_text(
        json.dumps(results.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
