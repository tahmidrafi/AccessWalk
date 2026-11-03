# AccessWalk

**Know before you go.** Film the walk from the bus stop or parking spot to the entrance on a phone.
AccessWalk turns that video into an accessibility report for wheelchair users: likely barriers along
the route, each tied to a tracked object and the video frame it rests on.

It is a pre-trip and pre-audit screening tool. It does **not** certify ADA compliance and it is not
real-time navigation. Every finding says "likely barrier" and asks you to verify on site; anything
judged from depth, height or slope in a phone video is marked `verify_manually`.

Built solo for the Meta Global AI Developer Hackathon (indie track).

## What it does

1. **Upload** a 15 s to 2 min walkthrough (`.mp4`/`.mov` from a phone, held upright).
2. **Privacy first, locally:** faces are detected and blurred on every source frame (OpenCV YuNet)
   before any frame leaves the machine. GPS and all other metadata are stripped from every derived
   file. License plates are blurred in everything published, using SAM's own `license plate` tracks.
3. **Track:** SAM 3.1 segments and tracks 14 noun phrases across the clip (bins, cars, poles,
   construction barriers, traffic barrels, raised slabs, curbs, tactile paving, sidewalk, stairs,
   handrails, doorknobs, vegetation, plates). Each object keeps one identity across frames.
4. **Inventory:** tracks are stitched, de-duplicated across phrases, given a best keyframe, and
   measured against the sidewalk mask (how much of an object stands on the walkway).
5. **Verify (agent):** an open-weight Muse Spark Open agent reviews the inventory against 8 rule-based
   checks, with tools to read a track, look at frames, re-run SAM with a new phrase on a time window,
   and cite a finding. A finding without a valid track and frame citation is dropped.
6. **Report:** a route verdict, findings with their cited frames and mask overlays, a timeline over
   the blurred video, and a PDF export.

### The 8 checks
Sidewalk obstruction · surface damage (heaved or broken slabs) · missing curb ramp · sidewalk ends ·
steps without a ramp · missing handrail · round doorknob · narrow passage.
Checks that score poorly in the eval are dropped rather than shown with weak numbers.

## Architecture

```mermaid
flowchart LR
  V[Phone video] --> I["ingest (local)<br/>face blur · GPS strip<br/>sam.mp4 5 fps · proxy.mp4"]
  I --> S["SAM 3.1<br/>one phrase per request<br/>tracks: id + box + mask per frame"]
  S --> N["inventory<br/>stitch · dedupe · keyframes<br/>plate blur · on-sidewalk share"]
  N --> A["verification agent<br/>Muse Spark Open on Baseten<br/>(Fireworks failover)"]
  R[(rules.yaml<br/>8 checks)] --> A
  A -- "get_track · view_frame<br/>recheck_with_sam · cite_finding" --> N
  A --> G["citation validator<br/>drops uncited findings"]
  G --> P["report JSON<br/>verdict · findings · timeline"]
  P --> U["React report page<br/>video + overlays · PDF"]
  C[(cache by video hash<br/>model + prompt + params)] -.-> S
  C -.-> A
```

| Piece | Where |
|---|---|
| Ingest, face blur, metadata strip | `backend/accesswalk/ingest.py` |
| SAM 3.1 client and Python parser for its token output | `backend/accesswalk/sam.py`, `sam_parse.py` |
| Inventory, plate blur | `backend/accesswalk/inventory.py`, `plates.py` |
| Agent loop, tools, provider failover | `backend/accesswalk/agent.py`, `llm.py` |
| Rules and citation validator | `backend/accesswalk/rules.yaml`, `validator.py` |
| Route verdict | `backend/accesswalk/verdict.py` |
| API (upload, job status, reports, media) | `backend/accesswalk/api.py`, `jobs.py` |
| Report contract (pydantic → JSON Schema) | `backend/accesswalk/schemas.py`, `frontend/src/schema/` |
| Report UI | `frontend/` (React + Vite) |
| Eval harness and baseline | `eval/`, `backend/accesswalk/scoring.py`, `baseline.py` |
| Deploy | `deploy/modal_app.py`, `scripts/deploy_bundle.py` |

### Meta AI tooling
- **SAM 3.1** (Meta Model API): video tracking with stable object identity, which is what makes
  route-level reasoning possible (one bin seen across 40 frames is one bin).
- **Muse Spark Open** (open weights, served by Baseten, same model on Fireworks as failover): the
  verification agent. Every model call logs the provider and the model that served it.
- **Muse Spark 1.3**: only as the no-tools baseline in the eval (the whole raw video in one prompt).

## Evaluation

> **Results pending.** Ground truth is being annotated (22 clips filmed on a Pixel 8 Pro; 5 marked
> done so far). Numbers go here once the eval set is complete.

Method (`eval/run_eval.py`, no network, no spend):
- Ground truth per clip in `data/annotations/` (barrier check, time, severity; clean stretches;
  checks not applicable). Only clips marked `done` are scored.
- A finding matches a barrier of the same check within ±1 s. Precision and recall per check.
- Baseline: Muse Spark 1.3 on the raw video with no tools and no tracking (`baseline-v1`), scored the
  same way, against the agent run frozen as `v1`.

| Check | Agent precision | Agent recall | Baseline precision | Baseline recall |
|---|---|---|---|---|
| _pending_ | | | | |

## Privacy
- Faces are blurred locally before any frame goes to a model. Raw videos never leave the machine and
  are never committed; on the deployed server, raw uploads are deleted when their job ends.
- Metadata (including the phone's GPS) is stripped from every derived file (`-map_metadata -1`).
- Published frames and the report video have faces and license plates blurred.
- The API serves only `proxy.mp4`, rendered frames and mask PNGs, matched against a fixed pattern.

## Cost and caching
Every model call is cached by (video hash, model, prompt, params) under `data/cache/`, and logged with
its provider, model and usage to `data/out/usage.jsonl`. Re-runs are free. A 24 s clip costs about
$0.40 end to end (SAM ~$0.29 for 14 phrases at 5 fps, agent ~$0.10). Each job has a $1 cap checked
before any paid call; the deployed server also has daily and total caps.

## Run it locally

Windows + micromamba (`environment.yml`; `setup.ps1` creates the `accesswalk` env).

```
copy .env.example .env        # fill in MODEL_API_KEY, BASETEN_*, FIREWORKS_*
micromamba run -n accesswalk python scripts/check_setup.py
micromamba run -n accesswalk uvicorn accesswalk.api:app --app-dir backend --port 8010
micromamba run -n accesswalk npm --prefix frontend ci
micromamba run -n accesswalk npm --prefix frontend run dev:http
```

Tests: `micromamba run -n accesswalk python -m pytest backend/tests` and `npm --prefix frontend test`
(no network; recorded fixtures).

### Demo route (always runs, $0)
The demo route is `PXL_20261029_230808382` (24 s, sidewalk to a flight of steps). Its SAM, agent and
recheck calls are all cached, so uploading it, or its GPS-stripped copy
(`ffmpeg -i in.mp4 -map 0:v:0 -map 0:a:0? -c copy -map_metadata -1 out.mp4`), completes in a few
seconds with no paid call. This was checked with every model host unreachable. "Try a sample route"
on the upload page opens its finished report with no upload at all (`VITE_SAMPLE_REPORT_ID`).

## Deploy (Modal)
Live: https://rafi-tahmid--accesswalk-web.us-east.modal.run (sample route and reports; uploads need the passcode).

One Modal app serves the API and the built UI on one URL, on CPU only, scaling to zero. It is public
and read-only: sample route, reports, blurred media. Uploads need a passcode, and they stop once the
spend caps are used ($1 per job, $5 a day, $10 in total). The data volume holds blurred media and
model caches only: no raw video, no `sam.mp4`, no face-only proxy.

```
modal token new
modal secret create accesswalk --from-dotenv .env
modal secret create accesswalk-upload ACCESSWALK_UPLOAD_PASSCODE=<16+ random characters>
cd frontend && VITE_SAMPLE_REPORT_ID=<report_id> npx vite build --mode http && cd ..
micromamba run -n accesswalk python scripts/deploy_bundle.py PXL_20261029_230808382 --twin data/out/demo/PXL_20261029_230808382.mp4 --upload
micromamba run -n accesswalk modal run deploy/modal_app.py --video data/out/demo/PXL_20261029_230808382.mp4
micromamba run -n accesswalk modal deploy deploy/modal_app.py
```
The `modal run` step replays the demo upload on the server with no keys and every model host
blocked; it passes only if everything comes from the cache. The laptop setup above stays the
offline fallback for the live demo.

## Limitations
- Phone video flattens depth: heights, slopes and clear widths are estimates, always marked for
  manual checks. A MapAnything spike (metric 3D from frames) passed on width repeatability only,
  without a tape-measure check yet, so no geometry tool ships.
- SAM does not localize ramps or curb ramps directly; the agent judges them from stairs, handrail,
  curb and tactile-paving tracks and their keyframes.
- Outdoor routes only, filmed by one person on one phone. The clips are silent, so narration
  (location tags from Muse Voice Transcribe) was dropped.

## Built during the hackathon
Everything in this repo was written during the build window, starting with the first commit on
Oct 28, 2026 (see `git log`), with no imported code. The day-by-day task list and session log are in
`PROGRESS.md`; the working rules are in `CLAUDE.md`. Code was written with Claude Code (pipeline and
frontend as two parallel sessions). The videos were filmed for this project; raw footage, audio and
unblurred frames are never committed.
