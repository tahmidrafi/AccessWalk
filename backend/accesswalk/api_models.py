"""HTTP API contract (d6-api) between the backend and the report UI (Session B).

Only Session A edits this file; ``scripts/export_schema.py`` writes
``frontend/src/schema/api.schema.json`` and mock responses under
``frontend/src/mock/api/`` in the same commit. Changes are additive after Oct 29.

Routes (all JSON unless noted; errors are ``ErrorResponse`` with the HTTP status):

  GET  /api/health                      -> Health
  POST /api/jobs   multipart: video (mp4/mov, <= MAX_UPLOAD_MB, <= MAX_DURATION_S),
                   title (optional str)  -> 202 JobStatus (state "queued")
                                            400 bad_request · 413 too_large · 415 unsupported_media
  GET  /api/jobs/{job_id}               -> JobStatus                    404 not_found
  GET  /api/reports                     -> ReportList (newest first)
  GET  /api/reports/{report_id}         -> schemas.Report (report.schema.json)   404 not_found
  GET  /media/{video_sha256}/proxy.mp4  -> video/mp4, supports Range (206)
  GET  /media/{video_sha256}/frames/{i}.jpg, /media/{video_sha256}/masks/{name}.png
                                        -> image (face- and plate-blurred / mask PNG)

Job lifecycle: ``queued -> running -> done`` or ``-> failed``. While running,
``stage`` says which step: ingest (face blur, derived files) -> segment (SAM) ->
inventory -> review (agent) -> report. Poll ``GET /api/jobs/{id}`` about every 2 s;
when ``state == "done"``, ``report_url`` points at the report. A job whose
estimated model cost exceeds the server budget fails with error code ``over_budget``
before any paid call.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .schemas import RouteRating

API_VERSION = "1.0"
MAX_UPLOAD_MB = 300
MAX_DURATION_S = 120

JobState = Literal["queued", "running", "done", "failed"]
JobStage = Literal["ingest", "segment", "inventory", "review", "report"]
ErrorCode = Literal[
    "bad_request", "too_large", "unsupported_media", "not_found", "over_budget", "pipeline_error"
]


class Health(BaseModel):
    ok: bool
    api_version: str = API_VERSION
    agent_provider: str  # primary host, e.g. "baseten"
    agent_model: str  # e.g. "meta-models/muse-spark-open-1026"
    sam_model: str


class JobError(BaseModel):
    code: ErrorCode
    message: str


class JobStatus(BaseModel):
    job_id: str
    state: JobState
    stage: JobStage | None = None  # set while running, and on failure (where it failed)
    progress: float = Field(0.0, ge=0, le=1)  # rough, for a progress bar
    message: str = ""  # human-readable step detail, e.g. "SAM: 4 of 12 phrases"
    title: str | None = None
    video_sha256: str | None = None  # known after ingest
    created_at: str
    updated_at: str
    cost_usd: float = 0.0  # model spend so far (cache hits are free)
    report_id: str | None = None
    report_url: str | None = None  # /api/reports/{report_id} when done
    error: JobError | None = None


class ReportSummary(BaseModel):
    report_id: str
    title: str
    video_sha256: str
    created_at: str
    rating: RouteRating
    n_findings: int
    report_url: str


class ReportList(BaseModel):
    reports: list[ReportSummary]


class ErrorResponse(BaseModel):
    error: JobError


API_MODELS = [Health, JobStatus, ReportList, ErrorResponse]


def json_schema() -> dict:
    """JSON Schema of every API body (exported to frontend/src/schema/api.schema.json)."""
    from pydantic.json_schema import models_json_schema

    _, schema = models_json_schema([(m, "serialization") for m in API_MODELS],
                                   title="AccessWalk HTTP API " + API_VERSION)
    return schema
