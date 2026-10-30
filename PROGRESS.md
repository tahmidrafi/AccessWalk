# AccessWalk progress

Task list for Claude Code sessions. IDs match the owner's tracker: never rename them.
`[ ]` to do · `[~]` in progress · `[x]` done · `[-]` dropped (add a reason). Owner: A = pipeline session, B = frontend session, You = Tahmid.

## D1 · Mon 10/26
- [x] `d1-accounts` Accounts and partner credits: Meta, Modal, Baseten, Fireworks (Setup, You)
- [x] `d1-env` micromamba env, setup.ps1, check_setup passing (Setup, You)
- [x] `d1-claudemd` CLAUDE.md v1: rules, pipeline, 8 checks, API facts, schedule (Setup)

## D2 · Tue 10/27
- [x] `d2-film1` Film first batch of outdoor clips (Data, You)
- [x] `d2-agents101` Watch Agents 101 workshop (Setup, You)

## D3 · Wed 10/28
- [x] `d3-review` Check clip specs (resolution, fps, codec, metadata) (Data)
- [x] `d3-claudemd2` CLAUDE.md v2: ingest outputs, parallel sessions, providers, revised schedule (Setup)
- [x] `d3-git` git init, first commit, public GitHub repo (Setup, A)
- [x] `d3-ingest` Ingest: local face blur, then sam.mp4 (5 fps), proxy.mp4 (H.264), audio.wav, meta.json; GPS stripped (Pipeline, A)
- [x] `d3-samclient` SAM 3.1 client + Python output parser + tests (Pipeline, A)
- [x] `d3-samfirst` First SAM run: 1 clip × 3 phrases, confirm cost (Pipeline, A)
- [x] `d3-usage` Cache by video hash + usage logging to usage.jsonl (Pipeline, A)
- [ ] `d3-agents102` Watch Agents 102 workshop (part 2) (Setup, You)

## D4 · Thu 10/29
- [x] `d4-samall` Pick barrier phrases on 2 clips (prompt the barrier itself, e.g. "raised sidewalk slab", "cracked pavement", not only its cause), estimate cost, then SAM all phrases × 11 clips (Pipeline, A)
- [x] `d4-inventory` Inventory: dedupe tracks, best keyframe, face/plate blur (Pipeline, A)
- [x] `d4-schema` Freeze schemas.py, export JSON Schema + mock report.json (Pipeline, A)
- [x] `d4-blurcheck` Face blur checked on a clip with a real person; blur made two-pass with gap bridging (Privacy, A)
- [~] `d4-annotate5` Annotation format + annotate 5 clips (Data, You) -- format, README, checker + clip-1 draft done (A); 5 clips to annotate (You)
- [x] `d4-phrasegaps` Ramp/curb-ramp phrases: SAM localizes no ramp; "tactile paving" added (curb-ramp pad), "ramp"/"curb ramp" dropped; ramps judged by the agent (Pipeline, A)
- [x] `d4-fescaffold` Vite scaffold + report page on mock data (Frontend, B)

## D5 · Fri 10/30
- [x] `d5-agentloop` Agent loop on Baseten (Muse Spark Open) with tools (Pipeline, A)
- [x] `d5-validator` Citation validator: drop findings without track + frame (Pipeline, A)
- [x] `d5-rules` Rules YAML for the 8 checks (Pipeline, A)
- [x] `d5-fireworks` Fireworks failover switch (config only) (Pipeline, A)
- [ ] `d5-filmgaps` Film 6–10 gap clips (Data, You)
- [ ] `d5-fwworkshop` Fireworks workshop (Setup, You)
- [x] `d5-fetimeline` Findings timeline + mask overlays on video (Frontend, B)

## D6 · Sat 10/31
- [ ] `d6-quality` Agent quality: re-checks, confidence (Pipeline, A)
- [ ] `d6-transcribe` Voice Transcribe → location tags (optional; handles silent clips) (Pipeline, A)
- [ ] `d6-verdict` Route-level verdict (Pipeline, A)
- [~] `d6-api` FastAPI: upload, job status, report JSON, /media frames (Pipeline, A) -- contract + app done; live upload run pending OK
- [ ] `d6-plateblur-proxy` Re-render proxy.mp4 with plates blurred from SAM `license plate` tracks: interpolate boxes between the 5 fps SAM frames, pad ~20%, hold across short gaps. Blocks deploy and the demo video (Privacy, A)
- [ ] `d6-blur-fp` Face-blur false positives: at threshold 0.5 YuNet puts 150-800 px "faces" on pavement, cars and the walkway in the Oct-29 clips (blurring evidence, protecting no one). Reject implausible boxes (landmark geometry, size vs position, higher score for big boxes), re-ingest, re-check coverage (Privacy, A)
- [ ] `d6-mapanything` MapAnything spike on Modal (2 h cap): go/no-go (Pipeline, A)
- [ ] `d6-fewire` Upload + job status + report wired to real JSON (Frontend, B)
- [ ] `d6-annotatenew` Annotate the new gap clips (Data, You)

## D7 · Sun 11/1
- [ ] `d7-annotateall` All clips annotated (15–25 total) (Data, You)
- [ ] `d7-eval` Eval harness: precision/recall per check (Pipeline, A)
- [ ] `d7-baseline` Baseline: Muse Spark 1.3 on raw video, no tools (Pipeline, A)
- [ ] `d7-fixworst` Fix the worst check; drop weak checks (Pipeline, A)
- [ ] `d7-deploy` Deploy end to end (backend + frontend) (Setup)

## D8 · Mon 11/2
- [ ] `d8-geometry` measure_geometry agent tool (only if spike is a go) (Pipeline, A)
- [x] `d8-pdf` PDF export of the report (Frontend, B)
- [ ] `d8-readme` README, architecture diagram, “Built during the hackathon” (Demo)
- [ ] `d8-demoroute` Cached demo route that always runs (Demo)

## D9 · Tue 11/3
- [ ] `d9-freeze` Feature freeze at noon (Demo)
- [ ] `d9-script` Demo script (Demo, You)
- [ ] `d9-video` Record 3-minute demo video (Demo, You)

## D10 · Wed 11/4
- [ ] `d10-fixes` Final fixes (Pipeline)
- [ ] `d10-submit` Submit by 5 PM CT (deadline 8 PM CT) (Demo, You)
- [ ] `d10-postx` Post the demo on X (Most Viral, engagement through Nov 8) (Demo, You)

## Milestones
- M1 Env, accounts, credits ready (D1) — done
- M2 First real SAM tracks from a clip (D3) — done
- M3 Report schema frozen; frontend unblocked (D4) — done (Oct 28 evening)
- M4 Agent produces cited findings end to end (D5) — done (Oct 29 evening, clip 1, all turns on Baseten)
- M5 Geometry spike go/no-go (D6)
- M6 Eval numbers vs raw-video baseline (D7)
- M7 Feature freeze, noon (D9)
- M8 Submitted, 5 PM CT (D10)

## Log
- 2026-10-28: plan set up; 11 clips filmed (silent, no narration); CLAUDE.md v2; Fireworks model ID set in .env.
- 2026-10-28 (Session A): M2 reached. git init + public repo pushed (owner, SSH alias); ingest.py (local YuNet face blur, GPS/metadata strip, sam.mp4/proxy.mp4/audio.wav/meta.json) verified on PXL_20261027_211833467 (1080x1920->720x1280, 111 frames, GPS stripped; 0 faces in this clip, so blur geometry covered by a unit test, not a real face); SAM client + grammar parser + cache (by video hash, keyed on full request metadata) + usage.jsonl logging, 18 tests passing, ruff clean; first SAM run (tree root=19 recs/2 tracks, trash bin=8/1, handrail=0, $0.0666, frame-alignment confirmed vfp==111, box dims==720x1280, re-run free via cache). SAM confidence (metadata.include_confidence) now enabled for d4; the one run clip predates it and will be re-segmented as part of d4-samall. Blocked: none. Note: local main ahead of origin (owner pushes). Next: d4 (SAM all phrases x 11 clips, inventory, freeze schemas.py + meta: populate proxy.n_frames; confirm face blur on a clip with people).
- 2026-10-28 evening (Session A): d3 review: ingest now fails on decode errors and records proxy.n_frames. d4-samall phrase test (2 clips: 211833467 heaved slab, 220842365 vegetation narrowing; 7 phrases, $0.3654 = estimate): keep `raised sidewalk slab` (localizes heaved/tilted slabs, 8 tracks, 0 on the clean clip; also fires on some ordinary slabs, so the agent must verify), `overgrown vegetation` (edge encroachment); `sidewalk` only as context; drop `uneven sidewalk` and `cracked pavement` (one whole-frame box per frame, inventory flags them as duplicates of `sidewalk`), `grass` (noisy duplicate of vegetation), `tree root` optional (beside the slab, not on it). Not yet run on all 11 clips: phrase list needs owner OK. Face blur: campus clip 225049085 has a real passer-by; YuNet at 0.6 caught them on 47/140 frames, leaving gaps of up to 19 unblurred frames (never sent to any model). Fix: detect pass, then plan (hold +-4 frames, bridge gaps <= 1 s with the hull of matched boxes), then blur pass; threshold 0.5; drop face boxes wider than half the frame (0.5 produced frame-sized false positives on clip 1). Blur-only change, so INGEST_VERSION unchanged and SAM cache valid; all clips with detections re-ingested; campus frames verified blurred incl. the old gap. d4-schema frozen (M3): schemas.py with grounding validator, JSON Schema + mock from clip 1 real tracks (18 tracks, 3 hand-written findings, agent_provider=mock). d4-inventory: build_tracks, id stitching, cross-phrase dedupe, plate-blurred keyframe JPEGs, inventory.json; 34 tests, ruff clean. Blocked: none. Next: OK phrase list -> d4-samall on 11 clips (~$0.33/phrase), then inventory on all.
- 2026-10-28 late (Session A): d4-samall done: 13 phrases (backend/accesswalk/phrases.py, mapped to the 8 checks) x 11 clips, $4.1698 (= estimate; total SAM spend to date $4.60, 23,009 frames billed). Hits: raised sidewalk slab only on clip 1 (the heaved slab); handrail good (stairs, ramps, railed walkways, 7 clips); doorknob boxes the lever/pull handles on the 2 entrance clips (no round knobs filmed: negatives only); stairs on 224805654 (indoor staircase); pole includes a utility pole on the sidewalk (214453883) but also door frames; car = cars on the road only (none on a sidewalk); trash bin weak (3 small hits); curb usable as context; license plate tracks plates on 4 clips. Misses: ramp = 0 and curb ramp = 0 on every clip, although clips show both -> d4-phrasegaps. d4-inventory done: inventory.json + plate-blurred keyframe JPEGs for all 11 clips (284 tracks, 282 after dedupe); plate blur checked on a rendered frame. Blocked: none. Next: d4-phrasegaps (needs OK), d5 agent loop.
- 2026-10-28 late (Session A): d4-phrasegaps test, $0.2384 (= estimate): "wheelchair ramp", "sloped walkway", "curb cut", "tactile paving" on 225049085 + 002145281. "sloped walkway" = one whole-walkway box per frame on the campus ramp (context only, like "sidewalk"); "curb cut" on 002145281 boxed ordinary curb edges and a slab lip (false positives); the other two found nothing. CORRECTION: the tactile-paver curb ramp is in 224931168, not 002145281 (I misread the montage order), so curb cut/tactile paving were tested on a clip without one; the d4-samall log line above has the same error. Options: test "tactile paving" + "curb cut" on 224931168 (~$0.03), and/or let the agent judge ramps from handrail/curb track keyframes. SAM spend to date $4.84.
- 2026-10-28 late (Session A): d4-phrasegaps on 224931168 (the real curb-ramp clip), $0.0462 (= estimate): "tactile paving" finds the detectable-warning pad (1 track, 0.6-6.6 s, conf 0.72) and nothing on the 2 clips without one -> usable as curb-ramp-present evidence (absence is not proof of a missing ramp: older ramps have no pad). "curb cut" boxes the curb/ramp area here but plain curb edges on 002145281 -> agent-verified at best. "wheelchair ramp" = 0 even beside a railed ramp; with "ramp"/"curb ramp" = 0 on all clips, SAM does not localize ramps: plan is for the agent to judge ramps from handrail/stairs/curb keyframes. Proposed (not done, needs OK): add "tactile paving" to phrases.py and run it on the other 10 clips (~$0.32); drop "ramp" and "curb ramp" from future runs. SAM spend to date $4.89.
- 2026-10-28 late (Session A): d4-phrasegaps closed. phrases.py: + "tactile paving" (missing_curb_ramp evidence), - "ramp", - "curb ramp" (12 phrases now). Ran tactile paving on the other 10 clips: $0.2578 (estimate $0.3174; 2 clips already cached), 0 hits, so the one track on 224931168 is the only one (no false positives). Inventory rebuilt for all 11 clips. 34 tests, ruff clean. SAM spend to date $5.15. Open: agent must judge ramps (no SAM detector); no round doorknob, car-on-sidewalk or missing-curb-ramp positives filmed yet (d5-filmgaps). Blocked: none.
- 2026-10-28 late (Session B): d4-fescaffold done: Vite + React + TS report page on mock report (verdict, findings with cited frame + box overlay, timeline, checks table, provenance); a11y (keyboard, contrast, screen-reader labels, Lighthouse a11y 100); types generated from report.schema.json; vitest checks mock vs schema and citations. Env npm 10.8 can't resolve deps (edgesOut): lockfile made with npm 11, env uses npm ci. Blocked: none. Next: d5-fetimeline.
- 2026-10-29 (Session A): d6-api task added (Sat). d4-annotate5 format done: annotations.py (barriers: check, t in seconds, sev, note, verify; clean ranges; not_applicable; draft/done, only done is scored, +-1 s match), data/annotations/README.md, scripts/annotate.py (new/check), clip-1 example left as draft for the owner to verify; owner annotates 5 clips tonight. d5-rules (rules.yaml: 8 checks, evidence phrases, keyframe-judged ramps/curb ramps, severity bins, references, pitfalls; phrases.py derives from it) and d5-validator (grounding gate + finalize) done; 45 tests, ruff clean. d5-agentloop: design proposed, waiting for OK before any Baseten/SAM call. Blocked: none.
- 2026-10-29 (Session A): agent design approved with changes. Push from here failed (SSH key needs the owner's passphrase): owner pushes. Built offline: llm.py (baseten -> fireworks failover, closed Muse Spark 1.3 only with allow_closed and marked in RunInfo.used_closed_fallback; cache key = provider + model + messages + tool defs + params; usage.jsonl per call), agent.py (get_track with mask ground-contact on-sidewalk share, view_frame, recheck_with_sam, cite_finding via validator, finish; parallel tool calls; 20-turn cap logged to data/out/agent_runs.jsonl), masks.py. schemas: RunInfo.used_closed_fallback (additive; JSON Schema + mock regenerated, Session B to regenerate types). 56 tests, ruff clean. Smoke test (approved): Baseten and Fireworks both accept temperature 0, image input and image + tools + parallel_tool_calls; image ~1.1k input tokens at 512 px; cost $0.0031 Baseten (at assumed $1.25/$4.25 per M) + $0.0036 Fireworks. d5-fireworks done (switch tested). Blocked: mask decoding needs meta-sam-parser installed (pip install was blocked by the permission check; in environment.yml), so on-sidewalk is reported unavailable until then. Next: 1-clip agent run (needs OK).
- 2026-10-29 (Session B, merged by A): d5-fetimeline done: route player plays proxy.mp4 with cited objects drawn while tracked (box held one SAM frame) and the SAM mask (mask_url) on keyframes; timeline marks, prev/next finding and "Show in video" pause on the cited frame; playhead, in-view cards and an "In view now" live region follow playback; WebVTT captions from findings, no autoplay, reduced-motion aware; Lighthouse a11y 100. Dev /media route serves proxy.mp4 with byte ranges plus jpg/png (masks). Tests: SAM-frame snapping, box hold, in-view, prev/next, captions, mask-vs-box. Note: proxy.mp4 is face-blurred but not plate-blurred yet (d6-plateblur-proxy).
- 2026-10-29 evening (Session A): owner pushed and installed meta-sam-parser. masks.decode_raster fixed (payload must include the marker) + disk cache (a 1024x574 sidewalk mask takes ~5 s to decode). On-sidewalk measure on clip 1 real masks: trash-bin-0 0.00 on all 8 sampled frames (beside, correct); far red post pole-1 0.42-1.0 (0.85 at f34; far-away contacts, check a near frame). Merged Session B f8f9d65 (d5-fetimeline); branch tip has 2 newer commits (box interpolation, regenerated types) not merged. 58 backend + 14 frontend tests pass (frontend run via a temporary junction to the B worktree node_modules). Push from here failed again (publickey). Added d6-plateblur-proxy. Mask PNGs: full-frame 720x1280 RGBA, alpha 0/255 (40 on clip 1). Clip-1 agent run (approved <= $1): $0.1414, 6/20 turns, finished; tools get_track 14, view_frame 12, cite_finding 2, finish 1, recheck 0; 2 findings, both surface_damage (f1 medium slab-4 f60 12.0 s; f2 high slab-3 f70 14.0 s), 0 rejections, verdict likely_blocked; vs the unverified draft annotation: 2 of 3 barrier ranges matched (the 9.5-11.5 s one only via the 1 s tolerance), the low 16.5-19 s one missed, 0 findings in clean ranges. Issue: Baseten rejects > 8 images per request (400 'Too many images: 12 (max 8)'), so turns 5-6 failed over to Fireworks (same open model, no closed fallback). Fix needed: keep <= 8 images in context. Cost is an upper bound: Baseten cached tokens (up to 12.5k/turn) are billed at full price in our estimate.
- 2026-10-29 late (Session A): M4 reached. Agent sends at most 8 images per request (latest views as images, older ones as captions; at most 8 views per turn) after Baseten's 400 'Too many images: 12 (max 8)'. llm.chat fails over to Fireworks only on 5xx, 429 and timeouts; any other error (4xx, auth, plain connection errors) raises ProviderError. Merged Session B branch tip 76f7781 (box interpolation, regenerated types; conflicts from the rebase resolved to the tip, frontend/ identical to it). Tests: backend 66, frontend 21, tsc clean. Clip-1 re-run (cap $0.50): $0.1446, 6/20 turns, all 6 on Baseten (meta-models/muse-spark-open-1026, no failover, no closed fallback); tools get_track 14, view_frame 12, cite_finding 3, finish 1; 3 surface_damage findings at 10.8 s (medium), 11.6 s (high), 12.0 s (medium), 0 rejections. vs the draft annotation: 2 of 3 barrier ranges hit, the low 16.5-19 s cracks missed, 0 in clean ranges; the first run's 14.0 s heave was not cited this time (run-to-run variance at temperature 0). Evidence notes say 'in the red box' (view_frame's colour), which the report's overlay may not match. main ahead of origin (owner pushes).
- 2026-10-29 (Session B): d8-pdf done on claude/frontend-pdf-export: "Download PDF" (browser print-to-PDF, file named after report + date) and print stylesheet (verdict, findings with cited frames + boxes, checks, provenance; no video/timeline/controls; colours printed exactly; findings kept whole). Tagged PDF checked with headless Chrome: 4 pages, outline "Route verdict: …" / "Finding n: …", figures with alt text, table headers; Lighthouse a11y 100. Blocked: none.
- 2026-10-29 late (Session A): d8-pdf fast-forwarded (878c06e; backend 66, frontend 22, tsc clean). Evidence notes: prompt forbids box colours/labels; validator strips 'in the red box'-style phrases (keeps sentence case, rejects notes left too short); tested on the real phrase from the clip-1 run. d6-api: contract first (api_models.py: Health, JobStatus with states queued/running/done/failed and stages ingest/segment/inventory/review/report, ReportList, ErrorResponse codes), exported to frontend/src/schema/api.schema.json + frontend/src/mock/api/*.json (one per job state) with a sync test. Then FastAPI app (api.py) + job store and pipeline (jobs.py): one job at a time, status persisted under data/out/jobs (unfinished jobs marked failed on restart), uploads .mp4/.mov <= 300 MB and <= 2 min to data/raw/uploads (never served), over_budget check before any paid call (ACCESSWALK_MAX_JOB_USD, default $1; agent open-weight only, $0.50 cap), /media serves only proxy.mp4 (Range/206), frames/<i>.jpg and masks/<name>.png. 77 tests (fake pipeline); live server check on real data: health, reports, report, frame, proxy range, mask OK; meta.json 404. Not run: a real upload through SAM + agent (paid). proxy.mp4 is not plate-blurred yet: d6-plateblur-proxy blocks deploy. Note: port 8765 is used by a local WSL service.
- 2026-10-29 night (Session A): live upload through the API (PXL_20261029_230808382, 24 s; port 8000 and 8001 are taken by another local app, ran on 8010): done in 398 s, $0.388 (SAM $0.288 for 12 phrases x 120 frames, agent $0.100, 6 turns all on Baseten, no closed fallback), 2 findings (not reviewed; clip not annotated). Wall clock: upload+probe 0.6 s, ingest 91.5 s, segment 84.2 s, inventory 19.3 s, review 202.9 s (incl. writing the report; 144 s of it between the agent's first and second model call = get_track decoding ~5 s full-frame sidewalk masks). Speed levers for the demo: pre-decode sidewalk masks during segment, cheaper face-detect pass. Ingested the other 10 Oct-29 clips (1,944 SAM frames total incl. the upload's 120 is 2,064). Face detections on all 11 Oct-29 clips, but most large boxes (150-800 px) are false positives on pavement/cars/walkway, so blur patches land on evidence (new task d6-blur-fp); real people seen are small and distant (blurred); no close-up person seen in sampled frames (not an exhaustive check). Readable plates on parked cars in several clips (231904710, 231822465, 225010831, 233500113): d6-plateblur-proxy. 11 blank annotation templates written (annotate.py new now writes empty lists + an ignored _example_barrier). stairs found the outdoor steps on 230808382 (1 track, 7.4-19.4 s). SAM estimate (not run): 12 phrases x 10 remaining clips (1,944 frames) = $4.67. Proposed phrase test (not run): fallen branch on 225609313, traffic cone + traffic barrel on 231529011, construction barrier on 231652382 ($0.15), optional parking block on 231822465 + 231904710 ($0.08). Next: d6-plateblur-proxy.
