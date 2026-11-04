# README media

Images and GIFs used at the top of the main README. **Blurred footage only**: every frame here comes from
the pipeline's face- and plate-blurred outputs (`proxy.mp4`, rendered `frames/`), never from `data/raw/`
or anything with a `.raw` name. Strip metadata from anything re-encoded (`-map_metadata -1`).

| Slot in README | File | What it shows |
|---|---|---|
| 1 · hero | `hero.gif` | Walkthrough with SAM tracking overlay (boxes / masks, stable ids) |
| 2 · how it works | `pipeline.png` | Pipeline: ingest + blur → SAM 3.1 tracks → inventory → two-tier review → report |
| 3 · results | `results.png` | Results card: two-tier 79% recall / 97% precision vs 64% / 95% video-only |
| 4 · left | `sam-tracks-steps.gif`, `sam-tracks-slab.gif` | What SAM tracks: the demo-route steps and a heaved-slab clip, side by side |
| 4 · right | `report-finding.png` | What the report says about the steps (finding card with its box) |

The slots are wired into `README.md`; `report-finding.png` is a headless-Chromium screenshot of the pinned demo report (finding 3, steps) served locally from `frontend/dist`.
