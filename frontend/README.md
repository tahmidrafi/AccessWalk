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
tracked. Boxes are interpolated linearly between a track's boxes on consecutive
SAM frames and redrawn on every video frame (requestVideoFrameCallback); across a
gap in the track, and at its end, the last box holds for one SAM frame (200 ms at
5 fps) with no extrapolation. On a track's keyframe the
SAM mask is drawn instead of the box when `mask_url` is set. Timeline marks,
Previous/Next finding and each card's "Show in video" pause the video on the
cited frame; the playhead, "In view now" panel (a polite live region) and
in-view rings follow playback. A captions track (CC) generated from the findings
names each one while it is on screen.

## PDF export

"Download PDF" opens the browser's print dialog ("Save as PDF"); the default file
name is the report title and date. The print stylesheet keeps the verdict,
disclaimer, findings with their cited frames and boxes, the checks table and the
provenance, and leaves out the video player, timeline and controls. Chrome/Edge
write a tagged PDF: headings become the outline ("Route verdict: ...",
"Finding 1: ..."), frames are figures with their alt text, and the checks table
keeps its header cells. Checked with headless Chrome `--print-to-pdf` (4 pages
for the mock).

## Upload and job status

Routes: `/` upload, `/jobs/<job_id>` status, `/reports/<report_id>` report (History
API paths, so a report keeps its `#finding-...` links; a static host needs an SPA
fallback to index.html). The UI talks to the API through `src/api/client.ts`,
against `src/schema/api.schema.json` (types: `npm run gen:types`).

Two clients, picked at build time in `src/api/index.ts`:

- **Mock** (default): `src/api/mockClient.ts`. Nothing is uploaded or fetched.
- **HTTP**: `src/api/httpClient.ts`, with `VITE_ACCESSWALK_API=http`. `fetch` for
  reads, `XMLHttpRequest` for the upload (progress events). Error bodies become
  `ApiError` with the API's code; network failures stay `TypeError` so pages
  retry. `VITE_ACCESSWALK_API_BASE` sets the API origin when it differs from
  the page's (report media URLs are then prefixed too).

Against a local backend: start it from `backend/` with
`micromamba run -n accesswalk uvicorn accesswalk.api:app --port 8010`, then
`npm run dev:http` (mode file `.env.http`: HTTP client, dev server proxies `/api`
and `/media` to 127.0.0.1:8010). `ACCESSWALK_LIVE_API=http://127.0.0.1:8010 npm test`
also runs `src/api.live.test.ts`: read-only routes only (health, report list,
each report, its frames and a video byte range, a 404), no uploads.

The mock checks the file on the device (type, size, duration
from the file's metadata), simulates the upload, and plays a job out from the
mocks in `src/mock/api/` (queued, then ingest, segment, inventory, review,
report, done in about 20 s; polled every 2 s as the contract asks). "Demo
outcome" on the upload page picks the ending: report ready, over budget (stops
after ingest, nothing charged), pipeline error (during review), or an upload
rejected with 400 or 413. A finished job links to its report via `report_url`.

For the live demo, "Try a sample route" on the upload page opens a finished report
straight away, with no upload: the newest one in the report list that has findings
(`pickSampleReport`). If the list can't be loaded the page says so. The expected
processing time next to the upload button comes from `EXPECTED_PROCESSING` in
`src/lib/jobs.ts`, a fixed estimate for now.

Accessibility: errors are announced (`role="alert"`) and focused, with the
server message plus what to do next; field errors sit on the field
(`aria-invalid`, `aria-describedby`). Focus moves to the new page's heading
after in-app navigation, to "Cancel upload" while uploading, and to the outcome
when a watched job ends. The status line is a polite live region that changes
only with the stage, not on every poll. Lighthouse accessibility 100 on the
upload page, a finished job, an over-budget job and the report (Oct 29).

## Accessibility

Landmarks and a skip link; one `h1`, an `h2` per section, an `h3` per finding.
Severity and "verify manually" are text + shape, never colour alone. Timeline
marks are links in route order. Native video controls (keyboard-operable),
labelled Previous/Next buttons, captions for the findings, no autoplay; smooth
scrolling only without reduced motion.
Contrast meets WCAG AA in light and dark mode; honours reduced motion and
forced colours. Lighthouse accessibility: 100 (mobile, Oct 29, with the video player).
