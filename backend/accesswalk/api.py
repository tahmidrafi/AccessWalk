"""FastAPI app (d6-api). Contract: api_models.py (routes listed in its docstring).

Run:  micromamba run -n accesswalk uvicorn accesswalk.api:app --app-dir backend --port 8000

Media: only blurred derived files are served -- ``proxy.mp4`` (faces blurred;
plates not yet, d6-plateblur-proxy blocks deploy), rendered ``frames/<i>.jpg``
(faces + plates blurred) and ``masks/<name>.png``. Paths are matched against a
fixed pattern, so nothing else under data/ (raw uploads with GPS, caches) is
reachable. Raw uploads go to data/raw/uploads/ and are never served.
"""
from __future__ import annotations

import os
import re
from concurrent.futures import Executor, ThreadPoolExecutor
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import jobs, llm, sam
from .api_models import (
    MAX_DURATION_S,
    MAX_UPLOAD_MB,
    ErrorResponse,
    Health,
    JobError,
    JobStatus,
    ReportList,
    ReportSummary,
)
from .ingest import DEFAULT_OUT_ROOT, probe_source
from .schemas import Report

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

VIDEO_TYPES = {".mp4": "video/mp4", ".mov": "video/quicktime"}
MEDIA_PATH = re.compile(r"^(proxy\.mp4|frames/\d{1,5}\.jpg|masks/[A-Za-z0-9_-]{1,120}\.png)$")
SHA = re.compile(r"^[0-9a-f]{64}$")
CHUNK = 1 << 20


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def create_app(
    store: jobs.JobStore | None = None,
    pipeline: jobs.Pipeline | None = None,
    executor: Executor | None = None,
    reports_dir: Path = jobs.REPORTS_DIR,
    upload_dir: Path = jobs.UPLOAD_DIR,
    media_root: Path = DEFAULT_OUT_ROOT,
) -> FastAPI:
    app = FastAPI(title="AccessWalk API", version="1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("ACCESSWALK_CORS", "http://localhost:5173").split(","),
        allow_methods=["GET", "POST"], allow_headers=["*"],
    )
    state = {"store": store, "executor": executor or ThreadPoolExecutor(max_workers=1)}
    run_pipeline = pipeline or jobs.real_pipeline

    def get_store() -> jobs.JobStore:
        if state["store"] is None:
            state["store"] = jobs.JobStore()
        return state["store"]

    @app.exception_handler(ApiError)
    async def _api_error(_req: Request, e: ApiError) -> JSONResponse:
        body = ErrorResponse(error=JobError(code=e.code, message=e.message))  # type: ignore[arg-type]
        return JSONResponse(body.model_dump(), status_code=e.status)

    @app.get("/api/health", response_model=Health)
    def health() -> Health:
        p = llm.providers_from_env()["baseten"]
        return Health(ok=True, agent_provider=p.name, agent_model=p.model, sam_model=sam.MODEL)

    @app.post("/api/jobs", response_model=JobStatus, status_code=202)
    def create_job(video: Annotated[UploadFile, File()],
                   title: Annotated[str | None, Form()] = None) -> JobStatus:
        ext = Path(video.filename or "").suffix.lower()
        if ext not in VIDEO_TYPES:
            raise ApiError(415, "unsupported_media", "upload an .mp4 or .mov video")
        st = get_store()
        job = st.create(title=(title or "").strip()[:120] or None)
        upload_dir.mkdir(parents=True, exist_ok=True)
        raw = upload_dir / f"{job.job_id}{ext}"
        size, limit = 0, MAX_UPLOAD_MB * CHUNK
        with raw.open("wb") as f:
            while chunk := video.file.read(CHUNK):
                size += len(chunk)
                if size > limit:
                    break
                f.write(chunk)
        if size > limit:
            raw.unlink(missing_ok=True)
            _reject(st, job.job_id, "too_large", f"video is over {MAX_UPLOAD_MB} MB")
            raise ApiError(413, "too_large", f"video is over {MAX_UPLOAD_MB} MB")
        try:
            duration = probe_source(raw).duration_s
        except Exception:
            raw.unlink(missing_ok=True)
            _reject(st, job.job_id, "bad_request", "could not read a video stream from the upload")
            raise ApiError(400, "bad_request", "could not read a video stream from the upload") from None
        if duration > MAX_DURATION_S:
            raw.unlink(missing_ok=True)
            msg = f"video is {duration / 60:.1f} min long; the limit is {MAX_DURATION_S // 60} min"
            _reject(st, job.job_id, "bad_request", msg)
            raise ApiError(400, "bad_request", msg)
        state["executor"].submit(jobs.run_job, st, job.job_id, raw, run_pipeline, reports_dir)
        return st.get(job.job_id) or job

    def _reject(st: jobs.JobStore, job_id: str, code: str, msg: str) -> None:
        st.update(job_id, state="failed", stage="ingest", message=msg,
                  error=JobError(code=code, message=msg))  # type: ignore[arg-type]

    @app.get("/api/jobs/{job_id}", response_model=JobStatus)
    def get_job(job_id: str) -> JobStatus:
        job = get_store().get(job_id)
        if job is None:
            raise ApiError(404, "not_found", f"no job {job_id}")
        return job

    @app.get("/api/reports", response_model=ReportList)
    def reports() -> ReportList:
        return ReportList(reports=[
            ReportSummary(report_id=r.report_id, title=r.title, video_sha256=r.video.video_sha256,
                          created_at=r.run.created_at, rating=r.verdict.rating, n_findings=len(r.findings),
                          report_url=f"/api/reports/{r.report_id}")
            for r in jobs.list_reports(reports_dir)
        ])

    @app.get("/api/reports/{report_id}", response_model=Report)
    def report(report_id: str) -> Report:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", report_id):
            raise ApiError(404, "not_found", f"no report {report_id}")
        r = jobs.find_report(report_id, reports_dir)
        if r is None:
            raise ApiError(404, "not_found", f"no report {report_id}")
        return r

    @app.get("/media/{sha}/{path:path}")
    def media(sha: str, path: str) -> FileResponse:
        if not SHA.fullmatch(sha) or not MEDIA_PATH.fullmatch(path):
            raise ApiError(404, "not_found", "no such media")
        file = Path(media_root) / sha / path
        if not file.is_file():
            raise ApiError(404, "not_found", "no such media")
        ctype = {".mp4": "video/mp4", ".jpg": "image/jpeg", ".png": "image/png"}[file.suffix]
        return FileResponse(file, media_type=ctype)  # Starlette answers Range requests with 206

    return app


app = create_app()
