"""Export the report contract for the frontend (Session B).

  frontend/src/schema/report.schema.json   JSON Schema of accesswalk.schemas.Report
  frontend/src/mock/report.json            mock report (--mock; needs the local SAM cache)
  frontend/src/schema/api.schema.json      JSON Schema of the HTTP API models (api_models.py)
  frontend/src/mock/api/*.json             example API responses (one per job state, etc.)

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

from accesswalk import api_models as api  # noqa: E402
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
from pydantic import BaseModel  # noqa: E402

SCHEMA_OUT = REPO_ROOT / "frontend" / "src" / "schema" / "report.schema.json"
MOCK_OUT = REPO_ROOT / "frontend" / "src" / "mock" / "report.json"
API_SCHEMA_OUT = REPO_ROOT / "frontend" / "src" / "schema" / "api.schema.json"
API_MOCK_DIR = REPO_ROOT / "frontend" / "src" / "mock" / "api"
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


def api_mocks(report: Report) -> dict[str, BaseModel]:
    """Example responses with fixed timestamps, so the files change only with the contract."""
    t0, t1 = "2026-10-30T15:00:00+00:00", "2026-10-30T15:03:20+00:00"
    sha = report.video.video_sha256
    job = dict(job_id="job-7f3a9c", title="Residential sidewalk past a large tree", created_at=t0)
    url = f"/api/reports/{report.report_id}"
    return {
        "health": api.Health(ok=True, agent_provider="baseten",
                             agent_model="meta-models/muse-spark-open-1026", sam_model=sam.MODEL),
        "job_queued": api.JobStatus(**job, state="queued", updated_at=t0, message="Waiting to start"),
        "job_running": api.JobStatus(**job, state="running", stage="segment", progress=0.35, updated_at=t1,
                                     message="SAM: 4 of 12 phrases", video_sha256=sha, cost_usd=0.09),
        "job_done": api.JobStatus(**job, state="done", stage="report", progress=1.0, updated_at=t1,
                                  message="Report ready", video_sha256=sha, cost_usd=0.41,
                                  report_id=report.report_id, report_url=url),
        "job_failed": api.JobStatus(**job, state="failed", stage="ingest", progress=0.05, updated_at=t1,
                                    message="Upload rejected",
                                    error=api.JobError(code="bad_request",
                                                       message="video is 4.2 min long; the limit is 2 min")),
        "reports": api.ReportList(reports=[api.ReportSummary(
            report_id=report.report_id, title=report.title, video_sha256=sha,
            created_at=report.run.created_at, rating=report.verdict.rating,
            n_findings=len(report.findings), report_url=url)]),
        "error_not_found": api.ErrorResponse(error=api.JobError(code="not_found", message="no job job-0000")),
    }


def write_api_contract() -> None:
    API_SCHEMA_OUT.write_text(json.dumps(api.json_schema(), indent=2) + "\n")
    print(f"wrote {API_SCHEMA_OUT.relative_to(REPO_ROOT)}")
    API_MOCK_DIR.mkdir(parents=True, exist_ok=True)
    for name, model in api_mocks(Report.model_validate_json(MOCK_OUT.read_text())).items():
        (API_MOCK_DIR / f"{name}.json").write_text(model.model_dump_json(indent=2) + "\n")
    print(f"wrote {API_MOCK_DIR.relative_to(REPO_ROOT)}/*.json")


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
    write_api_contract()
    return 0


if __name__ == "__main__":
    sys.exit(main())
