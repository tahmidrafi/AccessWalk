import Ajv from 'ajv'
import { describe, expect, it } from 'vitest'
import { createHttpClient } from './api/httpClient'
import apiSchema from './schema/api.schema.json'
import reportSchema from './schema/report.schema.json'

/**
 * Against a running API, read-only routes only (no uploads, nothing that costs):
 *   ACCESSWALK_LIVE_API=http://127.0.0.1:8010 npm test
 * Skipped when the variable is unset.
 */
declare const process: { env: Record<string, string | undefined> } // Node global; the app tsconfig has no Node types
const base = process.env.ACCESSWALK_LIVE_API ?? ''
const ajv = new Ajv({ allErrors: true, strict: false })
ajv.addSchema(apiSchema, 'api')
const reportValid = ajv.compile(reportSchema)

function expectValid(validate: ReturnType<Ajv['compile']>, value: unknown) {
  expect(validate(value), JSON.stringify(validate.errors)).toBe(true)
}

describe.skipIf(!base)(`live API at ${base || '(unset)'}`, () => {
  const api = createHttpClient(base)

  it('GET /api/health', async () => {
    const h = await api.health()
    expectValid(ajv.getSchema('api#/$defs/Health')!, h)
    expect(h.ok).toBe(true)
  })

  it('GET /api/reports, then each report_url, then its media', async () => {
    const list = await api.listReports()
    expectValid(ajv.getSchema('api#/$defs/ReportList')!, list)
    expect(list.reports.length).toBeGreaterThan(0)

    for (const summary of list.reports) {
      const report = await api.getReport(summary.report_url)
      expectValid(reportValid, report)
      expect(report.report_id).toBe(summary.report_id)
      expect(report.findings.length).toBe(summary.n_findings)

      for (const f of report.findings.filter((x) => x.frame_url)) {
        const res = await fetch(f.frame_url!)
        expect(res.status, f.frame_url!).toBe(200)
        expect(res.headers.get('content-type')).toBe('image/jpeg')
      }
      if (report.video.proxy_url) {
        const res = await fetch(report.video.proxy_url, { headers: { Range: 'bytes=0-99' } })
        expect(res.status).toBe(206)
        expect((await res.arrayBuffer()).byteLength).toBe(100)
      }
    }
  })

  it('GET of an unknown report is a 404 not_found ErrorResponse', async () => {
    await expect(api.getReport('/api/reports/no-such-report')).rejects.toMatchObject({
      status: 404,
      error: { code: 'not_found' },
    })
  })
})
