# README media

Images and GIFs used in the main README. **Blurred footage only**: every frame here comes from the
pipeline's face- and plate-blurred outputs (`proxy.mp4`, rendered `frames/`), never from `data/raw/` or
anything with a `.raw` name. Strip metadata from anything re-encoded (`-map_metadata -1`).
Licensed CC BY 4.0 (see the main README, "License").

| README section | File | What it shows |
|---|---|---|
| Top | `hero-barrels.gif`, `hero-steps.gif`, `hero-slab.gif` | Three walkthroughs with the SAM 3.1 tracking overlay |
| What the report shows | `report-finding.png` | The demo report's steps finding (frame and card), headless-Chromium screenshot of the local build at deviceScaleFactor 2 |
| How it works | `pipeline.png` | Pipeline card: walk, privacy, track, review, report |
| Results | `results.png` | Results card: two-tier 79% recall / 97% precision vs 64% / 95% video-only |
