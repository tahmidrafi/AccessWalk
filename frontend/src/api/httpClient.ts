import type { Health, JobError, JobStatus, ReportList } from '../types/api'
import type { Report } from '../types/report'
import { ApiError, type ApiClient } from './client'

const CODES: JobError['code'][] = ['bad_request', 'too_large', 'unsupported_media', 'not_found', 'over_budget', 'pipeline_error']

/** Turn a non-2xx response body into an ApiError: the API's ErrorResponse when it
 * is one, else a code from the HTTP status (e.g. a proxy's 502 page). */
export function toApiError(status: number, body: unknown): ApiError {
  const err = (body as { error?: Partial<JobError> } | null)?.error
  if (err && typeof err.message === 'string' && CODES.includes(err.code as JobError['code'])) {
    return new ApiError(status, { code: err.code as JobError['code'], message: err.message })
  }
  const code: JobError['code'] =
    status === 404 ? 'not_found' : status === 413 ? 'too_large' : status === 415 ? 'unsupported_media' : status >= 500 ? 'pipeline_error' : 'bad_request'
  return new ApiError(status, { code, message: `The server answered HTTP ${status}.` })
}

function parse(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

/** Report media URLs are root-relative (/media/...); point them at the API when it
 * is on another origin. */
export function withMediaBase(report: Report, base: string): Report {
  if (!base) return report
  const fix = <T extends string | null | undefined>(u: T): T => (u && u.startsWith('/') ? (`${base}${u}` as T) : u)
  return {
    ...report,
    video: { ...report.video, proxy_url: fix(report.video.proxy_url) },
    findings: report.findings.map((f) => ({ ...f, frame_url: fix(f.frame_url) })),
    tracks: report.tracks.map((t) => ({ ...t, keyframe_url: fix(t.keyframe_url), mask_url: fix(t.mask_url) })),
  }
}

/**
 * The real API over HTTP. ``base`` is '' when the page and API share an origin
 * (production, or the dev server's proxy), else e.g. 'http://127.0.0.1:8010'
 * (the API then has to allow this origin: ACCESSWALK_CORS).
 */
export function createHttpClient(base = ''): ApiClient {
  base = base.replace(/\/+$/, '')
  const url = (path: string) => (path.startsWith('/') ? `${base}${path}` : path)

  // Network failures reject with the browser's TypeError, which the pages treat as
  // "lost contact, retrying" rather than an API answer.
  async function getJson<T>(path: string): Promise<T> {
    const res = await fetch(url(path), { headers: { Accept: 'application/json' } })
    const body = parse(await res.text())
    if (!res.ok) throw toApiError(res.status, body)
    return body as T
  }

  return {
    health: () => getJson<Health>('/api/health'),
    getJob: (jobId) => getJson<JobStatus>(`/api/jobs/${encodeURIComponent(jobId)}`),
    listReports: () => getJson<ReportList>('/api/reports'),
    getReport: async (reportUrl) => withMediaBase(await getJson<Report>(reportUrl), base),

    // XMLHttpRequest, not fetch: fetch has no upload progress events.
    createJob(video, title, onProgress, signal) {
      return new Promise<JobStatus>((resolve, reject) => {
        if (signal.aborted) {
          reject(new DOMException('Upload cancelled', 'AbortError'))
          return
        }
        const xhr = new XMLHttpRequest()
        xhr.open('POST', url('/api/jobs'))
        xhr.setRequestHeader('Accept', 'application/json')
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable && e.total > 0) onProgress(e.loaded / e.total)
        }
        xhr.onload = () => {
          const body = parse(xhr.responseText)
          if (xhr.status >= 200 && xhr.status < 300) {
            onProgress(1)
            resolve(body as JobStatus)
          } else {
            reject(toApiError(xhr.status, body))
          }
        }
        xhr.onerror = () => reject(new TypeError('Network error while uploading'))
        xhr.onabort = () => reject(new DOMException('Upload cancelled', 'AbortError'))
        signal.addEventListener('abort', () => xhr.abort(), { once: true })
        const form = new FormData()
        form.append('video', video, video.name)
        if (title) form.append('title', title)
        xhr.send(form)
      })
    },
  }
}
