import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from './api/client'
import { createHttpClient, toApiError, withMediaBase } from './api/httpClient'
import health from './mock/api/health.json'
import jobQueued from './mock/api/job_queued.json'
import mockReport from './mock/report.json'
import type { Report } from './types/report'

function stubFetch(status: number, body: unknown) {
  const fetch = vi.fn(async () => new Response(typeof body === 'string' ? body : JSON.stringify(body), { status }))
  vi.stubGlobal('fetch', fetch)
  return fetch
}

/** Minimal XMLHttpRequest stand-in: records the request, answers on demand. */
class FakeXhr {
  static last: FakeXhr
  method = ''
  url = ''
  body: FormData | null = null
  status = 0
  responseText = ''
  upload: { onprogress: ((e: { lengthComputable: boolean; loaded: number; total: number }) => void) | null } = {
    onprogress: null,
  }
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  onabort: (() => void) | null = null
  constructor() {
    FakeXhr.last = this
  }
  open(method: string, url: string) {
    this.method = method
    this.url = url
  }
  setRequestHeader() {}
  send(body: FormData) {
    this.body = body
  }
  abort() {
    this.onabort?.()
  }
  respond(status: number, body: unknown) {
    this.status = status
    this.responseText = JSON.stringify(body)
    this.onload?.()
  }
}

afterEach(() => vi.unstubAllGlobals())

describe('HTTP client: reads', () => {
  it('GETs JSON from the API, same origin by default', async () => {
    const fetch = stubFetch(200, health)
    expect(await createHttpClient().health()).toEqual(health)
    expect(fetch).toHaveBeenCalledWith('/api/health', expect.anything())
  })

  it('turns an ErrorResponse into ApiError with its code', async () => {
    stubFetch(404, { error: { code: 'not_found', message: 'no job job-0000' } })
    const err = await createHttpClient('http://127.0.0.1:8010').getJob('job-0000').catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 404, error: { code: 'not_found', message: 'no job job-0000' } })
  })

  it('maps a non-API error page by status', () => {
    expect(toApiError(502, null).error.code).toBe('pipeline_error')
    expect(toApiError(413, '<html>').error.code).toBe('too_large')
    expect(toApiError(422, { detail: [] }).error.code).toBe('bad_request')
    expect(toApiError(400, { error: { code: 'made_up', message: 'x' } }).error.code).toBe('bad_request')
  })

  it('lets network failures through as TypeError (pages retry those)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('Failed to fetch'))))
    await expect(createHttpClient().listReports()).rejects.toBeInstanceOf(TypeError)
  })

  it('points report media at the API origin when it is elsewhere', async () => {
    const fetch = stubFetch(200, mockReport)
    const r = await createHttpClient('http://127.0.0.1:8010/').getReport('/api/reports/mock-64c947d94556')
    expect(fetch).toHaveBeenCalledWith('http://127.0.0.1:8010/api/reports/mock-64c947d94556', expect.anything())
    expect(r.video.proxy_url).toBe(`http://127.0.0.1:8010${mockReport.video.proxy_url}`)
    expect(r.findings[0].frame_url).toMatch(/^http:\/\/127\.0\.0\.1:8010\/media\//)
    expect(withMediaBase(mockReport as Report, '')).toBe(mockReport)
  })
})

describe('HTTP client: upload', () => {
  const upload = (signal = new AbortController().signal, progress: number[] = []) => {
    vi.stubGlobal('XMLHttpRequest', FakeXhr)
    const p = createHttpClient().createJob(new File(['abc'], 'walk.mp4'), 'Main St', (f) => progress.push(f), signal)
    return { p, xhr: FakeXhr.last, progress }
  }

  it('POSTs multipart video + title and reports progress', async () => {
    const { p, xhr, progress } = upload()
    expect(xhr.method).toBe('POST')
    expect(xhr.url).toBe('/api/jobs')
    expect((xhr.body!.get('video') as File).name).toBe('walk.mp4')
    expect(xhr.body!.get('title')).toBe('Main St')
    xhr.upload.onprogress!({ lengthComputable: true, loaded: 50, total: 100 })
    xhr.respond(202, jobQueued)
    expect(await p).toEqual(jobQueued)
    expect(progress).toEqual([0.5, 1])
  })

  it('rejects with the API error on 413', async () => {
    const { p, xhr } = upload()
    xhr.respond(413, { error: { code: 'too_large', message: 'video is over 300 MB' } })
    await expect(p).rejects.toMatchObject({ status: 413, error: { code: 'too_large' } })
  })

  it('aborts the request when cancelled', async () => {
    const ctrl = new AbortController()
    const { p } = upload(ctrl.signal)
    ctrl.abort()
    await expect(p).rejects.toMatchObject({ name: 'AbortError' })
  })
})
