import { useEffect, useRef, useState } from 'react'
import { ApiError, type ApiClient } from '../api/client'
import {
  ERROR_HELP,
  asSentence,
  POLL_MS,
  formatCost,
  isFinished,
  reportPagePath,
  stageSteps,
  statusSentence,
  type StepStatus,
} from '../lib/jobs'
import { usePageEntry } from '../lib/router'
import type { JobError, JobStatus } from '../types/api'
import { Link } from './Link'

const STEP_TEXT: Record<StepStatus, { icon: string; text: string }> = {
  done: { icon: '✓', text: 'Done' },
  current: { icon: '●', text: 'In progress' },
  waiting: { icon: '○', text: 'Waiting' },
  failed: { icon: '✕', text: 'Stopped' },
}

/** Poll GET /api/jobs/{id} every POLL_MS until the job is done or failed. */
function useJob(api: ApiClient, jobId: string) {
  const [job, setJob] = useState<JobStatus | null>(null)
  const [error, setError] = useState<JobError | null>(null)
  const [retrying, setRetrying] = useState(false)
  useEffect(() => {
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const poll = async () => {
      try {
        const j = await api.getJob(jobId)
        if (stopped) return
        setJob(j)
        setRetrying(false)
        if (!isFinished(j)) timer = setTimeout(poll, POLL_MS)
      } catch (err) {
        if (stopped) return
        if (err instanceof ApiError) {
          setError(err.error)
        } else {
          // Network trouble: keep the last status on screen and try again.
          setRetrying(true)
          timer = setTimeout(poll, POLL_MS * 2)
        }
      }
    }
    poll()
    return () => {
      stopped = true
      clearTimeout(timer)
    }
  }, [api, jobId])
  return { job, error, retrying }
}

export function JobPage({ api, jobId }: { api: ApiClient; jobId: string }) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  const outcomeRef = useRef<HTMLDivElement>(null)
  const { job, error, retrying } = useJob(api, jobId)
  const finished = job ? isFinished(job) : false
  const seenRunning = useRef(false)

  const pageTitle = error
    ? 'Job not found - AccessWalk'
    : job?.state === 'done'
      ? 'Report ready - AccessWalk'
      : job?.state === 'failed'
        ? 'Analysis stopped - AccessWalk'
        : 'Analysing - AccessWalk'
  usePageEntry(pageTitle, headingRef)

  // When a job we watched finish ends, move focus to the outcome (report link or error).
  useEffect(() => {
    if (!job) return
    if (!finished) seenRunning.current = true
    else if (seenRunning.current) outcomeRef.current?.focus()
  }, [job, finished])

  const failure = error ?? job?.error ?? null
  const pct = Math.round((job?.progress ?? 0) * 100)

  return (
    <>
      <div className="page-head">
        <h1 ref={headingRef} tabIndex={-1}>
          {job?.title ?? 'Your walkthrough'}
        </h1>
        <p className="muted">
          Analysis job <code>{jobId}</code>.{!finished && ' This page updates by itself; you can leave it open.'}
        </p>
      </div>

      {failure && (
        <div className="alert" role="alert" tabIndex={-1} ref={outcomeRef} aria-labelledby="job-error-title">
          <h2 id="job-error-title">{ERROR_HELP[failure.code].title}</h2>
          <p>{asSentence(failure.message)}</p>
          <p>{ERROR_HELP[failure.code].advice}</p>
          <p>
            <Link to="/">Upload a video</Link>
          </p>
        </div>
      )}

      {job?.state === 'done' && (
        <div className="success" tabIndex={-1} ref={outcomeRef} aria-labelledby="job-done-title">
          <h2 id="job-done-title">Your report is ready</h2>
          {job.report_url ? (
            <p>
              <Link to={reportPagePath(job.report_url)} className="button primary">
                Open the report{job.title ? `: ${job.title}` : ''}
              </Link>
            </p>
          ) : (
            <p>The job finished but did not return a report link. Try again later.</p>
          )}
        </div>
      )}

      {!job && !error && (
        <output className="muted">
          Checking the job…
        </output>
      )}

      {job && (
        <section aria-labelledby="progress-heading" className="job">
          <h2 id="progress-heading">Progress</h2>
          <output className="job-status">
            {statusSentence(job)}
          </output>
          {retrying && (
            <output className="muted">
              Lost contact with the server; trying again.
            </output>
          )}

          <div className="job-progress">
            <label htmlFor="job-progress">Overall progress</label>
            <progress id="job-progress" max={100} value={pct}>
              {pct}%
            </progress>
            <span aria-hidden="true">{pct}%</span>
          </div>
          {!finished && job.message && <p className="job-message">{job.message}</p>}

          <ol className="steps">
            {stageSteps(job).map((s) => (
              <li key={s.id} className={`step step-${s.status}`} aria-current={s.status === 'current' ? 'step' : undefined}>
                <span className="step-icon" aria-hidden="true">
                  {STEP_TEXT[s.status].icon}
                </span>
                <span className="step-label">{s.label}</span>
                <span className="step-status">{STEP_TEXT[s.status].text}</span>
              </li>
            ))}
          </ol>

          <dl className="job-facts">
            <div>
              <dt>{finished ? 'Model cost' : 'Model cost so far'}</dt>
              <dd>
                {formatCost(job.cost_usd)} <span className="muted">(object tracking and the review agent)</span>
              </dd>
            </div>
            <div>
              <dt>Started</dt>
              <dd>
                <time dateTime={job.created_at}>{new Date(job.created_at).toLocaleTimeString()}</time>
              </dd>
            </div>
          </dl>
        </section>
      )}
    </>
  )
}
