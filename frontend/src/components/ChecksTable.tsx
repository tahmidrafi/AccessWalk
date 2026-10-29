import { CHECK_LABELS, checkResult } from '../lib/labels'
import type { CheckSummary } from '../types/report'

/** Every check and what happened to it, so "no findings" is explicit, not silent. */
export function ChecksTable({ checks }: { checks: CheckSummary[] }) {
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
                <td>{checkResult(c)}</td>
                <td>{c.note ?? <span className="muted">None</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
