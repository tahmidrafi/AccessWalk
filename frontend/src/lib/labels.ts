import type { CheckSummary, Finding, Report, RouteVerdict } from '../types/report'

export const CHECK_LABELS: Record<Finding['check_id'], string> = {
  sidewalk_obstruction: 'Sidewalk obstruction',
  surface_damage: 'Surface damage',
  missing_curb_ramp: 'Missing curb ramp',
  sidewalk_ends: 'Sidewalk ends',
  steps_without_ramp: 'Steps without a ramp',
  missing_handrail: 'Missing handrail',
  round_doorknob: 'Round doorknob',
  narrow_passage: 'Narrow passage',
}

export const SEVERITY_LABELS: Record<Finding['severity'], string> = {
  high: 'High severity',
  medium: 'Medium severity',
  low: 'Low severity',
}

export const SEVERITY_ORDER: Record<Finding['severity'], number> = { high: 0, medium: 1, low: 2 }

export const RATING_TEXT: Record<RouteVerdict['rating'], { label: string; icon: string }> = {
  no_likely_barriers: { label: 'No likely barriers found', icon: '✓' },
  caution: { label: 'Caution: likely barriers on this route', icon: '!' },
  likely_blocked: { label: 'Likely blocked for a wheelchair', icon: '✕' },
}

/** Verdict box when the only findings are "possible" ones (see lib/tier.ts). */
export const NONE_CONFIRMED_TEXT = { label: 'No barriers confirmed: possible ones to check on site', icon: '?' }

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

/**
 * ``tiers``: this check's findings split by tier (two-tier reports). Without it
 * every finding counts as a likely barrier, as in reports before the split.
 */
export function checkResult(c: CheckSummary, tiers?: { confirmed: number; possible: number }): string {
  const n = tiers ? tiers.confirmed + tiers.possible : (c.n_findings ?? 0)
  switch (c.status) {
    case 'ran':
      if (n === 0) return 'Checked, nothing found'
      if (!tiers) return plural(n, 'likely barrier')
      if (tiers.possible === 0) return `${plural(n, 'likely barrier')} (confirmed)`
      if (tiers.confirmed === 0) return `${plural(tiers.possible, 'possible barrier')}, to verify on site`
      return `${plural(tiers.confirmed, 'likely barrier')} (confirmed), ${tiers.possible} possible`
    case 'not_applicable':
      return 'Not applicable'
    case 'dropped':
      return 'Not reported (check not reliable enough yet)'
  }
}

/** Default file name for "Save as PDF": the document title at print time. */
export function pdfTitle(report: Report): string {
  const day = report.run.created_at.slice(0, 10)
  return `AccessWalk report - ${report.title}${day ? ` (${day})` : ''}`
}
