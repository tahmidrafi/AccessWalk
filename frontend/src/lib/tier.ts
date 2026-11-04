import { SEVERITY_LABELS } from './labels'
import type { Finding, Report, RouteVerdict, Track } from '../types/report'

/**
 * Two-tier review (Nov 4): "confirmed" findings are cited to a SAM track and a
 * frame by the review agent; "possible" ones were seen only by the raw-video pass
 * (Muse Spark 1.3 watching the whole clip), usually with no SAM track behind them.
 * Possible findings are always verify_manually and never drive the verdict display.
 */
export type Tier = 'confirmed' | 'possible'

/** Reports from before the two-tier review have no tier: everything was cited. */
export function tierOf(f: Finding): Tier {
  return f.tier === 'possible' ? 'possible' : 'confirmed'
}

export function isPossible(f: Finding): boolean {
  return tierOf(f) === 'possible'
}

export const TIER_TEXT: Record<Tier, { badge: string; detail: string; short: string }> = {
  confirmed: { badge: 'Confirmed', detail: 'object and frame cited', short: 'confirmed' },
  possible: { badge: 'Possible', detail: 'verify on site', short: 'possible, verify on site' },
}

/** "Confirmed: object and frame cited" / "Possible: verify on site". */
export function tierLabel(f: Finding): string {
  const t = TIER_TEXT[tierOf(f)]
  return `${t.badge}: ${t.detail}`
}

export interface TierCounts {
  confirmed: number
  possible: number
}

export function tierCounts(findings: Finding[]): TierCounts {
  const possible = findings.filter(isPossible).length
  return { confirmed: findings.length - possible, possible }
}

/**
 * Numbering order: confirmed findings first, then possible ones, each in the
 * order you reach them along the route. The numbers on the timeline, video
 * overlay, captions and cards all follow this, so the cited findings read first.
 */
export function findingsByTier(routeOrder: Finding[]): Finding[] {
  return [...routeOrder.filter((f) => !isPossible(f)), ...routeOrder.filter(isPossible)]
}

/** The pipeline's pseudo-track for a raw-video finding has phrase "baseline (no SAM track)". */
export function isTracked(track: Track | undefined): track is Track {
  return track !== undefined && !track.phrase.startsWith('baseline')
}

// The combiner prefixes the note of an untracked possible finding; the badge and
// the card's own note say the same thing, so the page drops the repeat.
const POSSIBLE_PREFIX = /^Possible barrier, seen by the raw-video pass only \(no SAM track behind it\)\.\s*/

export function evidenceText(f: Finding): string {
  return isPossible(f) ? f.evidence_note.replace(POSSIBLE_PREFIX, '') : f.evidence_note
}

export interface VerdictDisplay {
  rating: RouteVerdict['rating'] | 'none_confirmed'
  /** Confirmed key findings, in the verdict's order. */
  key: Finding[]
  /** Every possible finding, in route order: listed apart, never as key findings. */
  possible: Finding[]
}

/**
 * What the verdict box shows. The rating comes from the pipeline (already from
 * confirmed findings only for "likely blocked"); when a route is "caution" only
 * because of possible findings, the box says no barrier was confirmed instead.
 */
export function verdictDisplay(report: Report, routeOrder: Finding[]): VerdictDisplay {
  const { rating, key_finding_ids = [] } = report.verdict
  const byId = new Map(routeOrder.map((f) => [f.finding_id, f]))
  const key = key_finding_ids.flatMap((id) => byId.get(id) ?? []).filter((f) => !isPossible(f))
  const possible = routeOrder.filter(isPossible)
  const counts = tierCounts(routeOrder)
  const shown =
    rating === 'caution' && counts.confirmed === 0 && counts.possible > 0 ? 'none_confirmed' : rating
  return { rating: shown, key, possible }
}

/** Caption per finding, in the same words as its card: "3. Curb step ... (possible, verify on site; high severity)". */
export function captionLabel(f: Finding): string {
  const sev = SEVERITY_LABELS[f.severity].toLowerCase()
  if (isPossible(f)) return `${f.title} (${TIER_TEXT.possible.short}; ${sev})`
  return `${f.title} (${TIER_TEXT.confirmed.short}; ${sev}${f.verify_manually ? ', verify manually' : ''})`
}
