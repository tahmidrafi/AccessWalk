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

## Evidence frames in dev

Findings point at `/media/<video sha256>/frames/<i>.jpg`. The dev server serves
those read-only from `data/cache/` (face- and plate-blurred frames written by the
inventory step; git-ignored). In a git worktree the cache is in the main
checkout: put its path in `frontend/.env.local` (git-ignored):

```
ACCESSWALK_MEDIA_DIR=D:/meta/AccessWalk/data/cache
```

Without frames the page still renders each box on a placeholder.

## Accessibility

Landmarks and a skip link; one `h1`, an `h2` per section, an `h3` per finding.
Severity and "verify manually" are text + shape, never colour alone. Timeline
marks are links in route order; activating one moves focus to its finding.
Contrast meets WCAG AA in light and dark mode; honours reduced motion and
forced colours. Lighthouse accessibility: 100 (mobile, Oct 28).
