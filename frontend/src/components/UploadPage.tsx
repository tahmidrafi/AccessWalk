import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError, type ApiClient } from '../api/client'
import { ERROR_HELP, MAX_DURATION_S, asSentence, MAX_UPLOAD_MB, readDurationS, reportPagePath, validateVideo } from '../lib/jobs'
import { RATING_TEXT } from '../lib/labels'
import { navigate, usePageEntry } from '../lib/router'
import type { JobError, ReportSummary } from '../types/api'
import { Link } from './Link'

export function UploadPage({ api }: { api: ApiClient }) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  usePageEntry('New report - AccessWalk', headingRef)

  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [fieldError, setFieldError] = useState<string | null>(null)
  const [uploadError, setUploadError] = useState<JobError | null>(null)
  const [progress, setProgress] = useState<number | null>(null) // null: not uploading
  const [announcement, setAnnouncement] = useState('')
  const [scenario, setScenario] = useState(() => api.mock?.scenario() ?? '')
  const [recent, setRecent] = useState<ReportSummary[] | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const alertRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const cancelRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    let live = true
    api.listReports().then(
      (r) => live && setRecent(r.reports),
      () => live && setRecent([]),
    )
    return () => {
      live = false
      abortRef.current?.abort()
    }
  }, [api])

  useEffect(() => {
    if (uploadError) alertRef.current?.focus()
  }, [uploadError])

  // The submit button gives way to the progress bar: keep focus on the one action left.
  const uploading = progress !== null
  useEffect(() => {
    if (uploading) cancelRef.current?.focus()
  }, [uploading])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setUploadError(null)
    if (!file) {
      setFieldError('Choose a video file to upload.')
      fileRef.current?.focus()
      return
    }
    const invalid = validateVideo(file, await readDurationS(file))
    if (invalid) {
      setFieldError(invalid.message)
      fileRef.current?.focus()
      return
    }
    setFieldError(null)
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setProgress(0)
    setAnnouncement('Upload started.')
    try {
      const job = await api.createJob(file, title.trim() || null, setProgress, ctrl.signal)
      setAnnouncement('Upload complete.')
      navigate(`/jobs/${job.job_id}`)
    } catch (err) {
      setProgress(null)
      if (err instanceof DOMException && err.name === 'AbortError') {
        setAnnouncement('Upload cancelled.')
        return
      }
      setAnnouncement('')
      setUploadError(
        err instanceof ApiError
          ? err.error
          : { code: 'pipeline_error', message: 'The upload did not reach the server. Check your connection and try again.' },
      )
    }
  }

  const pct = Math.round((progress ?? 0) * 100)
  const describedBy = ['video-hint', fieldError ? 'video-error' : null].filter(Boolean).join(' ')

  return (
    <>
      <div className="page-head">
        <h1 ref={headingRef} tabIndex={-1}>
          Check a route before you go
        </h1>
        <p className="lede">
          Upload a phone video of the walk, from the bus stop or parking to the entrance. AccessWalk tracks what is
          along the route and reports likely barriers for a wheelchair user, each with the frame it rests on.
        </p>
        {api.mock && (
          <p className="notice">
            <strong>Demo mode.</strong> Nothing is uploaded: the page checks the file on your device and then plays
            out a sample analysis.
          </p>
        )}
      </div>

      {uploadError && (
        <div className="alert" role="alert" tabIndex={-1} ref={alertRef} aria-labelledby="upload-error-title">
          <h2 id="upload-error-title">{ERROR_HELP[uploadError.code].title}</h2>
          <p>{asSentence(uploadError.message)}</p>
          <p>{ERROR_HELP[uploadError.code].advice}</p>
        </div>
      )}

      <form className="upload" onSubmit={onSubmit} noValidate aria-labelledby="upload-heading">
        <h2 id="upload-heading">Upload a walkthrough</h2>

        <div className={`field${fieldError ? ' field-invalid' : ''}`}>
          <label htmlFor="video">Walkthrough video</label>
          <p id="video-hint" className="hint">
            .mp4 or .mov, up to {MAX_DURATION_S / 60} minutes and {MAX_UPLOAD_MB} MB. Phone upright, steady walking
            pace; pause for a moment at each step, ramp or obstacle. Faces are blurred and location data removed
            before any frame is analysed.
          </p>
          <input
            ref={fileRef}
            id="video"
            name="video"
            type="file"
            accept=".mp4,.mov,video/mp4,video/quicktime"
            aria-describedby={describedBy}
            aria-invalid={fieldError ? true : undefined}
            disabled={uploading}
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null)
              setFieldError(null)
            }}
          />
          {fieldError && (
            <p id="video-error" className="field-error">
              <span aria-hidden="true">✕ </span>
              {fieldError}
            </p>
          )}
        </div>

        <div className="field">
          <label htmlFor="title">
            Route name <span className="muted">(optional)</span>
          </label>
          <p id="title-hint" className="hint">
            For example "Bus stop to library entrance". Shown as the report title.
          </p>
          <input
            id="title"
            name="title"
            type="text"
            maxLength={120}
            autoComplete="off"
            aria-describedby="title-hint"
            value={title}
            disabled={uploading}
            onChange={(e) => setTitle(e.target.value)}
          />
        </div>

        {api.mock && (
          <details className="dev-options">
            <summary>Demo outcome</summary>
            <label htmlFor="scenario">What the sample analysis does</label>
            <select
              id="scenario"
              value={scenario}
              disabled={uploading}
              onChange={(e) => {
                api.mock?.setScenario(e.target.value)
                setScenario(e.target.value)
              }}
            >
              {api.mock.scenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </details>
        )}

        {uploading ? (
          <div className="upload-progress">
            <label htmlFor="upload-progress">Uploading</label>
            <progress id="upload-progress" max={100} value={pct}>
              {pct}%
            </progress>
            <span aria-hidden="true">{pct}%</span>
            <button type="button" ref={cancelRef} onClick={() => abortRef.current?.abort()}>
              Cancel upload
            </button>
          </div>
        ) : (
          <button type="submit" className="primary">
            Upload and analyse
          </button>
        )}
        <output className="visually-hidden">
          {announcement}
        </output>
      </form>

      <section aria-labelledby="recent-heading" className="recent">
        <h2 id="recent-heading">Recent reports</h2>
        {recent === null ? (
          <p className="muted">Loading…</p>
        ) : recent.length === 0 ? (
          <p className="muted">No reports yet.</p>
        ) : (
          <ul>
            {recent.map((r) => (
              <li key={r.report_id}>
                <Link to={reportPagePath(r.report_url)}>{r.title}</Link>
                <span className="muted">
                  {' '}
                  · {RATING_TEXT[r.rating].label} · {r.n_findings} likely {r.n_findings === 1 ? 'barrier' : 'barriers'}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  )
}
