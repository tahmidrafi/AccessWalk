import Ajv from 'ajv'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from './api/client'
import { MOCK_DONE_MS, createMockClient, mockJobAt } from './api/mockClient'
import {
  ERROR_HELP,
  STAGES,
  asSentence,
  expectedProcessingText,
  pickSampleReport,
  reportPagePath,
  stageSteps,
  statusSentence,
  validateVideo,
} from './lib/jobs'
import { matchRoute } from './lib/router'
import errorNotFound from './mock/api/error_not_found.json'
import health from './mock/api/health.json'
import jobDone from './mock/api/job_done.json'
import jobFailed from './mock/api/job_failed.json'
import jobQueued from './mock/api/job_queued.json'
import jobRunning from './mock/api/job_running.json'
import reports from './mock/api/reports.json'
import apiSchema from './schema/api.schema.json'
import type { JobStatus, ReportSummary } from './types/api'

const ajv = new Ajv({ allErrors: true, strict: false })
ajv.addSchema(apiSchema, 'api')
const validator = (def: string) => ajv.getSchema(`api#/$defs/${def}`)!

function expectValid(def: string, value: unknown) {
  const validate = validator(def)
  expect(validate(value), JSON.stringify(validate.errors)).toBe(true)
}

const job = (scenario: 'success' | 'over_budget' | 'pipeline_error') => ({
  job_id: 'job-abc123',
  title: 'Bus stop to library',
  created_ms: Date.parse('2026-10-30T15:00:00Z'),
  scenario,
})

describe('API mocks', () => {
  it('match api.schema.json', () => {
    for (const j of [jobQueued, jobRunning, jobDone, jobFailed]) expectValid('JobStatus', j)
    expectValid('ErrorResponse', errorNotFound)
    expectValid('Health', health)
    expectValid('ReportList', reports)
  })

  it('has advice for every error code in the schema', () => {
    const codes = (apiSchema.$defs.JobError.properties.code as { enum: string[] }).enum
    expect(Object.keys(ERROR_HELP).sort()).toEqual([...codes].sort())
  })
})

describe('mock job timeline', () => {
  const sample = (scenario: Parameters<typeof job>[0]) => {
    const out: JobStatus[] = []
    for (let ms = 0; ms <= MOCK_DONE_MS + 1000; ms += 250) out.push(mockJobAt(job(scenario), ms))
    return out
  }

  it('runs queued -> each stage in order -> done, every status valid', () => {
    const states = sample('success')
    for (const s of states) expectValid('JobStatus', s)
    expect(states[0].state).toBe('queued')
    const seen = states.flatMap((s) => (s.stage && s.state === 'running' ? [s.stage] : []))
    expect([...new Set(seen)]).toEqual(STAGES.map((s) => s.id))
    for (let i = 1; i < states.length; i++) {
      expect(states[i].progress!).toBeGreaterThanOrEqual(states[i - 1].progress!)
      expect(states[i].cost_usd!).toBeGreaterThanOrEqual(states[i - 1].cost_usd!)
    }
    const done = states.at(-1)!
    expect(done.state).toBe('done')
    expect(done.report_url).toBe(jobDone.report_url)
    expect(done.cost_usd).toBe(jobDone.cost_usd)
    expect(done.title).toBe('Bus stop to library')
  })

  it('stops over_budget after ingest, before any paid stage, at no cost', () => {
    const states = sample('over_budget')
    for (const s of states) expectValid('JobStatus', s)
    expect(states.some((s) => s.stage === 'segment')).toBe(false)
    const last = states.at(-1)!
    expect(last.state).toBe('failed')
    expect(last.error?.code).toBe('over_budget')
    expect(last.cost_usd).toBe(0)
    expect(last.report_url).toBeNull()
  })

  it('fails pipeline_error during review with the cost so far', () => {
    const last = sample('pipeline_error').at(-1)!
    expectValid('JobStatus', last)
    expect(last).toMatchObject({ state: 'failed', stage: 'review', error: { code: 'pipeline_error' } })
    expect(last.cost_usd).toBeGreaterThan(0)
  })
})

describe('mock client', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('uploads with progress, then serves the job until done', async () => {
    let t = 1_000_000
    const api = createMockClient(() => t)
    const progress: number[] = []
    const created = api.createJob(new File(['x'], 'walk.mp4'), ' Main St ', (p) => progress.push(p), new AbortController().signal)
    await vi.runAllTimersAsync()
    const j = await created
    expect(progress.at(-1)).toBe(1)
    expect(j).toMatchObject({ state: 'queued', title: 'Main St' })
    t += MOCK_DONE_MS
    const polled = api.getJob(j.job_id)
    await vi.runAllTimersAsync()
    expect(await polled).toMatchObject({ state: 'done', report_url: jobDone.report_url })
  })

  it('rejects uploads like the server: 415, 400, cancel', async () => {
    const api = createMockClient()
    await expect(api.createJob(new File(['x'], 'notes.txt'), null, () => {}, new AbortController().signal)).rejects.toMatchObject({
      status: 415,
      error: { code: 'unsupported_media' },
    })
    api.mock!.setScenario('too_long')
    const tooLong = api.createJob(new File(['x'], 'walk.mov'), null, () => {}, new AbortController().signal)
    const settled = expect(tooLong).rejects.toMatchObject({ status: 400, error: { code: 'bad_request' } })
    await vi.runAllTimersAsync()
    await settled
    const ctrl = new AbortController()
    const cancelled = api.createJob(new File(['x'], 'walk.mp4'), null, () => {}, ctrl.signal)
    const aborted = expect(cancelled).rejects.toMatchObject({ name: 'AbortError' })
    ctrl.abort()
    await vi.runAllTimersAsync()
    await aborted
  })

  it('returns 404 not_found for unknown jobs and reports', async () => {
    const api = createMockClient()
    const missingJob = expect(api.getJob('job-0000')).rejects.toBeInstanceOf(ApiError)
    const missingReport = expect(api.getReport('/api/reports/nope')).rejects.toMatchObject({ status: 404 })
    const report = api.getReport(reports.reports[0].report_url)
    await vi.runAllTimersAsync()
    await missingJob
    await missingReport
    expect((await report).report_id).toBe(reports.reports[0].report_id)
  })
})

describe('job helpers', () => {
  it('checks the file before uploading', () => {
    const mb = 1024 * 1024
    expect(validateVideo({ name: 'walk.MOV', size: 10 * mb }, 45)).toBeNull()
    expect(validateVideo({ name: 'walk.mp4', size: 10 * mb }, null)).toBeNull()
    expect(validateVideo({ name: 'walk.avi', size: 1 }, null)?.code).toBe('unsupported_media')
    expect(validateVideo({ name: 'walk', size: 1 }, null)?.code).toBe('unsupported_media')
    expect(validateVideo({ name: 'walk.mp4', size: 301 * mb }, null)?.code).toBe('too_large')
    expect(validateVideo({ name: 'walk.mp4', size: 1 }, 121)?.code).toBe('bad_request')
  })

  it('picks the newest report with findings as the sample', () => {
    const r = (report_id: string, created_at: string, n_findings: number) => ({
      report_id,
      title: report_id,
      video_sha256: 'x',
      created_at,
      rating: 'caution' as const,
      n_findings,
      report_url: `/api/reports/${report_id}`,
    })
    const old = r('old', '2026-10-29T10:00:00+00:00', 2)
    const newer = r('newer', '2026-10-30T10:00:00+00:00', 1)
    const clean = r('clean', '2026-10-30T12:00:00+00:00', 0)
    expect(pickSampleReport([old, newer, clean])?.report_id).toBe('newer')
    expect(pickSampleReport([clean])?.report_id).toBe('clean')
    expect(pickSampleReport([])).toBeNull()
    expect(pickSampleReport(reports.reports as ReportSummary[])?.report_url).toBe(reports.reports[0].report_url)
  })

  it('states the expected time in words a screen reader reads correctly', () => {
    expect(expectedProcessingText()).toBe('Analysis takes about 6 to 7 minutes for a 30-second clip.')
  })

  it('marks each stage done, current, failed or waiting', () => {
    const statuses = (j: Pick<JobStatus, 'state' | 'stage'>) => stageSteps(j).map((s) => s.status)
    expect(statuses({ state: 'queued', stage: null })).toEqual(['waiting', 'waiting', 'waiting', 'waiting', 'waiting'])
    expect(statuses({ state: 'running', stage: 'segment' })).toEqual(['done', 'current', 'waiting', 'waiting', 'waiting'])
    expect(statuses({ state: 'failed', stage: 'review' })).toEqual(['done', 'done', 'done', 'failed', 'waiting'])
    expect(statuses({ state: 'done', stage: 'report' })).toEqual(['done', 'done', 'done', 'done', 'done'])
    expect(statusSentence({ state: 'running', stage: 'segment' })).toBe('Step 2 of 5: Find and track objects (SAM 3.1).')
  })

  it('maps API URLs and paths', () => {
    expect(reportPagePath('/api/reports/mock-64c947d94556')).toBe('/reports/mock-64c947d94556')
    expect(matchRoute('/')).toEqual({ name: 'upload' })
    expect(matchRoute('/jobs/job-7f3a9c/')).toEqual({ name: 'job', jobId: 'job-7f3a9c' })
    expect(matchRoute('/reports/mock-64c947d94556')).toEqual({ name: 'report', reportId: 'mock-64c947d94556' })
    expect(matchRoute('/jobs/../etc')).toEqual({ name: 'not_found' })
    expect(asSentence('video is 4.2 min long; the limit is 2 min')).toBe('Video is 4.2 min long; the limit is 2 min.')
  })
})
