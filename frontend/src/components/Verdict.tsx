import { NONE_CONFIRMED_TEXT, RATING_TEXT } from '../lib/labels'
import { findingAnchor } from '../lib/report'
import { isPossible, tierCounts, verdictDisplay } from '../lib/tier'
import { formatClock } from '../lib/time'
import type { Finding, Report } from '../types/report'

interface Props {
  report: Report
  /** Route order. */
  findings: Finding[]
  numberOf: Map<string, number>
  onGo: (f: Finding) => void
}

function FindingLinks({ items, numberOf, onGo }: { items: Finding[]; numberOf: Map<string, number>; onGo: Props['onGo'] }) {
  return (
    <ul>
      {items.map((f) => (
        <li key={f.finding_id}>
          <a
            href={`#${findingAnchor(f)}`}
            onClick={(e) => {
              e.preventDefault()
              onGo(f)
            }}
          >
            {numberOf.get(f.finding_id)}. {f.title}
          </a>{' '}
          at {formatClock(f.frame_ms)}
        </li>
      ))}
    </ul>
  )
}

/**
 * The route verdict. Only confirmed findings (cited to a tracked object and a
 * frame) are key findings here; possible ones are counted and listed apart, in
 * a quieter box, and never set the rating shown.
 */
export function Verdict({ report, findings, numberOf, onGo }: Props) {
  const { summary } = report.verdict
  const { rating, key, possible } = verdictDisplay(report, findings)
  const { label, icon } = rating === 'none_confirmed' ? NONE_CONFIRMED_TEXT : RATING_TEXT[rating]
  const counts = tierCounts(findings)
  const toVerify = findings.filter((f) => f.verify_manually && !isPossible(f)).length

  return (
    <section className={`verdict verdict-${rating}`} aria-labelledby="verdict-heading">
      <h2 id="verdict-heading" className="verdict-rating">
        <span className="verdict-icon" aria-hidden="true">
          {icon}
        </span>
        <span className="visually-hidden">Route verdict: </span>
        {label}
      </h2>
      <p className="verdict-summary">{summary}</p>

      <ul className="verdict-counts" aria-label="Findings on this route">
        <li className="count-confirmed">
          <strong>{counts.confirmed}</strong> confirmed{' '}
          <span className="count-detail">
            {counts.confirmed === 1 ? 'barrier' : 'barriers'}: object and frame cited
            {toVerify > 0 && <>, {toVerify} to verify manually</>}
          </span>
        </li>
        <li className="count-possible">
          <strong>{counts.possible}</strong> possible{' '}
          <span className="count-detail">
            {counts.possible === 1 ? 'barrier' : 'barriers'}: verify on site
          </span>
        </li>
      </ul>

      {key.length > 0 && (
        <div className="verdict-key">
          <h3>{key.length === 1 ? 'Key finding' : 'Key findings'}</h3>
          <FindingLinks items={key} numberOf={numberOf} onGo={onGo} />
        </div>
      )}
      {possible.length > 0 && (
        <div className="verdict-possible">
          <h3>Possible, not confirmed: check on site</h3>
          <p>Seen in the video by the raw-video pass, with no tracked object to confirm it. Not counted in the rating above.</p>
          <FindingLinks items={possible} numberOf={numberOf} onGo={onGo} />
        </div>
      )}
    </section>
  )
}
