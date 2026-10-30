"""HTTP API tests (d6-api): contract shapes, job lifecycle, upload limits, media paths.
Fake pipeline and an inline executor: no model calls, no network."""
import subprocess
from pathlib import Path

import pytest
from accesswalk import api, api_models, jobs
from accesswalk.schemas import Report
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
MOCK_JSON = REPO_ROOT / "frontend" / "src" / "mock" / "report.json"
MOCK_REPORT = Report.model_validate_json(MOCK_JSON.read_text())
SHA = MOCK_REPORT.video.video_sha256


class Inline:
    """Executor that runs the job immediately (tests see the final state)."""

    def submit(self, fn, *args):
        fn(*args)


def fake_pipeline(raw, update):
    update(stage="ingest", progress=0.1, message="ingest")
    update(stage="segment", progress=0.4, message="SAM", cost_usd=0.1)
    update(stage="review", progress=0.8, message="agent")
    return MOCK_REPORT


def failing_pipeline(raw, update):
    update(stage="ingest", progress=0.1)
    raise jobs.PipelineError("over_budget", "estimated cost $3.10 is over the $1.00 job limit")


@pytest.fixture(scope="module")
def tiny_mp4(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("vid") / "clip.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc=size=64x64:rate=5:duration=1", "-pix_fmt", "yuv420p", str(out)], check=True)
    return out


def _client(tmp_path, pipeline=fake_pipeline):
    media = tmp_path / "media"
    (media / SHA / "frames").mkdir(parents=True)
    (media / SHA / "frames" / "60.jpg").write_bytes(b"\xff\xd8jpeg")
    (media / SHA / "proxy.mp4").write_bytes(bytes(range(256)) * 4)
    (media / SHA / "masks").mkdir()
    (media / SHA / "masks" / "abc.npy").write_bytes(b"not served")
    app = api.create_app(store=jobs.JobStore(tmp_path / "jobs"), pipeline=pipeline, executor=Inline(),
                         reports_dir=tmp_path / "reports", upload_dir=tmp_path / "uploads", media_root=media)
    return TestClient(app)


def test_health(tmp_path):
    body = _client(tmp_path).get("/api/health").json()
    api_models.Health.model_validate(body)
    assert body["ok"] and body["agent_provider"] == "baseten"


def test_job_lifecycle_to_report(tmp_path, tiny_mp4):
    c = _client(tmp_path)
    r = c.post("/api/jobs", files={"video": ("walk.mp4", tiny_mp4.read_bytes(), "video/mp4")},
               data={"title": "Test route"})
    assert r.status_code == 202
    job = api_models.JobStatus.model_validate(r.json())
    done = api_models.JobStatus.model_validate(c.get(f"/api/jobs/{job.job_id}").json())
    assert (done.state, done.stage, done.progress, done.title) == ("done", "report", 1.0, "Test route")
    assert done.report_url == f"/api/reports/{MOCK_REPORT.report_id}" and done.cost_usd == 0.1
    rep = Report.model_validate(c.get(done.report_url).json())
    assert rep.report_id == MOCK_REPORT.report_id
    listing = api_models.ReportList.model_validate(c.get("/api/reports").json())
    assert listing.reports[0].n_findings == len(MOCK_REPORT.findings)
    assert (tmp_path / "jobs" / f"{job.job_id}.json").exists()  # persisted


def test_pipeline_failure_is_reported_with_stage(tmp_path, tiny_mp4):
    c = _client(tmp_path, pipeline=failing_pipeline)
    files = {"video": ("w.mov", tiny_mp4.read_bytes(), "video/quicktime")}
    job_id = c.post("/api/jobs", files=files).json()["job_id"]
    job = c.get(f"/api/jobs/{job_id}").json()
    assert job["state"] == "failed" and job["stage"] == "ingest"
    assert job["error"]["code"] == "over_budget"


def test_upload_rejections(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/jobs", files={"video": ("photo.jpg", b"x", "image/jpeg")})
    assert r.status_code == 415 and r.json()["error"]["code"] == "unsupported_media"
    r = c.post("/api/jobs", files={"video": ("fake.mp4", b"not a video", "video/mp4")})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_request"
    assert not any((tmp_path / "uploads").glob("*"))  # rejected uploads are deleted


def test_not_found_errors_follow_contract(tmp_path):
    c = _client(tmp_path)
    for url in ["/api/jobs/job-nope", "/api/reports/nope"]:
        r = c.get(url)
        assert r.status_code == 404
        api_models.ErrorResponse.model_validate(r.json())


def test_media_serves_only_blurred_derived_files(tmp_path):
    c = _client(tmp_path)
    assert c.get(f"/media/{SHA}/frames/60.jpg").headers["content-type"] == "image/jpeg"
    r = c.get(f"/media/{SHA}/proxy.mp4", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100  # seeking works
    for bad in [f"/media/{SHA}/masks/abc.npy", f"/media/{SHA}/meta.json", f"/media/{SHA}/sam.mp4",
                "/media/not-a-sha/proxy.mp4",
                f"/media/{SHA}/frames/..%2F..%2Fx.jpg"]:
        assert c.get(bad).status_code == 404, bad


def test_restart_marks_unfinished_jobs_failed(tmp_path):
    st = jobs.JobStore(tmp_path / "jobs")
    job = st.create("t")
    st.update(job.job_id, state="running", stage="segment")
    again = jobs.JobStore(tmp_path / "jobs").get(job.job_id)
    assert again.state == "failed" and again.error.code == "pipeline_error"
