import { CHECK_LABELS, checkResult } from '../lib/labels'
import { tierCounts } from '../lib/tier'
import type { CheckSummary, Finding } from '../types/report'

/**
 * Every check and what happened to it, so "no findings" is explicit, not silent.
 * With ``findings`` the result splits confirmed from possible barriers.
 */
export function ChecksTable({ checks, findings }: { checks: CheckSummary[]; findings?: Finding[] }) {
  return (
    <section aria-labelledby="checks-heading">
      <h2 id="checks-heading">What was checked</h2>
      <div className="table-wrap">
        <table className="checks">
          <thead>
            <tr>
              <th scope="col">Check</th>
              <th scope="col">Result</th>
              <th scope="col">Note</th>
            </tr>
          </thead>
          <tbody>
            {checks.map((c) => (
              <tr key={c.check_id} className={`check-${c.status}${(c.n_findings ?? 0) > 0 ? ' check-hit' : ''}`}>
                <th scope="row">{CHECK_LABELS[c.check_id]}</th>
                <td>{checkResult(c, findings && tierCounts(findings.filter((f) => f.check_id === c.check_id)))}</td>
                <td>{c.note ?? <span className="muted">None</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
