import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { EvidenceFrame } from './components/EvidenceFrame'
import {
  adjacentFinding,
  boxAt,
  findingsInRouteOrder,
  findingsInView,
  findingsVtt,
  interpolatedBoxAt,
  loadReport,
  overlayShapes,
  samFrameMs,
  snapToSamFrame,
  trackById,
} from './lib/report'
import type { Finding, Track, TrackBox } from './types/report'

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

describe('box interpolation', () => {
  // SAM frames 10, 11 and 14 at 5 fps (200 ms apart): 12 and 13 are a gap.
  const box = (frame_index: number, x1: number, y1: number, x2: number, y2: number): TrackBox => ({
    frame_index,
    frame_ms: frame_index * 200,
    x1,
    y1,
    x2,
    y2,
  })
  const track: Track = {
    track_id: 'bin-0',
    phrase: 'trash bin',
    object_id: 0,
    first_ms: 2000,
    last_ms: 2800,
    n_frames: 3,
    keyframe_index: 11,
    keyframe_ms: 2200,
    // Deliberately out of order: the helper sorts by frame.
    boxes: [box(14, 300, 300, 400, 400), box(10, 100, 100, 200, 300), box(11, 120, 140, 240, 340)],
  }
  const at = (ms: number) => interpolatedBoxAt(track, ms, frameMs)

  it('is absent before the first box', () => {
    expect(at(1999)).toBeUndefined()
  })

  it('returns the SAM box exactly on its frame', () => {
    expect(at(2000)?.bbox).toEqual({ x1: 100, y1: 100, x2: 200, y2: 300 })
    expect(at(2200)?.bbox).toEqual({ x1: 120, y1: 140, x2: 240, y2: 340 })
  })

  it('moves linearly between consecutive SAM frames', () => {
    expect(at(2100)?.bbox).toEqual({ x1: 110, y1: 120, x2: 220, y2: 320 })
    const q = at(2050)!
    expect(q.bbox).toEqual({ x1: 105, y1: 110, x2: 210, y2: 310 })
    expect(q.from.frame_index).toBe(10)
  })

  it('does not interpolate across a gap: holds 200 ms, then nothing', () => {
    // Frame 11 -> 14 skips 12 and 13, so no movement toward frame 14.
    expect(at(2300)?.bbox).toEqual({ x1: 120, y1: 140, x2: 240, y2: 340 })
    expect(at(2399)?.bbox).toEqual({ x1: 120, y1: 140, x2: 240, y2: 340 })
    expect(at(2400)).toBeUndefined()
    expect(at(2700)).toBeUndefined()
    expect(at(2800)?.bbox).toEqual({ x1: 300, y1: 300, x2: 400, y2: 400 })
  })

  it('holds the last box for 200 ms at the track end, no extrapolation', () => {
    expect(at(2999)?.bbox).toEqual({ x1: 300, y1: 300, x2: 400, y2: 400 })
    expect(at(3000)).toBeUndefined()
  })

  it('is on screen exactly when the held box is (same in-view rule)', () => {
    for (const t of report.tracks) {
      for (let ms = 0; ms <= report.video.duration_ms + 400; ms += 10) {
        expect(interpolatedBoxAt(t, ms, frameMs) !== undefined, `${t.track_id} @ ${ms}`).toBe(
          boxAt(t, ms, frameMs) !== undefined,
        )
      }
    }
  })

  it('swaps in the keyframe mask for that SAM frame only', () => {
    const f = { finding_id: 'fx', track_id: 'bin-0', frame_ms: 2200 } as Finding
    const withMask = new Map([['bin-0', { ...track, mask_url: '/m.png' }]])
    const shapes = (ms: number) => overlayShapes([f], withMask, new Map([['fx', 1]]), ms, frameMs)
    expect(shapes(2100)[0].mask).toBeNull()
    expect(shapes(2200)[0].mask).toBe('/m.png')
    expect(shapes(2399)[0].mask).toBe('/m.png')
    expect(shapes(2400)).toEqual([])
  })
})
