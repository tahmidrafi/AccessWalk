import type { Finding } from '../types/report'
import { TierBadge } from './FindingCard'
import { Link } from './Link'

/** Eval numbers from the README (two-tier review, 22 labelled clips, 28 barriers). */
const STATS = [
  { n: '79%', label: 'of labelled barriers found' },
  { n: '97%', label: 'precision on 22 filmed routes' },
  { n: '8', label: 'accessibility checks' },
]

export function StatTiles() {
  return (
    <section className="stats band band-tint" aria-labelledby="stats-heading">
      <h2 id="stats-heading" className="visually-hidden">
        Results so far
      </h2>
      <ul className="stat-tiles">
        {STATS.map((s) => (
          <li key={s.label} className="stat">
            <strong className="stat-n">{s.n}</strong>
            <span className="stat-label">{s.label}</span>
          </li>
        ))}
      </ul>
      <p className="stats-note">
        Scored against hand-labelled barriers in 22 walkthrough clips (28 barriers). A small sample: read the numbers as
        indicative, not as a guarantee for your route.
      </p>
    </section>
  )
}

/** Small scene for an example card: steps (solid, cited box) or a curb (dashed, possible). */
function Thumb({ kind }: { kind: 'steps' | 'curb' }) {
  return (
    <svg className="preview-thumb" viewBox="0 0 120 160" aria-hidden="true" focusable="false">
      <rect width="120" height="160" fill="#7a8f5a" />
      {kind === 'steps' ? (
        <>
          <rect width="120" height="56" fill="#9a5a44" />
          <rect x="48" y="22" width="24" height="34" fill="#2f3b45" />
          <rect x="38" y="56" width="44" height="9" fill="#d6d1c7" />
          <rect x="32" y="65" width="56" height="9" fill="#c2bdb3" />
          <rect x="26" y="74" width="68" height="9" fill="#aea99f" />
          <polygon points="30,83 90,83 112,160 8,160" fill="#a9a59c" />
          <rect x="22" y="52" width="76" height="35" fill="none" stroke="#000" strokeWidth="5" />
          <rect x="22" y="52" width="76" height="35" fill="none" stroke="#ffd400" strokeWidth="2.5" />
        </>
      ) : (
        <>
          <polygon points="0,0 120,0 120,92 0,70" fill="#b3afa6" />
          <polygon points="0,70 120,92 120,104 0,82" fill="#d8d4cb" />
          <polygon points="0,82 120,104 120,160 0,160" fill="#3d3f42" />
          <rect x="6" y="62" width="108" height="48" fill="none" stroke="#000" strokeWidth="5" />
          <rect x="6" y="62" width="108" height="48" fill="none" stroke="#ffd400" strokeWidth="2.5" strokeDasharray="8 5" />
        </>
      )}
    </svg>
  )
}

const EXAMPLES: {
  tier: 'confirmed' | 'possible'
  title: string
  check: string
  at: string
  evidence: string
  cite: string
  thumb: 'steps' | 'curb'
}[] = [
  {
    tier: 'confirmed',
    title: 'Steps to the entrance with no ramp in view',
    check: 'Steps without a ramp',
    at: '0:12',
    evidence: 'Concrete steps are the only way to the door, with no ramp or level route in view.',
    cite: 'Cited evidence: track stairs-0 (seen 7.5 s to 19.5 s over 61 frames), frame 60.',
    thumb: 'steps',
  },
  {
    tier: 'possible',
    title: 'Curb step from the street with no ramp',
    check: 'Missing curb ramp',
    at: '0:05',
    evidence: 'Where the sidewalk meets the street there is a continuous curb step and no ramp cut visible.',
    cite: 'Seen by the raw-video pass only, with no tracked object behind it: check it on site.',
    thumb: 'curb',
  },
]

/** Two example findings, styled as on the report, so the two tiers read at a glance. */
export function ReportPreview({ sampleHref }: { sampleHref?: string }) {
  return (
    <section className="preview band band-tint" aria-labelledby="preview-heading">
      <h2 id="preview-heading">What a report looks like</h2>
      <p className="section-intro">
        A verdict for the whole route, then each finding on the frame it rests on. Confirmed findings cite an object SAM
        3.1 tracked; possible ones are leads to check on site and never set the verdict. Examples from the sample route.
      </p>
      <ul className="preview-cards">
        {EXAMPLES.map((e, i) => (
          <li key={e.title}>
            <article className={`finding preview-card tier-${e.tier} sev-high`} aria-labelledby={`preview-${i}`}>
              <div className="finding-body">
                <header className="finding-header">
                  <h3 id={`preview-${i}`}>
                    <span className="finding-number" aria-hidden="true">
                      {i + 1}
                    </span>
                    <span className="visually-hidden">Example finding, {e.tier}: </span>
                    {e.title}
                  </h3>
                  <dl className="finding-facts">
                    <div>
                      <dt>Check</dt>
                      <dd>{e.check}</dd>
                    </div>
                    <div>
                      <dt>Where</dt>
                      <dd>{e.at} into the clip</dd>
                    </div>
                  </dl>
                  <ul className="finding-flags" aria-label="Flags">
                    <li>
                      <TierBadge finding={{ tier: e.tier } as Finding} />
                    </li>
                    <li className="badge badge-sev sev-high">
                      <span className="sev-shape" aria-hidden="true" />
                      High severity
                    </li>
                  </ul>
                </header>
                <p className="finding-evidence">{e.evidence}</p>
                <p className="finding-cite">{e.cite}</p>
              </div>
              <Thumb kind={e.thumb} />
            </article>
          </li>
        ))}
      </ul>
      {sampleHref && (
        <p className="preview-more">
          <Link to={sampleHref} className="button">
            Open the full sample report
          </Link>
        </p>
      )}
    </section>
  )
}
