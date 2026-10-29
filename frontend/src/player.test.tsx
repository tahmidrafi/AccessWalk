import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { EvidenceFrame } from './components/EvidenceFrame'
import {
  adjacentFinding,
  boxAt,
  findingsInRouteOrder,
  findingsInView,
  findingsVtt,
  loadReport,
  samFrameMs,
  snapToSamFrame,
  trackById,
} from './lib/report'
import type { Finding, Track } from './types/report'

const report = loadReport()
const findings = findingsInRouteOrder(report)
const tracks = trackById(report)
const frameMs = samFrameMs(report.video)

describe('video sync', () => {
  it('snaps video time to SAM frames, tolerating float seeks', () => {
    expect(frameMs).toBe(200)
    expect(snapToSamFrame(11_999.6, frameMs)).toBe(12_000)
    expect(snapToSamFrame(12_001, frameMs)).toBe(12_000)
    expect(snapToSamFrame(12_198, frameMs)).toBe(12_000)
    expect(snapToSamFrame(12_200, frameMs)).toBe(12_200)
  })

  it('holds a box for one SAM frame and no longer', () => {
    const t = tracks.get('raised-sidewalk-slab-4')!
    expect(boxAt(t, 11_800, frameMs)).toBeUndefined()
    expect(boxAt(t, 12_000, frameMs)?.frame_index).toBe(60)
    expect(boxAt(t, 12_100, frameMs)?.frame_index).toBe(60)
    expect(boxAt(t, t.last_ms + frameMs, frameMs)).toBeUndefined()
  })

  it('lists the findings whose object is on screen', () => {
    const ids = (ms: number) => findingsInView(findings, tracks, ms, frameMs).map((f) => f.finding_id)
    expect(ids(0)).toEqual([])
    expect(ids(10_800)).toEqual(['f2'])
    expect(ids(12_000)).toEqual(['f2', 'f1'])
    expect(ids(18_000)).toEqual(['f3'])
  })

  it('steps to the previous and next finding', () => {
    expect(adjacentFinding(findings, 0, 1)?.finding_id).toBe('f2')
    expect(adjacentFinding(findings, 10_800, 1)?.finding_id).toBe('f1')
    expect(adjacentFinding(findings, 12_000, -1)?.finding_id).toBe('f2')
    expect(adjacentFinding(findings, 10_800, -1)).toBeUndefined()
    expect(adjacentFinding(findings, 18_000, 1)).toBeUndefined()
  })

  it('captions each finding while its object is tracked', () => {
    const numberOf = new Map(findings.map((f, i) => [f.finding_id, i + 1]))
    const vtt = findingsVtt(findings, tracks, numberOf, frameMs, (f) => f.title)
    expect(vtt.startsWith('WEBVTT\n\n')).toBe(true)
    // f1's track raised-sidewalk-slab-4 spans 12.0-14.0 s, shown until the next SAM frame.
    expect(vtt).toContain('00:00:12.000 --> 00:00:14.200\n2. Heaved slab beside a tree trunk')
  })
})

describe('evidence overlay', () => {
  const f1 = report.findings.find((f) => f.finding_id === 'f1') as Finding
  const t1 = tracks.get(f1.track_id) as Track
  const render = (track: Track) =>
    renderToStaticMarkup(<EvidenceFrame finding={f1} video={report.video} track={track} related={[]} />)

  it('draws the box when the track has no mask', () => {
    const html = render(t1)
    expect(html).toContain('box-cited')
    expect(html).not.toContain('<image')
  })

  it('draws the mask instead of the box on the keyframe', () => {
    const html = render({ ...t1, mask_url: '/media/x/masks/raised-sidewalk-slab-4.png' })
    expect(html).toContain('href="/media/x/masks/raised-sidewalk-slab-4.png"')
    expect(html).not.toContain('box-cited')
  })

  it('falls back to the box when the mask is for another frame', () => {
    const html = render({ ...t1, mask_url: '/m.png', keyframe_index: t1.keyframe_index + 1 })
    expect(html).toContain('box-cited')
  })
})
