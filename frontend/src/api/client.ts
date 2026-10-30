import type { JobError, JobStatus, ReportList } from '../types/api'
import type { Report } from '../types/report'

/** An error response from the API (``ErrorResponse``), with its HTTP status. */
export class ApiError extends Error {
  readonly status: number
  readonly error: JobError

  constructor(status: number, error: JobError) {
    super(error.message)
    this.status = status
    this.error = error
  }
}

/** One outcome the mock API can play out, for demos and testing the error states. */
export interface MockScenario {
  id: string
  label: string
}

/**
 * The HTTP API (backend/accesswalk/api_models.py) as the UI uses it. The mock
 * client implements it now; a fetch/XHR client drops in for d7-deploy.
 */
export interface ApiClient {
  /** POST /api/jobs (multipart: video, title). Rejects with ApiError on 400/413/415. */
  createJob(
    video: File,
    title: string | null,
    onProgress: (fraction: number) => void,
    signal: AbortSignal,
  ): Promise<JobStatus>
  /** GET /api/jobs/{job_id}. Rejects with ApiError(404, not_found). */
  getJob(jobId: string): Promise<JobStatus>
  /** GET /api/reports */
  listReports(): Promise<ReportList>
  /** GET of a report_url, e.g. /api/reports/{report_id}. */
  getReport(reportUrl: string): Promise<Report>
  /** Present on the mock client only. */
  mock?: {
    scenarios: MockScenario[]
    scenario: () => string
    setScenario: (id: string) => void
  }
}
