# AccessWalk — project guide for Claude Code

AccessWalk turns a first-person phone walkthrough video of a route (bus stop/parking → sidewalk → entrance)
into a "know before you go" accessibility report for wheelchair users. Every finding is grounded in a tracked
object and a video frame. Built solo for the **Meta Global AI Developer Hackathon** (indie track).

Positioning: a pre-trip / pre-audit screening tool. NOT an ADA compliance certification, NOT real-time
navigation for blind users. Say "likely barrier" / "verify manually", never "violation".

## Hackathon rules that constrain the code (read before every change)
- **Build window: guide says Oct 27 → Nov 4, 9:00 PM ET (kickoff slide says Oct 26 → Nov 4).** Only work created in this window counts.
  Commits must show that; no importing old code. Keep commit history honest and incremental.
- **Repo is public.** Never commit `.env`, API keys, raw videos, audio, or unblurred frames.
  `.gitignore` already excludes `data/raw/`, `data/cache/`, `data/out/`, `*.mp4`, `*.mov`, `*.wav`, `.env`.
- **Banned: "simple image analyzer".** Value must come from video tracking (object identity across frames),
  route-level reasoning, evidence-cited findings, and measured precision/recall — not "upload photo, get labels".
- Also banned (kickoff slides): **Streamlit apps** and **dashboards as the main feature**. Frontend is React;
  the report presents agent findings with evidence, not charts.
- Judging rubric (kickoff, Oct 26): **Impact 30%** (real-world potential, who benefits, problem fit) ·
  **Use of Meta AI tooling 25%** (creative use beyond a basic integration) · **Technical depth 20%** ·
  **Demo 25%** (working demo that holds up + 3-min video). Stage 1 is pass/fail (theme fit + uses Meta AI).
  Top 5 per track demo **live** on Nov 9 → keep a cached sample route that always runs.
- Bonus targets: **Best Agentic Use-Case** (judged on autonomy, effectiveness, usefulness);
  **Best Build on Open-Weight Models** — the infra partner verifies the product runs on an eligible open-weight
  model, so the shipped agent must run on Muse Spark Open via Baseten (Muse Spark 1.3 only as fallback), and
  every model call logs which model served it. Also: Most Viral (X post, engagement through Nov 8) and
  Community Vote (public gallery, winner Nov 16).
- Privacy: free Meta credits mean uploaded content may be used for product improvement. **Blur faces/plates
  before sending frames to any model where possible**, and never commit unblurred media.
  Pixel clips embed **GPS location** in metadata: strip it from every derived file (`-map_metadata -1`)
  and never upload a raw `data/raw/` file to any model or host.

## Environment (Windows, micromamba)
- Env name: `accesswalk` (Python 3.11, ffmpeg, Node 20). Defined in `environment.yml`; created by `setup.ps1`.
- Run anything with: `micromamba run -n accesswalk <cmd>` (or `micromamba activate accesswalk`).
- Smoke test: `micromamba run -n accesswalk python scripts/check_setup.py`
- Keys live in `.env` (template: `.env.example`): `MODEL_API_KEY`, `META_BASE_URL`, `BASETEN_API_KEY`,
  `BASETEN_BASE_URL`, `BASETEN_MODEL`, `FIREWORKS_API_KEY`, `FIREWORKS_BASE_URL`, `FIREWORKS_MODEL`.
  Load with python-dotenv. Never print full keys. Modal auth uses `modal token new` (stored in the user
  profile, not `.env`).
- Add a dependency → add it to `environment.yml` (pip section) in the same change.

## Repo layout (single repo)
```
backend/accesswalk/   Python package: ingest, sam client, inventory, agent, transcribe, report, api (FastAPI)
frontend/             React (Vite) report UI — Session B, from Oct 29
eval/                 eval harness: precision/recall per check, baseline comparison
data/annotations/     ground-truth JSON per clip (committed)
data/raw/             source videos (git-ignored)
data/cache/           cached model outputs keyed by video hash (git-ignored)
scripts/              one-off utilities (check_setup.py, etc.)
```
No git repo existed before Oct 28: first action is `git init` + initial commit of the scaffold.

## Progress file (read at the start of every session)
- `PROGRESS.md` (repo root, committed) is the task list. Task IDs match the owner's tracker; never rename them.
- At session start: read it, report what's done, and propose the next 1–3 open tasks (earliest day first,
  carried-over tasks before today's). Wait for a go-ahead before starting.
- When a task is finished, tick it (`[x]`) in the same commit as the work; `[~]` while in progress; `[-]` if
  dropped (with a one-line reason). Add new tasks under the right day with a new kebab-case ID.
- Append one line per session to the Log section: date, what changed, anything blocked.

## Parallel Claude Code sessions (from Thu 10/29)
- **Session A (pipeline):** owns `backend/`, `eval/`, `scripts/`, `data/annotations/`, this file.
- **Session B (frontend):** owns `frontend/` only. Builds against `frontend/src/mock/report.json`.
- The contract is `backend/accesswalk/schemas.py` (pydantic `Finding`, `Track`, `Report`) plus the exported
  JSON Schema in `frontend/src/schema/report.schema.json`. Only Session A changes schemas; it regenerates the
  JSON Schema and the mock in the same commit. Never edit the other session's directories.
- Commit often from both; pull/rebase before each commit to avoid conflicts.

## Pipeline
```
video ─► ingest (ffmpeg: re-encode to low fps for SAM, keyframes, 24 kHz mono WAV)
  ├─► Muse Voice Transcribe ─► location tags from narration ("bus stop", "approaching entrance")
  └─► SAM 3.1 video tracking, one noun phrase per request ─► tracks (object id, per-frame box+mask)
        ─► inventory: dedupe tracks, best keyframe per object, face blur
              ─► verification agent (Muse Spark Open on Baseten; Muse Spark 1.3 as fallback)
                   tools: get_track · view_frame · recheck_with_sam · cite_finding
                   rules: YAML (check id, evidence required, reference, severity)
                   output: JSON validated; findings without a valid track+frame citation are DROPPED
              ─► route verdict ─► report (timeline, mask overlays, findings, PDF)
eval: ground truth ─► precision/recall per check; baseline = Muse Spark 1.3 on the raw video, no tools
```

### Ingest specifics (Pixel 8 Pro clips, verified Oct 28)
- Source: HEVC 1920×1080 with rotation −90 (portrait), ~20 Mbps, 30 fps (low light ~24 fps), AAC stereo
  48 kHz, GPS in metadata, plus an extra Pixel data track. Clips are 15–50 s.
- **Face blur first, locally**: detect faces on every source frame with OpenCV YuNet (`cv2.FaceDetectorYN`,
  model `face_detection_yunet_2023mar.onnx` from github.com/opencv/opencv_zoo, saved under `models/`,
  git-ignored), pad boxes ~20%, Gaussian-blur them, and hold each box for a few frames to cover misses.
  Every derived video below is made from the blurred frames, so no unblurred face leaves the machine.
  Originals in `data/raw/` are never modified. License plates: blur in anything published (report frames,
  demo video) using SAM `license plate` tracks.
- Produce per clip (all with `-map 0:v:0 -map 0:a:0? -map_metadata -1`, rotation applied by re-encode):
  1. `sam.mp4`: H.264, 5 fps, 720p short side, no audio → sent to SAM.
  2. `proxy.mp4`: H.264 + AAC, 720p, original fps, `+faststart` → plays in the report page (HEVC won't).
  3. `audio.wav`: mono 24 kHz 16-bit PCM → Voice Transcribe. The Oct-27 clips have **no narration**: an empty
     transcript is normal, and location tags are optional everywhere downstream.
  4. `meta.json`: source fps, duration, frame-index↔ms mapping for `sam.mp4`, video hash.
- Cache key = sha256 of the raw file.

### Geometry spike (MapAnything on Modal) — go/no-go Sat 10/31, 2 h cap
- Problem: phone video flattens depth; slab heave, slope and clear width look smaller than they are.
- Try `facebook/map-anything-apache` (Meta + CMU, Apache 2.0, metric 3D from images) on a Modal GPU on
  blurred keyframes from 2–3 clips. Measure: clear width at a narrow passage, slab lift height, slope.
- Go if estimates are within a plausible range of tape-measure checks; then expose a `measure_geometry`
  agent tool and report values as "~estimated" with `verify_manually: true`. No-go → drop, note in README.

## MVP checks (outdoor first)
1. Sidewalk obstruction (bins, branches, cars, signs)  2. Surface damage (heaved/broken slabs, potholes)
3. Missing curb ramp  4. Sidewalk ends (absence → reasoning, not segmentation; test early, drop if weak)
5. Steps without ramp  6. Missing handrail  7. Round doorknob  8. Narrow passage
Drop a check rather than show weak numbers.
Known limitation: when a finding rests on depth/height/slope judged from video alone, set
`verify_manually: true` and say so in `evidence_note`.

### Filming protocol (new clips)
- Phone upright, chest height, steady walking pace. At each barrier: slow down, pause ~2 s, tilt toward it.
- Do not narrate barriers (eval leakage); narrate locations only ("bus stop", "approaching entrance",
  "corner of X and Y"). The Oct-27 clips are silent; narrate the new clips and the demo route.
- Capture both positives and clean "no barrier" stretches. Gaps as of Oct 28: curb ramp (missing and
  present), steps without ramp, round doorknob, bins/cars/signs blocking the sidewalk.

## Meta API facts (verified from dev.meta.ai docs, Oct 26 2026)
- Base URL `https://api.meta.ai/v1`, Bearer `MODEL_API_KEY`, OpenAI-SDK compatible.
- **SAM 3.1** (`sam-3.1`): Responses API (`POST /v1/responses`). One short noun phrase per request
  (several object types = several requests). Video via `input_video` part: MP4/MOV, H.264/H.265/MPEG-4.
  Upload once via Files API when reusing a clip. Streaming recommended for video.
  Output is special-token text in `output_text`, one line per frame:
  `<0f>0<|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..|><|mask;x=..;y=..;data=...|>,1<|box...|>...`
  (`<Nf>` = frame, leading int = object ordinal, stable across frames). Official parser is TypeScript
  (`@meta-sam/parser`); grammar documented at dev.meta.ai/docs/sam/reading-segmentation — write a Python
  parser against that doc, with tests. Empty `output_text` = zero matches (valid).
  Price: $0.20 / 1,000 video frames, **min 50 frames billed per request**; `usage.video_frames_processed`.
  Unverified (third-party): hosted cap ~15,000 frames and 16 tracked objects per frame.
- **Muse Voice Transcribe** (`muse-voice-transcribe-1.0`): `POST /v1/asr/transcribe`, multipart
  (`request` JSON part + `audio` file). Mono 16-bit PCM WAV at 16 or 24 kHz, ≤10 min, ≤32 MB.
  `mode: "ENDPOINTING"` → `turns[]` with `startMs`/`endMs`. `keywords` biases vocabulary (street names).
  Turn-level timestamps only. $0.18/hour.
  ffmpeg: `ffmpeg -i in.mp4 -vn -ac 1 -ar 24000 -c:a pcm_s16le -map_metadata -1 out.wav`
- **Muse Spark 1.3** (`muse-spark-1.3`): text/image/video/audio/PDF in, 1M context. $1.25 in / $4.25 out per 1M.
  Use for the raw-video baseline and as agent fallback. Do NOT use `-contributor` variants.
- **Muse Spark Open on Baseten**: `https://inference.baseten.co/v1`, model `meta-models/muse-spark-open-1026`
  (hackathon ID — not `muse-spark-open`). Reasoning model: set generous `max_tokens`, otherwise
  `message.content` can come back `None`. Supports image input (check Baseten "Vision" docs).

## Other providers
- **Fireworks**: failover host for the *same* open-weight agent model (keeps open-weight eligibility).
  OpenAI-compatible, `https://api.fireworks.ai/inference/v1`, model `accounts/fireworks/models/muse-spark-open`
  (serverless; verified via `/models` Oct 28). $1.25/M in, $0.15/M cached, $4.25/M out. Don't use the
  "816B-A42B NVFP4" or Glimmer entries: those need a dedicated deployment billed per GPU hour.
  Provider is a config switch, not new code.
- **Modal**: GPU only for the MapAnything spike (and optionally hosting the backend for the live demo).
  Set function timeouts, scale to zero, cap GPU minutes; log GPU seconds per run.
- Every model call logs `provider`, `model`, `usage` to `data/out/usage.jsonl`.

## Cost guardrails (Meta ≈ $170 · Baseten $100 · Fireworks $100 · Modal $101)
- Cache every model call by (video hash, model, prompt, params) under `data/cache/`. Re-runs must be free.
- Expected SAM spend: ~1,670 frames per noun phrase for the 11 Oct-27 clips at 5 fps ≈ $0.33/phrase.
- Re-encode to a low fps (start with 5 fps, verify tracking holds) before SAM. Estimate frames × prompts
  and log expected cost before any batch run; ask before runs estimated > $5.
- Never loop model calls without a cap. Log `usage` from every response to `data/out/usage.jsonl`.

## Conventions
- Python: type hints, pydantic models for all JSON crossing module boundaries, `ruff` clean, `pytest` for
  parsers/validators (no network in unit tests; use recorded fixtures).
- Times: store video time in milliseconds (int). Frame indices refer to the **re-encoded** clip; keep the
  mapping to source time.
- Findings schema (minimum): `check_id, severity, confidence, track_id, frame_ms, bbox, evidence_note,
  location_tag, verify_manually: bool`.
- Small, focused commits with clear messages. README gets a "Built during the hackathon" section.

## Schedule (CT; workshops 11 AM–12 PM CT) — revised Oct 28 (Tue tasks slipped)
Live tracker artifact mirrors this list.
- Wed 10/28: git init + first commit; ingest (outputs above); SAM client + Python parser + tests;
  SAM on 1 clip × 3 phrases; usage logging. (Agents 102)
- Thu 10/29: SAM all phrases × 11 clips (estimate first); inventory (dedupe, keyframes, face/plate blur);
  freeze `schemas.py` + mock report JSON; annotation format + annotate 5 clips.
  Session B starts: Vite scaffold, report page on mock data.
- Fri 10/30: Baseten agent loop (tools + citation validator + rules YAML); Fireworks failover switch;
  evening: film 6–10 gap clips. (Fireworks workshop)
- Sat 10/31: agent quality (re-checks, confidence); transcription tags; route verdict; MapAnything spike
  (2 h, go/no-go). Session B: upload + job status + report page wired to real JSON.
- Sun 11/1: annotate all clips; eval + baseline; fix worst check, drop weak ones; end-to-end deploy.
- Mon 11/2: iterate; geometry tool if go; PDF export; README + architecture diagram; cached demo route.
- Tue 11/3: feature freeze at noon; demo script; record 3-min video.
- Wed 11/4: final fixes; submit by 5 PM CT (deadline 8 PM CT); post demo on X.
