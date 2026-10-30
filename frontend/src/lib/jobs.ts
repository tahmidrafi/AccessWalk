import type { JobError, JobStatus, ReportSummary } from '../types/api'

/** Server limits (backend/accesswalk/api_models.py: MAX_UPLOAD_MB, MAX_DURATION_S). */
export const MAX_UPLOAD_MB = 300
export const MAX_DURATION_S = 120
export const VIDEO_EXTENSIONS = ['.mp4', '.mov']
/** The API contract asks clients to poll about every 2 s. */
export const POLL_MS = 2000

/** Expected time from upload to report, shown before uploading. A fixed estimate for now. */
export const EXPECTED_PROCESSING = { minMinutes: 6, maxMinutes: 7, clipSeconds: 30 }

/** "to", not a dash: screen readers can read "6-7" as a subtraction or a single number. */
export function expectedProcessingText(e = EXPECTED_PROCESSING): string {
  return `Analysis takes about ${e.minMinutes} to ${e.maxMinutes} minutes for a ${e.clipSeconds}-second clip.`
}

/** The report behind "Try a sample route": the newest one with findings, else the newest. */
export function pickSampleReport(reports: ReportSummary[]): ReportSummary | null {
  const newestFirst = [...reports].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
  return newestFirst.find((r) => r.n_findings > 0) ?? newestFirst[0] ?? null
}

export type StageId = NonNullable<JobStatus['stage']>

export const STAGES: { id: StageId; label: string }[] = [
  { id: 'ingest', label: 'Blur faces and prepare the video' },
  { id: 'segment', label: 'Find and track objects (SAM 3.1)' },
  { id: 'inventory', label: 'List the tracked objects' },
  { id: 'review', label: 'Check each likely barrier (review agent)' },
  { id: 'report', label: 'Write the report' },
]

export type StepStatus = 'done' | 'current' | 'waiting' | 'failed'

/** Status of each pipeline stage for a job, in pipeline order. */
export function stageSteps(job: Pick<JobStatus, 'state' | 'stage'>): { id: StageId; label: string; status: StepStatus }[] {
  const at = job.stage ? STAGES.findIndex((s) => s.id === job.stage) : -1
  return STAGES.map((s, i) => {
    let status: StepStatus = 'waiting'
    if (job.state === 'done' || i < at) status = 'done'
    else if (i === at) status = job.state === 'failed' ? 'failed' : 'current'
    return { ...s, status }
  })
}

/** One sentence for the job's status line; it only changes when the stage or state does. */
export function statusSentence(job: Pick<JobStatus, 'state' | 'stage'>): string {
  if (job.state === 'queued') return 'Waiting to start.'
  if (job.state === 'done') return 'Report ready.'
  if (job.state === 'failed') return 'Analysis stopped.'
  const i = STAGES.findIndex((s) => s.id === job.stage)
  return i < 0 ? 'Starting.' : `Step ${i + 1} of ${STAGES.length}: ${STAGES[i].label}.`
}

export function isFinished(job: Pick<JobStatus, 'state'>): boolean {
  return job.state === 'done' || job.state === 'failed'
}

/** Server messages are terse lower-case clauses; show them as sentences. */
export function asSentence(message: string): string {
  const m = message.trim()
  if (!m) return m
  return m[0].toUpperCase() + m.slice(1) + (/[.!?]$/.test(m) ? '' : '.')
}

export function formatCost(usd: number | undefined): string {
  return `$${(usd ?? 0).toFixed(2)}`
}

/** What each error means for the person filming, and what to do next. */
export const ERROR_HELP: Record<JobError['code'], { title: string; advice: string }> = {
  bad_request: {
    title: 'This video could not be used',
    advice: `Upload a walkthrough of up to ${MAX_DURATION_S / 60} minutes, filmed with the phone upright.`,
  },
  too_large: {
    title: 'The file is too large',
    advice: `Upload a file of up to ${MAX_UPLOAD_MB} MB. Trimming the clip to the route itself usually helps.`,
  },
  unsupported_media: {
    title: 'This file type is not supported',
    advice: 'Upload an .mp4 or .mov video, as phones record by default.',
  },
  not_found: {
    title: 'This job was not found',
    advice: 'The link may be out of date, or the job was removed. Upload the video again to start a new one.',
  },
  over_budget: {
    title: 'This video is over the analysis budget',
    advice:
      'Analysing it would cost more than one report is allowed to. Nothing was charged. Upload a shorter clip that covers just the route.',
  },
  pipeline_error: {
    title: 'The analysis stopped with an error',
    advice: 'This is a problem on our side, not with your video. Try uploading it again in a few minutes.',
  },
}

/** Client-side checks before uploading; the server checks again. */
export function validateVideo(file: { name: string; size: number }, durationS: number | null): JobError | null {
  const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
  if (!file.name.includes('.') || !VIDEO_EXTENSIONS.includes(ext)) {
    return { code: 'unsupported_media', message: `"${file.name}" is not an .mp4 or .mov video.` }
  }
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    const mb = Math.round(file.size / (1024 * 1024))
    return { code: 'too_large', message: `The file is ${mb} MB; the limit is ${MAX_UPLOAD_MB} MB.` }
  }
  if (durationS !== null && durationS > MAX_DURATION_S) {
    return {
      code: 'bad_request',
      message: `The video is ${(durationS / 60).toFixed(1)} minutes long; the limit is ${MAX_DURATION_S / 60} minutes.`,
    }
  }
  return null
}

/** The page that shows a report: its report_url without the /api prefix. */
export function reportPagePath(reportUrl: string): string {
  return reportUrl.replace(/^\/api(?=\/reports\/)/, '')
}

/** Duration of a local video file from its metadata, or null if the browser can't read it. */
export function readDurationS(file: File, timeoutMs = 5000): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file)
    const v = document.createElement('video')
    const done = (d: number | null) => {
      clearTimeout(timer)
      URL.revokeObjectURL(url)
      v.removeAttribute('src')
      resolve(d !== null && Number.isFinite(d) ? d : null)
    }
    const timer = setTimeout(() => done(null), timeoutMs)
    v.preload = 'metadata'
    v.onloadedmetadata = () => done(v.duration)
    v.onerror = () => done(null)
    v.src = url
  })
}
