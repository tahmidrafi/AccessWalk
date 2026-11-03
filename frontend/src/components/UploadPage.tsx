import { useEffect, useRef, useState, type FormEvent, type Ref } from 'react'
import { ApiError, type ApiClient } from '../api/client'
import {
  MAX_DURATION_S,
  MAX_UPLOAD_MB,
  asSentence,
  expectedProcessingText,
  pickSampleReport,
  readDurationS,
  reportPagePath,
  suggestsSample,
  uploadErrorHelp,
  validateVideo,
} from '../lib/jobs'
import { RATING_TEXT } from '../lib/labels'
import { navigate, usePageEntry } from '../lib/router'
import type { Health, JobError, ReportSummary } from '../types/api'
import { Link } from './Link'

interface Props {
  api: ApiClient
  /** report_id behind "Try a sample route"; config wins, the mock has its own. */
  sampleReportId?: string
}

export function UploadPage({ api, sampleReportId = import.meta.env.VITE_SAMPLE_REPORT_ID || api.mock?.sampleReportId }: Props) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  usePageEntry('New report - AccessWalk', headingRef)

  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  // Held in this component only: never stored, never put in the URL.
  const [passcode, setPasscode] = useState('')
  const [passcodeError, setPasscodeError] = useState<string | null>(null)
  // Health says so, or the server refused an upload for want of one (health failed).
  const [passcodeRequired, setPasscodeRequired] = useState(false)
  const [fieldError, setFieldError] = useState<string | null>(null)
  const [uploadError, setUploadError] = useState<JobError | null>(null)
  const [progress, setProgress] = useState<number | null>(null) // null: not uploading
  const [announcement, setAnnouncement] = useState('')
  const [scenario, setScenario] = useState(() => api.mock?.scenario() ?? '')
  const [recent, setRecent] = useState<ReportSummary[] | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [listFailed, setListFailed] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const alertRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const cancelRef = useRef<HTMLButtonElement>(null)
  const passcodeRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let live = true
    api.listReports().then(
      (r) => live && setRecent(r.reports),
      () => live && setListFailed(true),
    )
    api.health().then(
      (h) => {
        if (!live) return
        setHealth(h)
        setPasscodeRequired(h.uploads === 'passcode')
      },
      () => live && setHealth(null),
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
    if (passcodeRequired && !passcode) {
      setPasscodeError('Enter the upload passcode.')
      passcodeRef.current?.focus()
      return
    }
    setPasscodeError(null)
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setProgress(0)
    setAnnouncement('Upload started.')
    try {
      const job = await api.createJob(
        file,
        title.trim() || null,
        setProgress,
        ctrl.signal,
        passcodeRequired ? passcode : null,
      )
      setAnnouncement('Upload complete.')
      navigate(`/jobs/${job.job_id}`)
    } catch (err) {
      setProgress(null)
      if (err instanceof DOMException && err.name === 'AbortError') {
        setAnnouncement('Upload cancelled.')
        return
      }
      setAnnouncement('')
      if (err instanceof ApiError && err.error.code === 'forbidden') setPasscodeRequired(true)
      setUploadError(
        err instanceof ApiError
          ? err.error
          : { code: 'pipeline_error', message: 'The upload did not reach the server. Check your connection and try again.' },
      )
    }
  }

  const pct = Math.round((progress ?? 0) * 100)
  const sample = recent && sampleReportId ? pickSampleReport(recent, sampleReportId) : null
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
            out a shortened sample analysis.
          </p>
        )}
      </div>

      {sampleReportId && (
        <section aria-labelledby="sample-heading" className="sample">
          <h2 id="sample-heading">No video to hand?</h2>
          {sample ? (
            <>
              <Link to={reportPagePath(sample.report_url)} className="button" aria-describedby="sample-hint">
                Try a sample route
              </Link>
              <p id="sample-hint" className="hint">
                Opens a finished report straight away, with {sample.n_findings} likely{' '}
                {sample.n_findings === 1 ? 'barrier' : 'barriers'}. Nothing is uploaded.
              </p>
            </>
          ) : listFailed ? (
            <p className="hint">The sample route could not be loaded. Reload the page to try again.</p>
          ) : recent === null ? (
            <p className="hint">Looking for a sample route…</p>
          ) : (
            <p className="hint">The sample route is not available right now.</p>
          )}
        </section>
      )}

      {uploadError && (
        <div className="alert" role="alert" tabIndex={-1} ref={alertRef} aria-labelledby="upload-error-title">
          <h2 id="upload-error-title">{uploadErrorHelp(uploadError.code).title}</h2>
          <p>{asSentence(uploadError.message)}</p>
          <p>{uploadErrorHelp(uploadError.code).advice}</p>
          {sample && suggestsSample(uploadError.code) && (
            <p>
              <Link to={reportPagePath(sample.report_url)}>Open the sample route</Link>
            </p>
          )}
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

        {passcodeRequired && (
          <PasscodeField
            inputRef={passcodeRef}
            value={passcode}
            error={passcodeError}
            refused={uploadError?.code === 'forbidden'}
            disabled={uploading}
            onChange={(v) => {
              setPasscode(v)
              setPasscodeError(null)
            }}
          />
        )}

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
                // Scenarios can change what health says (uploads: passcode).
                api.health().then(
                  (h) => {
                    setHealth(h)
                    setPasscodeRequired(h.uploads === 'passcode')
                  },
                  () => {},
                )
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
          <div className="upload-submit">
            <button type="submit" className="primary" aria-describedby="upload-time">
              Upload and analyse
            </button>
            <p id="upload-time" className="hint">
              {expectedProcessingText()}
            </p>
          </div>
        )}
        <output className="visually-hidden">
          {announcement}
        </output>
      </form>

      <section aria-labelledby="recent-heading" className="recent">
        <h2 id="recent-heading">Recent reports</h2>
        {listFailed ? (
          <p className="muted">The reports could not be loaded.</p>
        ) : recent === null ? (
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

      {health && (
        <p className="provenance muted">
          Analysis runs on {health.agent_model} via {health.agent_provider} (open-weight review agent) and{' '}
          {health.sam_model} (object tracking).
        </p>
      )}
    </>
  )
}

interface PasscodeFieldProps {
  value: string
  /** Client-side check, e.g. left empty. */
  error: string | null
  /** The server answered 403 forbidden to the last upload. */
  refused?: boolean
  disabled?: boolean
  onChange: (value: string) => void
  inputRef?: Ref<HTMLInputElement>
}

/** Shown when Health.uploads is "passcode": POST /api/jobs then needs form field ``passcode``. */
export function PasscodeField({ value, error, refused = false, disabled, onChange, inputRef }: PasscodeFieldProps) {
  const describedBy = ['passcode-hint', error ? 'passcode-error' : null].filter(Boolean).join(' ')
  return (
    <div className={`field${error || refused ? ' field-invalid' : ''}`}>
      <label htmlFor="passcode">Upload passcode</label>
      <p id="passcode-hint" className="hint">
        Judges: see the submission notes. Uploads on this server need the passcode; the sample route needs none.
      </p>
      <input
        ref={inputRef}
        id="passcode"
        name="passcode"
        type="password"
        required
        autoComplete="off"
        spellCheck={false}
        aria-describedby={describedBy}
        aria-invalid={error || refused ? true : undefined}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      />
      {error && (
        <p id="passcode-error" className="field-error">
          <span aria-hidden="true">✕ </span>
          {error}
        </p>
      )}
    </div>
  )
}
