"""AccessWalk on Modal (d7-deploy): the API and the built report UI on one URL, CPU only.

Public and read-only: the sample route, reports, blurred media. Uploads need the
passcode (Modal secret ``accesswalk-upload``) and stop once the spend caps below are
used up. One container at most, so jobs still run one at a time; it scales to zero
15 min after the last request, which also covers a full ~400 s job.

Owner, once (keys go straight from .env to Modal, never through a terminal log):
  modal token new
  modal secret create accesswalk --from-dotenv .env
  modal secret create accesswalk-upload ACCESSWALK_UPLOAD_PASSCODE=<16+ random characters>
Each deploy (README "Deploy" has the full sequence):
  cd frontend && VITE_SAMPLE_REPORT_ID=<report_id> npx vite build --mode http
  python scripts/deploy_bundle.py <clip> --twin <stripped copy> --upload   # blurred media only
  modal run deploy/modal_app.py --video <stripped copy>    # offline replay check, $0
  modal deploy deploy/modal_app.py
"""
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[1]
APP = "/app"  # REPO_ROOT inside the container; data/ is the volume
YUNET = "face_detection_yunet_2023mar.onnx"
PIP = [  # pinned to the local env so a cached replay renders and keys exactly as on the laptop
    "fastapi==0.162.0", "starlette==1.10.0", "python-multipart==0.0.32", "pydantic==2.14.1",
    "openai==3.39.0", "httpx==0.28.1", "requests==2.34.2", "python-dotenv==1.2.4", "PyYAML==6.0.3",
    "numpy==2.4.6", "opencv-python-headless==5.0.0.93", "meta-sam-parser==0.1.0", "pillow==13.0.0",
]
BLOCKED = "http://127.0.0.1:9/v1"

data = modal.Volume.from_name("accesswalk-data", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(*PIP)
    .env({
        "PYTHONPATH": f"{APP}/backend",
        "ACCESSWALK_FRONTEND_DIR": f"{APP}/frontend/dist",
        "ACCESSWALK_MAX_JOB_USD": "1.0",
        "ACCESSWALK_MAX_DAILY_USD": "5",
        "ACCESSWALK_MAX_TOTAL_USD": "10",
        "ACCESSWALK_DELETE_UPLOADS": "1",
    })
    .add_local_dir(ROOT / "backend" / "accesswalk", f"{APP}/backend/accesswalk", ignore=["__pycache__"])
    .add_local_file(ROOT / "models" / YUNET, f"{APP}/models/{YUNET}")
    .add_local_dir(ROOT / "frontend" / "dist", f"{APP}/frontend/dist")
)
app = modal.App("accesswalk", image=image)


@app.function(
    volumes={f"{APP}/data": data},
    secrets=[modal.Secret.from_name("accesswalk"), modal.Secret.from_name("accesswalk-upload")],
    cpu=2.0, memory=4096, timeout=900, scaledown_window=900, max_containers=1, min_containers=1,
)
@modal.concurrent(max_inputs=20)
@modal.asgi_app()
def web():
    from accesswalk import api, jobs

    run_job = jobs.run_job

    def run_and_commit(*args, **kwargs):
        try:
            run_job(*args, **kwargs)
        finally:
            data.commit()  # job record, report and caches survive the container

    jobs.run_job = run_and_commit
    return api.app


@app.function(volumes={f"{APP}/data": data}, cpu=2.0, memory=4096, timeout=900)
def offline_check(video: bytes, name: str) -> dict:
    """Run the upload pipeline on ``video`` with no keys and every model host
    unreachable: passes only if every model call is served from the volume's cache."""
    import json
    import os
    import tempfile
    import time

    for k in ("BASETEN_BASE_URL", "FIREWORKS_BASE_URL", "META_BASE_URL"):
        os.environ[k] = BLOCKED
    for k in ("BASETEN_API_KEY", "FIREWORKS_API_KEY", "MODEL_API_KEY"):
        os.environ[k] = "blocked"
    from accesswalk import jobs

    raw = Path(tempfile.mkdtemp()) / name
    raw.write_bytes(video)
    log = Path(APP) / "data" / "out" / "usage.jsonl"
    n0 = len(log.read_text().splitlines()) if log.exists() else 0
    t, err = time.time(), None
    try:
        report = jobs.real_pipeline(raw, lambda **_: None)
    except Exception as e:
        report, err = None, f"{type(e).__name__}: {str(e)[:300]}"
    new = [json.loads(line) for line in log.read_text().splitlines()[n0:]] if log.exists() else []
    return {
        "ok": report is not None, "error": err, "seconds": round(time.time() - t, 1),
        "model_calls": len(new), "not_cached": sum(not r.get("cache_hit") for r in new),
        "cost_usd": report.run.cost_usd if report else None,
        "n_findings": len(report.findings) if report else None,
    }


@app.local_entrypoint()
def main(video: str):
    p = Path(video)
    print(offline_check.remote(p.read_bytes(), p.name))
