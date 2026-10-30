import { useEffect, useRef, useState } from 'react'
import { ApiError, type ApiClient } from '../api/client'
import { ERROR_HELP, asSentence } from '../lib/jobs'
import { usePageEntry } from '../lib/router'
import type { JobError } from '../types/api'
import type { Report } from '../types/report'
import { Link } from './Link'
import { ReportPage } from './ReportPage'

/** /reports/{id}: fetch the report from its report_url (/api/reports/{id}) and show it. */
export function ReportRoute({ api, reportId }: { api: ApiClient; reportId: string }) {
  const [state, setState] = useState<{ id: string; report?: Report; error?: JobError } | null>(null)

  useEffect(() => {
    let live = true
    api.getReport(`/api/reports/${reportId}`).then(
      (report) => live && setState({ id: reportId, report }),
      (err) =>
        live &&
        setState({
          id: reportId,
          error: err instanceof ApiError ? err.error : { code: 'pipeline_error', message: 'The report could not be loaded.' },
        }),
    )
    return () => {
      live = false
    }
  }, [api, reportId])

  const current = state?.id === reportId ? state : null
  if (current?.report) return <ReportPage key={reportId} report={current.report} />
  return <ReportStatus error={current?.error ?? null} />
}

function ReportStatus({ error }: { error: JobError | null }) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  usePageEntry(error ? 'Report not found - AccessWalk' : 'Loading report - AccessWalk', headingRef)
  if (!error) {
    return (
      <div className="page-head">
        <h1 ref={headingRef} tabIndex={-1}>
          Loading the report
        </h1>
        <output className="muted">
          Loading…
        </output>
      </div>
    )
  }
  return (
    <div className="page-head">
      <h1 ref={headingRef} tabIndex={-1}>
        {ERROR_HELP[error.code].title.replace('This job', 'This report')}
      </h1>
      <div className="alert" role="alert">
        <p>{asSentence(error.message)}</p>
        <p>
          <Link to="/">Upload a video</Link> to make a new report.
        </p>
      </div>
    </div>
  )
}
