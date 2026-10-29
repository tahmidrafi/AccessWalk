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

export function checkResult(c: CheckSummary): string {
  const n = c.n_findings ?? 0
  switch (c.status) {
    case 'ran':
      return n === 0 ? 'Checked, nothing found' : `${n} likely ${n === 1 ? 'barrier' : 'barriers'}`
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
