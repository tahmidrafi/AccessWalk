import { RATING_TEXT } from '../lib/labels'
import { findingAnchor } from '../lib/report'
import { formatClock } from '../lib/time'
import type { Finding, Report } from '../types/report'

interface Props {
  report: Report
  findings: Finding[]
  numberOf: Map<string, number>
  onGo: (f: Finding) => void
}

export function Verdict({ report, findings, numberOf, onGo }: Props) {
  const { rating, summary, key_finding_ids = [] } = report.verdict
  const { label, icon } = RATING_TEXT[rating]
  const key = key_finding_ids.flatMap((id) => findings.filter((f) => f.finding_id === id))
  const toVerify = findings.filter((f) => f.verify_manually).length

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
      <p className="verdict-counts">
        {findings.length} likely {findings.length === 1 ? 'barrier' : 'barriers'}
        {findings.length > 0 && <>, {toVerify} to verify manually</>}.
      </p>
      {key.length > 0 && (
        <div className="verdict-key">
          <h3>{key.length === 1 ? 'Key finding' : 'Key findings'}</h3>
          <ul>
            {key.map((f) => (
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
        </div>
      )}
    </section>
  )
}
