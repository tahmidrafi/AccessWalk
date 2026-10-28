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
- [~] `d3-git` git init, first commit, public GitHub repo (Setup, A)
- [ ] `d3-ingest` Ingest: local face blur, then sam.mp4 (5 fps), proxy.mp4 (H.264), audio.wav, meta.json; GPS stripped (Pipeline, A)
- [ ] `d3-samclient` SAM 3.1 client + Python output parser + tests (Pipeline, A)
- [ ] `d3-samfirst` First SAM run: 1 clip × 3 phrases, confirm cost (Pipeline, A)
- [ ] `d3-usage` Cache by video hash + usage logging to usage.jsonl (Pipeline, A)
- [ ] `d3-agents102` Watch Agents 102 workshop (part 2) (Setup, You)

## D4 · Thu 10/29
- [ ] `d4-samall` Estimate cost, then SAM all phrases × 11 clips (Pipeline, A)
- [ ] `d4-inventory` Inventory: dedupe tracks, best keyframe, face/plate blur (Pipeline, A)
- [ ] `d4-schema` Freeze schemas.py, export JSON Schema + mock report.json (Pipeline, A)
- [ ] `d4-annotate5` Annotation format + annotate 5 clips (Data, You)
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
- M2 First real SAM tracks from a clip (D3)
- M3 Report schema frozen; frontend unblocked (D4)
- M4 Agent produces cited findings end to end (D5)
- M5 Geometry spike go/no-go (D6)
- M6 Eval numbers vs raw-video baseline (D7)
- M7 Feature freeze, noon (D9)
- M8 Submitted, 5 PM CT (D10)

## Log
- 2026-10-28: plan set up; 11 clips filmed (silent, no narration); CLAUDE.md v2; Fireworks model ID set in .env.
