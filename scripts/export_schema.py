"""Export the report contract for the frontend (Session B).

  frontend/src/schema/report.schema.json   JSON Schema of accesswalk.schemas.Report
  frontend/src/mock/report.json            mock report (--mock; needs the local SAM cache)

The mock uses REAL SAM 3.1 tracks from the first clip (PXL_20261027_211833467,
cached by the d4 phrase test) and HAND-WRITTEN findings standing in for the
agent, which does not exist yet (d5). ``run.agent_provider`` is "mock" to say so.

Media URLs follow the convention the API will serve (d6-fewire):
  /media/<video_sha256>/proxy.mp4 · /media/<video_sha256>/frames/<frame_index>.jpg

Run:  micromamba run -n accesswalk python scripts/export_schema.py [--mock]
"""
import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from accesswalk import cache, sam  # noqa: E402
from accesswalk.ingest import ingest  # noqa: E402
from accesswalk.inventory import build_tracks  # noqa: E402
from accesswalk.schemas import (  # noqa: E402
    BBox,
    CheckSummary,
    Finding,
    Report,
    RouteVerdict,
    RunInfo,
    VideoInfo,
)

SCHEMA_OUT = REPO_ROOT / "frontend" / "src" / "schema" / "report.schema.json"
MOCK_OUT = REPO_ROOT / "frontend" / "src" / "mock" / "report.json"
MOCK_CLIP = REPO_ROOT / "data" / "raw" / "PXL_20261027_211833467.mp4"
MOCK_PHRASES = ["raised sidewalk slab", "tree root", "sidewalk", "overgrown vegetation"]
LEVEL_REF = "2010 ADA Standards 303.2-303.4: level changes over 1/4 in need a bevel; over 1/2 in, a ramp"


def _no_net(*_a, **_k):
    raise SystemExit("mock needs the cached phrase-test results for the first clip")


def build_mock() -> Report:
    meta = ingest(MOCK_CLIP)
    tracks = []
    for phrase in MOCK_PHRASES:
        res = cache.segment_cached(None, meta, phrase, segment_fn=_no_net, upload_fn=_no_net)
        tracks += build_tracks(phrase, res.records, meta)
    media = f"/media/{meta.video_sha256}"
    for t in tracks:
        t.keyframe_url = f"{media}/frames/{t.keyframe_index}.jpg"
    by_id = {t.track_id: t for t in tracks}

    def cite(track_id: str, frame_index: int) -> dict:
        box = next(b for b in by_id[track_id].boxes if b.frame_index == frame_index)
        return dict(
            track_id=track_id, frame_index=frame_index, frame_ms=box.frame_ms,
            bbox=BBox(x1=box.x1, y1=box.y1, x2=box.x2, y2=box.y2),
            frame_url=f"{media}/frames/{frame_index}.jpg",
        )

    findings = [
        Finding(
            finding_id="f1", check_id="surface_damage", severity="high", confidence=0.82,
            title="Heaved slab beside a tree trunk",
            evidence_note=(
                "The slab next to the tree trunk is broken into several pieces that sit at "
                "different heights, with tree roots exposed along its outer edge. The raised "
                "edges look large enough to stop a front caster. Height is judged from video "
                "alone: verify on site."
            ),
            verify_manually=True, reference=LEVEL_REF, related_track_ids=["tree-root-0"],
            **cite("raised-sidewalk-slab-4", 60),
        ),
        Finding(
            finding_id="f2", check_id="surface_damage", severity="medium", confidence=0.68,
            title="Cracked, tilted slab before the tree",
            evidence_note=(
                "This slab is cracked across and its outer corner has dropped toward the dirt "
                "strip, leaving a cross-slope and an uneven joint. Passable with care; the "
                "slope is judged from video alone."
            ),
            verify_manually=True, reference=LEVEL_REF,
            **cite("raised-sidewalk-slab-1", 54),
        ),
        Finding(
            finding_id="f3", check_id="surface_damage", severity="low", confidence=0.41,
            title="Crack across a slab, possibly uneven",
            evidence_note=(
                "SAM flagged this slab as raised. A crack runs across it, but on re-check the "
                "two sides look nearly flush. Kept at low confidence; verify on site."
            ),
            verify_manually=True, reference=LEVEL_REF,
            **cite("raised-sidewalk-slab-6", 90),
        ),
    ]
    checks = [
        CheckSummary(check_id="surface_damage", status="ran", n_findings=3),
        CheckSummary(check_id="sidewalk_obstruction", status="ran", n_findings=0,
                     note="Trash bin seen at 1 s is beside the sidewalk, not on it."),
        CheckSummary(check_id="narrow_passage", status="ran", n_findings=0),
        CheckSummary(check_id="missing_curb_ramp", status="ran", n_findings=0,
                     note="No street crossing on this stretch."),
        CheckSummary(check_id="sidewalk_ends", status="ran", n_findings=0),
        CheckSummary(check_id="steps_without_ramp", status="not_applicable",
                     note="No entrance in this clip."),
        CheckSummary(check_id="missing_handrail", status="not_applicable",
                     note="No steps or ramp in this clip."),
        CheckSummary(check_id="round_doorknob", status="not_applicable",
                     note="No entrance in this clip."),
    ]
    return Report(
        report_id=f"mock-{meta.video_sha256[:12]}",
        title="Residential sidewalk past a large tree (mock)",
        video=VideoInfo(
            video_sha256=meta.video_sha256,
            duration_ms=round(meta.source.duration_s * 1000),
            width=meta.sam.width, height=meta.sam.height, sam_fps=meta.sam.fps,
            proxy_url=f"{media}/proxy.mp4", frame_ms=meta.frame_ms,
        ),
        verdict=RouteVerdict(
            rating="caution",
            summary=(
                "Mostly a continuous sidewalk, but one slab beside the large tree (about 12 s in) "
                "is heaved enough to be a likely barrier for a wheelchair. Check its height before "
                "relying on this route."
            ),
            key_finding_ids=["f1"],
        ),
        findings=findings,
        tracks=tracks,
        checks=checks,
        run=RunInfo(
            agent_provider="mock", agent_model="mock (hand-written findings on real SAM tracks)",
            sam_model=sam.MODEL, n_model_calls=len(MOCK_PHRASES), cost_usd=0.0,
            created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        ),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="also rebuild the mock report")
    args = ap.parse_args()
    SCHEMA_OUT.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_OUT.write_text(json.dumps(Report.model_json_schema(), indent=2) + "\n")
    print(f"wrote {SCHEMA_OUT.relative_to(REPO_ROOT)}")
    if args.mock:
        report = build_mock()
        MOCK_OUT.parent.mkdir(parents=True, exist_ok=True)
        MOCK_OUT.write_text(report.model_dump_json(indent=2) + "\n")
        print(f"wrote {MOCK_OUT.relative_to(REPO_ROOT)}: {len(report.findings)} findings, "
              f"{len(report.tracks)} tracks, {sum(t.n_frames for t in report.tracks)} boxes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
