# README media

Images and GIFs used at the top of the main README. **Blurred footage only**: every frame here comes from
the pipeline's face- and plate-blurred outputs (`proxy.mp4`, rendered `frames/`), never from `data/raw/`
or anything with a `.raw` name. Strip metadata from anything re-encoded (`-map_metadata -1`).

| Slot in README | File | What it shows |
|---|---|---|
| 1 · hero | `hero.gif` | Walkthrough with SAM tracking overlay (boxes / masks, stable ids) |
| 2 · how it works | `pipeline.png` | Pipeline: ingest + blur → SAM 3.1 tracks → inventory → two-tier review → report |
| 3 · results | `results.png` | Results card: two-tier 79% recall / 97% precision vs 64% / 95% video-only |
| 4 · left | `sam-tracks.png` | What SAM tracks (one frame, tracked objects with ids) |
| 4 · right | `report-finding.png` | What the report says about the same moment (finding card) |

Each slot is an HTML comment in `README.md` with the `<img>` tag inside; uncomment it when the file lands.
