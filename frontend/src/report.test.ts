import Ajv from 'ajv'
import { describe, expect, it } from 'vitest'
import { checkResult, pdfTitle } from './lib/labels'
import { boxOnFrame, findingsInRouteOrder, loadReport, timelineRows, trackById } from './lib/report'
import { formatClock, formatSeconds, spokenTime } from './lib/time'
import schema from './schema/report.schema.json'
import type { Finding } from './types/report'

const report = loadReport()

describe('mock report', () => {
  it('matches the exported JSON Schema', () => {
    const validate = new Ajv({ allErrors: true, strict: false }).compile(schema)
    expect(validate(report), JSON.stringify(validate.errors, null, 2)).toBe(true)
  })

  it('cites a real track and frame for every finding', () => {
    const tracks = trackById(report)
    for (const f of report.findings) {
      const t = tracks.get(f.track_id)
      expect(t, f.finding_id).toBeDefined()
      expect(boxOnFrame(t!, f.frame_index), f.finding_id).toBeDefined()
      expect(report.video.frame_ms[f.frame_index]).toBe(f.frame_ms)
    }
  })
})

describe('helpers', () => {
  it('formats times', () => {
    expect(formatClock(0)).toBe('0:00')
    expect(formatClock(12_999)).toBe('0:12')
    expect(formatClock(72_000)).toBe('1:12')
    expect(formatSeconds(10_800)).toBe('10.8 s')
    expect(spokenTime(1_000)).toBe('1 second')
    expect(spokenTime(72_000)).toBe('1 minute 12 seconds')
    expect(spokenTime(120_000)).toBe('2 minutes')
  })

  it('orders findings by time along the route', () => {
    expect(findingsInRouteOrder(report).map((f) => f.finding_id)).toEqual(['f2', 'f1', 'f3'])
  })

  it('puts close timeline marks on separate rows', () => {
    const at = (id: string, ms: number) => ({ finding_id: id, frame_ms: ms }) as Finding
    const rows = timelineRows([at('a', 10_000), at('b', 11_000), at('c', 20_000), at('d', 10_500)], 22_000)
    expect(rows.get('a')).toBe(0)
    expect(rows.get('d')).toBe(1)
    expect(rows.get('b')).toBe(2)
    expect(rows.get('c')).toBe(0)
  })

  it('names the PDF after the report and its date', () => {
    expect(pdfTitle(report)).toBe(`AccessWalk report - ${report.title} (${report.run.created_at.slice(0, 10)})`)
  })

  it('describes check outcomes in words', () => {
    expect(checkResult({ check_id: 'surface_damage', status: 'ran', n_findings: 1 })).toBe('1 likely barrier')
    expect(checkResult({ check_id: 'surface_damage', status: 'ran' })).toBe('Checked, nothing found')
    expect(checkResult({ check_id: 'round_doorknob', status: 'not_applicable' })).toBe('Not applicable')
  })
})
