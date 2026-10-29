# AccessWalk frontend

React + TypeScript (Vite) report page. Renders `src/mock/report.json` until the
upload/job flow is wired (`d6-fewire`).

The contract is `src/schema/report.schema.json` (exported from
`backend/accesswalk/schemas.py` by Session A). `src/types/report.ts` is generated
from it; regenerate after a schema change with `npm run gen:types`.

## Run

```
micromamba run -n accesswalk npm --prefix frontend ci
micromamba run -n accesswalk npm --prefix frontend run dev
```

`npm test` checks the mock against the JSON Schema and that every finding cites
a real track and frame. `npm run lint` includes the jsx-a11y rules.

Install with `npm ci`. The env's npm 10.8 crashes (`edgesOut`) when it has to
resolve the dependency tree itself, so to add or upgrade a package use npm 11+
(any recent Node) to update `package-lock.json`, then `npm ci` in the env.

## Evidence media in dev

Findings point at `/media/<video sha256>/frames/<i>.jpg`, tracks may carry a
`mask_url` (keyframe mask PNG), and the video is `/media/<sha>/proxy.mp4`. The dev
server serves those read-only from `data/cache/` (git-ignored), with byte ranges
so the video can seek. Frames are face- and plate-blurred; `proxy.mp4` is
face-blurred only, so it is fine locally but must not be published as is. In a git worktree the cache is in the main
checkout: put its path in `frontend/.env.local` (git-ignored):

```
ACCESSWALK_MEDIA_DIR=D:/meta/AccessWalk/data/cache
```

Without frames the page still renders each box on a placeholder; without the
video the timeline marks link to each finding's evidence instead.

## Video and timeline

The video plays with the objects behind the findings drawn on top while they are
tracked (box held for one SAM frame, 200 ms at 5 fps). On a track's keyframe the
SAM mask is drawn instead of the box when `mask_url` is set. Timeline marks,
Previous/Next finding and each card's "Show in video" pause the video on the
cited frame; the playhead, "In view now" panel (a polite live region) and
in-view rings follow playback. A captions track (CC) generated from the findings
names each one while it is on screen.

## Accessibility

Landmarks and a skip link; one `h1`, an `h2` per section, an `h3` per finding.
Severity and "verify manually" are text + shape, never colour alone. Timeline
marks are links in route order. Native video controls (keyboard-operable),
labelled Previous/Next buttons, captions for the findings, no autoplay; smooth
scrolling only without reduced motion.
Contrast meets WCAG AA in light and dark mode; honours reduced motion and
forced colours. Lighthouse accessibility: 100 (mobile, Oct 29, with the video player).
