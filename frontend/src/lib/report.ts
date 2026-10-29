import mockReport from '../mock/report.json'
import type { Finding, Report, Track, TrackBox } from '../types/report'

/** The report this page shows. Mock data until the upload/job flow lands (d6-fewire). */
export function loadReport(): Report {
  return mockReport as Report
}

/** Findings in the order you meet them walking the route. */
export function findingsInRouteOrder(report: Report): Finding[] {
  return [...report.findings].sort((a, b) => a.frame_ms - b.frame_ms || a.finding_id.localeCompare(b.finding_id))
}

export function trackById(report: Report): Map<string, Track> {
  return new Map(report.tracks.map((t) => [t.track_id, t]))
}

export function boxOnFrame(track: Track, frameIndex: number): TrackBox | undefined {
  return track.boxes.find((b) => b.frame_index === frameIndex)
}

/**
 * Put timeline marks that would overlap on separate rows. ``minGap`` is a fraction
 * of the clip length; marks closer than that to the previous mark on a row move
 * to the next row. Returns the row index per finding id.
 */
export function timelineRows(findings: Finding[], durationMs: number, minGap = 0.08): Map<string, number> {
  const lastOnRow: number[] = []
  const rows = new Map<string, number>()
  for (const f of [...findings].sort((a, b) => a.frame_ms - b.frame_ms)) {
    const x = f.frame_ms / durationMs
    let row = lastOnRow.findIndex((last) => x - last >= minGap)
    if (row === -1) row = lastOnRow.length
    lastOnRow[row] = x
    rows.set(f.finding_id, row)
  }
  return rows
}

export function findingAnchor(f: Finding): string {
  return `finding-${f.finding_id}`
}
