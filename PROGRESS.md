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
- [ ] `d4-annotate5` Annotation format + annotate 5 clips (Data, You)
- [~] `d4-phrasegaps` `ramp` and `curb ramp` found nothing on clips that show them (railed campus ramp 225049085; tactile-paver curb ramp + railed ramp at 224931168 ~1-3 s). Tested 4 alternates; none usable yet, see log (Pipeline, A)
- [ ] `d4-fescaffold` Vite scaffold + report page on mock data (Frontend, B)

## D5 · Fri 10/30
- [ ] `d5-agentloop` Agent loop on Baseten (Muse Spark Open) with tools (Pipeline, A)
- [ ] `d5-validator` Citation validator: drop findings without track + frame (Pipeline, A)
- [ ] `d5-rules` Rules YAML for the 8 checks (Pipeline, A)
- [ ] `d5-fireworks` Fireworks failover switch (config only) (Pipeline, A)
- [ ] `d5-filmgaps` Film 6–10 gap clips (Data, You)
- [ ] `d5-fwworkshop` Fireworks workshop (Setup, You)
- [ ] `d5-fetimeline` Findings timeline + mask overlays on video (Frontend, B)

## D6 · Sat 10/31
- [ ] `d6-quality` Agent quality: re-checks, confidence (Pipeline, A)
- [ ] `d6-transcribe` Voice Transcribe → location tags (optional; handles silent clips) (Pipeline, A)
- [ ] `d6-verdict` Route-level verdict (Pipeline, A)
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
- [ ] `d8-pdf` PDF export of the report (Frontend, B)
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
- M4 Agent produces cited findings end to end (D5)
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
