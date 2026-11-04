import { renderToStaticMarkup } from 'react-dom/server'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import { ChecksTable } from './components/ChecksTable'
import { EvidenceFrame } from './components/EvidenceFrame'
import { FindingCard } from './components/FindingCard'
import { HeroMedia } from './components/HeroMedia'
import { HowItWorks } from './components/HowItWorks'
import { ReportPage } from './components/ReportPage'
import { Verdict } from './components/Verdict'
import { checkResult } from './lib/labels'
import { findingsInRouteOrder, findingsVtt, loadReport, trackById } from './lib/report'
import {
  captionLabel,
  evidenceText,
  findingsByTier,
  isTracked,
  tierCounts,
  tierLabel,
  tierOf,
  verdictDisplay,
} from './lib/tier'
import type { Finding, Report, Track } from './types/report'

const mock = loadReport()

/** The two-tier shape the pipeline writes: a raw-video finding on a pseudo-track. */
function twoTier(base: Report = mock, rating: Report['verdict']['rating'] = 'caution'): Report {
  const pseudo: Track = {
    track_id: 'baseline-1',
    phrase: 'baseline (no SAM track)',
    object_id: 0,
    first_ms: 5_000,
    last_ms: 5_000,
    n_frames: 1,
    mean_conf: null,
    keyframe_index: 25,
    keyframe_ms: 5_000,
    keyframe_url: null,
    mask_url: null,
    boxes: [{ frame_index: 25, frame_ms: 5_000, x1: 10, y1: 500, x2: 700, y2: 640, conf: null }],
  }
  const possible: Finding = {
    finding_id: 'f9',
    check_id: 'missing_curb_ramp',
    title: 'Curb step with no ramp',
    severity: 'high',
    confidence: 0.88,
    track_id: 'baseline-1',
    frame_index: 25,
    frame_ms: 5_000,
    bbox: { x1: 10, y1: 500, x2: 700, y2: 640 },
    evidence_note: 'Possible barrier, seen by the raw-video pass only (no SAM track behind it). A curb step, no cut.',
    verify_manually: true,
    tier: 'possible',
    frame_url: null,
  }
  return {
    ...base,
    findings: [...base.findings.map((f) => ({ ...f, tier: 'confirmed' as const })), possible],
    tracks: [...base.tracks, pseudo],
    verdict: { ...base.verdict, rating, key_finding_ids: ['f9', ...(base.verdict.key_finding_ids ?? [])] },
  }
}

const report = twoTier()
const routeOrder = findingsInRouteOrder(report)
const byTier = findingsByTier(routeOrder)
const numberOf = new Map(byTier.map((f, i) => [f.finding_id, i + 1]))
const possible = report.findings.find((f) => f.finding_id === 'f9')!

describe('finding tiers', () => {
  it('treats reports without a tier as confirmed', () => {
    expect(mock.findings.every((f) => tierOf(f) === 'confirmed')).toBe(true)
    expect(tierCounts(mock.findings)).toEqual({ confirmed: 3, possible: 0 })
  })

  it('labels each tier in words', () => {
    expect(tierLabel(possible)).toBe('Possible: verify on site')
    expect(tierLabel(mock.findings[0])).toBe('Confirmed: object and frame cited')
  })

  it('numbers confirmed findings first, then possible ones, each in route order', () => {
    // f9 is first along the route (5 s) but possible: it comes last.
    expect(routeOrder[0].finding_id).toBe('f9')
    expect(byTier.map((f) => f.finding_id)).toEqual(['f2', 'f1', 'f3', 'f9'])
  })

  it('tells a SAM track from the raw-video pseudo-track', () => {
    const tracks = trackById(report)
    expect(isTracked(tracks.get('baseline-1'))).toBe(false)
    expect(isTracked(tracks.get(mock.findings[0].track_id))).toBe(true)
    expect(isTracked(undefined)).toBe(false)
  })

  it('drops the combiner prefix the badge already says', () => {
    expect(evidenceText(possible)).toBe('A curb step, no cut.')
    expect(evidenceText(mock.findings[0])).toBe(mock.findings[0].evidence_note)
  })
})

describe('verdict display', () => {
  it('never lists a possible finding as a key finding', () => {
    const v = verdictDisplay(report, routeOrder)
    expect(v.key.map((f) => f.finding_id)).toEqual(['f1'])
    expect(v.possible.map((f) => f.finding_id)).toEqual(['f9'])
    expect(v.rating).toBe('caution')
  })

  it('does not show "caution" when only possible findings caused it', () => {
    const onlyPossible = twoTier({ ...mock, findings: [] })
    const v = verdictDisplay(onlyPossible, findingsInRouteOrder(onlyPossible))
    expect(v.rating).toBe('none_confirmed')
    expect(v.key).toEqual([])
  })

  it('keeps the pipeline rating when confirmed findings set it', () => {
    const blocked = twoTier(mock, 'likely_blocked')
    expect(verdictDisplay(blocked, findingsInRouteOrder(blocked)).rating).toBe('likely_blocked')
  })

  it('counts each tier and lists the possible one apart', () => {
    const html = renderToStaticMarkup(<Verdict report={report} findings={routeOrder} numberOf={numberOf} onGo={() => {}} />)
    expect(html).toContain('<strong>3</strong> confirmed')
    expect(html).toContain('<strong>1</strong> possible')
    expect(html).toContain('Possible, not confirmed: check on site')
    // Key findings first, then the possible list: f9 (number 4) only in the second.
    const [keyPart, possiblePart] = html.split('Possible, not confirmed')
    expect(keyPart).not.toContain('4. Curb step')
    expect(possiblePart).toContain('4. Curb step with no ramp')
  })
})

describe('finding card', () => {
  const tracks = trackById(report)
  const render = (f: Finding) =>
    renderToStaticMarkup(
      <FindingCard
        finding={f}
        number={numberOf.get(f.finding_id)!}
        video={report.video}
        track={tracks.get(f.track_id)}
        related={[]}
        selected={false}
        inView={false}
      />,
    )

  it('badges a confirmed finding as cited', () => {
    const html = render(report.findings[0])
    expect(html).toContain('finding tier-confirmed')
    expect(html).toContain('<strong>Confirmed:</strong> object and frame cited')
    expect(html).toContain('Cited evidence: track')
  })

  it('badges a possible finding, says it does not count, and shows no fake track', () => {
    const html = render(possible)
    expect(html).toContain('finding tier-possible')
    expect(html).toContain('<strong>Possible:</strong> verify on site')
    expect(html).toContain('does not count toward the route verdict')
    expect(html).toContain('Finding 4, possible:')
    expect(html).not.toContain('Possible barrier, seen by the raw-video pass only')
    expect(html).not.toContain('baseline (no SAM track)')
    expect(html).not.toContain('Verify manually') // the tier badge already says so
  })

  it('draws the raw-video area dashed and calls it approximate', () => {
    const html = renderToStaticMarkup(
      <EvidenceFrame finding={{ ...possible, frame_url: '/f.jpg' }} video={report.video} track={tracks.get('baseline-1')} related={[]} />,
    )
    expect(html).toContain('box-possible')
    expect(html).toContain('area the raw-video pass named outlined (approximate)')
    expect(html).not.toContain('track baseline-1')
  })
})

describe('captions and checks', () => {
  it('captions name the tier in the same words as the card', () => {
    expect(captionLabel(possible)).toBe('Curb step with no ramp (possible, verify on site; high severity)')
    const vtt = findingsVtt(byTier, trackById(report), numberOf, 200, captionLabel)
    expect(vtt).toContain('4. Curb step with no ramp (possible, verify on site; high severity)')
    expect(vtt).toMatch(/1\. .*\(confirmed; medium severity, verify manually\)/)
  })

  it('splits check results by tier', () => {
    const c = { check_id: 'missing_curb_ramp' as const, status: 'ran' as const, n_findings: 1 }
    expect(checkResult(c, { confirmed: 0, possible: 1 })).toBe('1 possible barrier, to verify on site')
    expect(checkResult(c, { confirmed: 2, possible: 1 })).toBe('2 likely barriers (confirmed), 1 possible')
    expect(checkResult(c, { confirmed: 1, possible: 0 })).toBe('1 likely barrier (confirmed)')
    const html = renderToStaticMarkup(<ChecksTable checks={[c]} findings={report.findings} />)
    expect(html).toContain('1 possible barrier, to verify on site')
  })
})

describe('report page', () => {
  // ReportPage reads the URL hash for a linked finding while rendering.
  beforeAll(() => vi.stubGlobal('window', { location: { hash: '' } }))
  afterAll(() => vi.unstubAllGlobals())

  it('puts possible findings in their own, later section', () => {
    const html = renderToStaticMarkup(<ReportPage report={report} />)
    const confirmedAt = html.indexOf('Confirmed findings')
    const possibleAt = html.indexOf('Possible findings: verify on site')
    expect(confirmedAt).toBeGreaterThan(-1)
    expect(possibleAt).toBeGreaterThan(confirmedAt)
    expect(html).toContain('<ol class="findings" start="4">')
  })

  it('has no possible section for a report without possible findings', () => {
    expect(renderToStaticMarkup(<ReportPage report={mock} />)).not.toContain('Possible findings')
  })
})

describe('landing', () => {
  it('has a silent, captioned hero clip that falls back to a still', () => {
    const html = renderToStaticMarkup(<HeroMedia />)
    expect(html).toContain('src="/media/showcase/hero.mp4"')
    expect(html).toMatch(/<video[^>]* muted/)
    expect(html).not.toContain('autoplay') // play() is called only without reduced motion
    expect(html).toContain('kind="captions"')
    expect(html).toContain('class="hero-still"') // shown until the clip has loaded
  })

  it('explains the three steps in order', () => {
    const html = renderToStaticMarkup(<HowItWorks />)
    const steps = ['Film the walk', 'SAM 3.1 tracks every object', 'Review agent confirms each barrier with proof']
    const at = steps.map((s) => html.indexOf(s))
    expect(at.every((i) => i > -1)).toBe(true)
    expect([...at].sort((a, b) => a - b)).toEqual(at)
  })
})
