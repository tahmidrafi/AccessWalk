"""Job store and the end-to-end pipeline behind ``POST /api/jobs`` (d6-api).

One job = one uploaded video -> one report. Jobs run one at a time (a single
worker), so two uploads can never double the model spend. Every job's status is
kept in memory and written to ``data/out/jobs/<job_id>.json``; a job that was
queued or running when the server stopped is marked failed on the next start.

Spend guard: before any paid call the pipeline estimates SAM cost for the clip
(frames x phrases, ignoring cache hits) plus the review budget, and fails with
``over_budget`` if that exceeds ``ACCESSWALK_MAX_JOB_USD`` (default $1). The review
stage is ``review.DEFAULT_REVIEW`` unless ``ACCESSWALK_REVIEW`` names another (see
review.py for the systems and which models they call).

Deploy-wide caps (d7-deploy): ``ACCESSWALK_MAX_TOTAL_USD`` over all jobs and
``ACCESSWALK_MAX_DAILY_USD`` over jobs created that UTC day, counted from the job
records (cache hits cost $0). Unset = no cap. ``ACCESSWALK_DELETE_UPLOADS=1``
deletes each raw upload (it keeps the phone's GPS) once its job ends.
"""
from __future__ import annotations

import os
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from . import cache, sam
from .api_models import JobError, JobStatus
from .ingest import DEFAULT_OUT_ROOT, ingest
from .inventory import build_inventory
from .phrases import SAM_PHRASES
from .schemas import Report

REPO_ROOT = Path(__file__).resolve().parents[2]
JOBS_DIR = REPO_ROOT / "data" / "out" / "jobs"
REPORTS_DIR = REPO_ROOT / "data" / "out" / "reports"
UPLOAD_DIR = REPO_ROOT / "data" / "raw" / "uploads"  # git-ignored; raw files keep GPS: never served
AGENT_BUDGET_USD = 0.5


def max_job_usd() -> float:
    return float(os.getenv("ACCESSWALK_MAX_JOB_USD", "1.0"))


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class PipelineError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class JobStore:
    def __init__(self, root: Path = JOBS_DIR):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._jobs: dict[str, JobStatus] = {}
        for p in self.root.glob("*.json"):
            job = JobStatus.model_validate_json(p.read_text(encoding="utf-8"))
            if job.state in ("queued", "running"):
                job = job.model_copy(update={
                    "state": "failed", "updated_at": _now(),
                    "error": JobError(code="pipeline_error", message="the server restarted during this job"),
                })
                p.write_text(job.model_dump_json(indent=2), encoding="utf-8")
            self._jobs[job.job_id] = job

    def create(self, title: str | None) -> JobStatus:
        now = _now()
        job = JobStatus(job_id=f"job-{uuid.uuid4().hex[:10]}", state="queued", title=title,
                        created_at=now, updated_at=now, message="Waiting to start")
        self._save(job)
        return job

    def get(self, job_id: str) -> JobStatus | None:
        with self._lock:
            return self._jobs.get(job_id)

    def all(self) -> list[JobStatus]:
        with self._lock:
            return list(self._jobs.values())

    def update(self, job_id: str, **fields) -> JobStatus:
        with self._lock:
            job = self._jobs[job_id].model_copy(update={**fields, "updated_at": _now()})
        self._save(job)
        return job

    def _save(self, job: JobStatus) -> None:
        with self._lock:
            self._jobs[job.job_id] = job
            (self.root / f"{job.job_id}.json").write_text(job.model_dump_json(indent=2), encoding="utf-8")


def _cap(name: str) -> float | None:
    v = os.getenv(name, "").strip()
    return float(v) if v else None


def spend_left_usd(store: JobStore, today: str | None = None) -> float:
    """USD the deploy-wide caps still allow. A job not finished yet reserves a full
    job budget (or what it has spent, if more), so queued uploads can't overshoot."""
    today = today or _now()[:10]
    total = day = 0.0
    for j in store.all():
        cost = j.cost_usd or 0.0
        if j.state in ("queued", "running"):
            cost = max(cost, max_job_usd())
        total += cost
        day += cost if j.created_at[:10] == today else 0.0
    left = [cap - spent for cap, spent in ((_cap("ACCESSWALK_MAX_TOTAL_USD"), total),
                                           (_cap("ACCESSWALK_MAX_DAILY_USD"), day)) if cap is not None]
    return min(left, default=float("inf"))


# A pipeline turns a raw upload into a Report, reporting progress through ``update``.
Pipeline = Callable[[Path, Callable[..., None]], Report]


def real_pipeline(raw: Path, update: Callable[..., None], out_root: Path = DEFAULT_OUT_ROOT) -> Report:
    from .agent import load_context  # heavy imports only when a job runs

    update(stage="ingest", progress=0.02, message="Blurring faces and preparing the video")
    meta = ingest(raw)
    update(video_sha256=meta.video_sha256, progress=0.1)

    est = sam.estimate_cost(meta.sam.n_frames, len(SAM_PHRASES)) + AGENT_BUDGET_USD
    if est > max_job_usd():
        raise PipelineError(
            "over_budget", f"estimated cost ${est:.2f} is over the ${max_job_usd():.2f} job limit"
        )

    client = sam.make_client()
    file_id, spent, records = None, 0.0, {}
    for i, phrase in enumerate(SAM_PHRASES):
        update(stage="segment", progress=0.1 + 0.5 * i / len(SAM_PHRASES),
               message=f"SAM: {i + 1} of {len(SAM_PHRASES)} phrases", cost_usd=round(spent, 4))
        res = cache.segment_cached(client, meta, phrase, file_id=file_id, out_root=out_root)
        file_id, spent, records[phrase] = res.file_id, spent + res.cost_usd, res.records

    update(stage="inventory", progress=0.62, message="Building the object inventory",
           cost_usd=round(spent, 4))
    build_inventory(meta, records, out_root)

    from .review import run_review, selected

    update(stage="review", progress=0.7, message="Agent reviewing tracked objects")
    ctx = load_context(raw.stem, out_root, raw_path=raw)
    report, review_spent = run_review(ctx, out_root, AGENT_BUDGET_USD, selected())
    update(stage="report", progress=0.98, message="Writing the report",
           cost_usd=round(spent + review_spent, 4))
    return report


def run_job(store: JobStore, job_id: str, raw: Path, pipeline: Pipeline,
            reports_dir: Path = REPORTS_DIR) -> None:
    """Executor entry point: run ``pipeline`` and record the outcome on the job."""
    stage: list[str | None] = [None]

    def update(**fields) -> None:
        if "stage" in fields:
            stage[0] = fields["stage"]
        store.update(job_id, state="running", **fields)

    try:
        report = pipeline(raw, update)
        reports_dir.mkdir(parents=True, exist_ok=True)
        out = reports_dir / f"{report.report_id}.json"
        out.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        store.update(job_id, state="done", stage="report", progress=1.0, message="Report ready",
                     video_sha256=report.video.video_sha256, report_id=report.report_id,
                     report_url=f"/api/reports/{report.report_id}")
    except PipelineError as e:
        store.update(job_id, state="failed", stage=stage[0], message=str(e),
                     error=JobError(code=e.code, message=str(e)))  # type: ignore[arg-type]
    except Exception as e:  # keep the server up; the job says what broke
        store.update(job_id, state="failed", stage=stage[0], message="Pipeline error",
                     error=JobError(code="pipeline_error", message=f"{type(e).__name__}: {str(e)[:300]}"))
    finally:
        if os.getenv("ACCESSWALK_DELETE_UPLOADS") == "1":
            raw.unlink(missing_ok=True)


def list_reports(reports_dir: Path = REPORTS_DIR) -> list[Report]:
    out = []
    for p in reports_dir.glob("*.json"):
        try:
            out.append(Report.model_validate_json(p.read_text(encoding="utf-8")))
        except ValueError:
            continue  # not a report (or an older format): skip rather than break the list
    return sorted(out, key=lambda r: r.run.created_at, reverse=True)


def find_report(report_id: str, reports_dir: Path = REPORTS_DIR) -> Report | None:
    direct = reports_dir / f"{report_id}.json"
    if direct.exists():
        return Report.model_validate_json(direct.read_text(encoding="utf-8"))
    return next((r for r in list_reports(reports_dir) if r.report_id == report_id), None)
