import health from '../mock/api/health.json'
import jobDone from '../mock/api/job_done.json'
import jobFailed from '../mock/api/job_failed.json'
import jobQueued from '../mock/api/job_queued.json'
import jobRunning from '../mock/api/job_running.json'
import notFound from '../mock/api/error_not_found.json'
import reports from '../mock/api/reports.json'
import mockReport from '../mock/report.json'
import { validateVideo } from '../lib/jobs'
import type { Health, JobStatus, ReportList } from '../types/api'
import type { Report } from '../types/report'
import { ApiError, type ApiClient, type MockScenario } from './client'

/**
 * In-browser stand-in for the API, built from the exported mocks in
 * src/mock/api/. Nothing leaves the page: the "upload" only reads the file name,
 * size and type, and jobs play out on a clock (about 20 s to a report).
 */

export const SCENARIOS: MockScenario[] = [
  { id: 'success', label: 'Report ready' },
  { id: 'over_budget', label: 'Over budget (fails after ingest)' },
  { id: 'pipeline_error', label: 'Pipeline error (fails during review)' },
  { id: 'too_long', label: 'Upload rejected: video too long (400)' },
  { id: 'too_large', label: 'Upload rejected: file too large (413)' },
]

export type ScenarioId = 'success' | 'over_budget' | 'pipeline_error' | 'too_long' | 'too_large'

interface MockJob {
  job_id: string
  title: string | null
  created_ms: number
  scenario: ScenarioId
}

// Stage windows on the mock clock: [start ms, end ms, progress at start, at end].
const PLAN: { stage: NonNullable<JobStatus['stage']>; from: number; to: number; p0: number; p1: number }[] = [
  { stage: 'ingest', from: 2_000, to: 5_000, p0: 0.0, p1: 0.15 },
  { stage: 'segment', from: 5_000, to: 11_000, p0: 0.15, p1: 0.6 },
  { stage: 'inventory', from: 11_000, to: 13_000, p0: 0.6, p1: 0.7 },
  { stage: 'review', from: 13_000, to: 18_000, p0: 0.7, p1: 0.95 },
  { stage: 'report', from: 18_000, to: 20_000, p0: 0.95, p1: 1.0 },
]
export const MOCK_DONE_MS = 20_000
const SAM_PHRASES = 12
const SAM_COST = 0.33 // ~$0.33 for 12 phrases on a 22 s clip at 5 fps
const PIPELINE_ERROR_MS = 15_000

function iso(ms: number): string {
  return new Date(ms).toISOString().replace(/\.\d{3}Z$/, '+00:00')
}

function stageMessage(stage: string, u: number): string {
  switch (stage) {
    case 'ingest':
      return 'Blurring faces and removing location data'
    case 'segment':
      return `SAM: ${Math.min(SAM_PHRASES, Math.floor(u * SAM_PHRASES) + 1)} of ${SAM_PHRASES} phrases`
    case 'inventory':
      return 'Merging tracks and picking evidence frames'
    case 'review':
      return 'Review agent checking likely barriers'
    default:
      return 'Writing the report'
  }
}

function costAt(ms: number): number {
  const seg = PLAN[1]
  const rev = PLAN[3]
  const sam = SAM_COST * Math.min(1, Math.max(0, (ms - seg.from) / (seg.to - seg.from)))
  const agent = (jobDone.cost_usd - SAM_COST) * Math.min(1, Math.max(0, (ms - rev.from) / (rev.to - rev.from)))
  return Math.round((sam + agent) * 100) / 100
}

/** The job as GET /api/jobs/{id} would return it ``elapsed`` ms after upload. */
export function mockJobAt(job: MockJob, elapsed: number): JobStatus {
  const base = {
    job_id: job.job_id,
    title: job.title,
    created_at: iso(job.created_ms),
    updated_at: iso(job.created_ms + Math.max(0, elapsed)),
  }
  if (job.scenario === 'over_budget' && elapsed >= PLAN[0].to) {
    // The cost estimate runs after ingest, before any paid call.
    return {
      ...jobFailed,
      ...base,
      stage: 'ingest',
      progress: PLAN[0].p1,
      message: 'Stopped before analysis: estimated cost is over the budget',
      video_sha256: jobRunning.video_sha256,
      cost_usd: 0,
      error: { code: 'over_budget', message: 'Estimated model cost is $6.80; the budget for one report is $5.00.' },
    } as JobStatus
  }
  if (job.scenario === 'pipeline_error' && elapsed >= PIPELINE_ERROR_MS) {
    return {
      ...jobFailed,
      ...base,
      stage: 'review',
      progress: 0.8,
      message: 'Stopped during review',
      video_sha256: jobRunning.video_sha256,
      cost_usd: costAt(PIPELINE_ERROR_MS),
      error: { code: 'pipeline_error', message: 'The review agent did not answer after 3 retries.' },
    } as JobStatus
  }
  if (elapsed >= MOCK_DONE_MS) return { ...jobDone, ...base } as JobStatus
  const step = PLAN.find((s) => elapsed < s.to && elapsed >= s.from)
  if (!step) return { ...jobQueued, ...base } as JobStatus
  const u = (elapsed - step.from) / (step.to - step.from)
  return {
    ...jobRunning,
    ...base,
    stage: step.stage,
    progress: Math.round((step.p0 + (step.p1 - step.p0) * u) * 100) / 100,
    message: stageMessage(step.stage, u),
    video_sha256: step.stage === 'ingest' ? null : jobRunning.video_sha256,
    cost_usd: costAt(elapsed),
  } as JobStatus
}

const STORE_KEY = 'accesswalk.mockJobs'

function loadJobs(): Record<string, MockJob> {
  try {
    return JSON.parse(sessionStorage.getItem(STORE_KEY) ?? '{}') as Record<string, MockJob>
  } catch {
    return {}
  }
}

function saveJobs(jobs: Record<string, MockJob>) {
  try {
    sessionStorage.setItem(STORE_KEY, JSON.stringify(jobs))
  } catch {
    // Private mode etc.: jobs then last until reload.
  }
}

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(t)
      reject(new DOMException('Upload cancelled', 'AbortError'))
    })
  })
}

export function createMockClient(now: () => number = Date.now): ApiClient {
  const jobs = loadJobs()
  let scenario: ScenarioId = 'success'

  return {
    async health() {
      await wait(150)
      return health as Health
    },

    async createJob(video, title, onProgress, signal) {
      // The server re-checks what the page already checked (type, size).
      const invalid = validateVideo(video, null)
      if (invalid) throw new ApiError(invalid.code === 'too_large' ? 413 : 415, invalid)
      // Simulated transfer: ten steps over ~2 s.
      for (let i = 1; i <= 10; i++) {
        await wait(200, signal)
        onProgress(i / 10)
      }
      if (scenario === 'too_long') throw new ApiError(400, jobFailed.error as { code: 'bad_request'; message: string })
      if (scenario === 'too_large') {
        throw new ApiError(413, { code: 'too_large', message: 'video is over 300 MB' })
      }
      const job: MockJob = {
        job_id: `job-${Math.floor(Math.random() * 0xffffff).toString(16).padStart(6, '0')}`,
        title: title?.trim().slice(0, 120) || null,
        created_ms: now(),
        scenario,
      }
      jobs[job.job_id] = job
      saveJobs(jobs)
      return mockJobAt(job, 0)
    },

    async getJob(jobId) {
      await wait(150)
      const job = jobs[jobId]
      if (!job) throw new ApiError(404, { ...notFound.error, message: `no job ${jobId}` } as ApiError['error'])
      return mockJobAt(job, now() - job.created_ms)
    },

    async listReports() {
      await wait(150)
      return reports as ReportList
    },

    async getReport(reportUrl) {
      await wait(150)
      const known = (reports as ReportList).reports.find((r) => r.report_url === reportUrl)
      if (!known) throw new ApiError(404, { code: 'not_found', message: `no report at ${reportUrl}` })
      return mockReport as Report
    },

    mock: {
      scenarios: SCENARIOS,
      scenario: () => scenario,
      setScenario: (id) => {
        scenario = id as ScenarioId
      },
    },
  }
}
