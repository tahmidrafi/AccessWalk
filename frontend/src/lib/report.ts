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

/** Length of one SAM frame in ms (200 at 5 fps): a box holds until the next one. */
export function samFrameMs(video: { sam_fps: number }): number {
  return 1000 / video.sam_fps
}

/** Snap a video time to the start of its SAM frame (with 1 ms slack for float seeks). */
export function snapToSamFrame(ms: number, frameMs: number): number {
  return Math.floor((ms + 1) / frameMs) * frameMs
}

/** The track's box on screen at video time ``ms``: its last SAM box at or before
 * ``ms``, if that box is less than one SAM frame old. */
export function boxAt(track: Track, ms: number, frameMs: number): TrackBox | undefined {
  let found: TrackBox | undefined
  for (const b of track.boxes) {
    if (b.frame_ms <= ms && (!found || b.frame_ms > found.frame_ms)) found = b
  }
  return found && ms - found.frame_ms < frameMs ? found : undefined
}

/** Findings whose cited object is tracked on screen at video time ``ms``. */
export function findingsInView(findings: Finding[], tracks: Map<string, Track>, ms: number, frameMs: number): Finding[] {
  return findings.filter((f) => {
    const t = tracks.get(f.track_id)
    return t ? boxAt(t, ms, frameMs) !== undefined : Math.abs(ms - f.frame_ms) < frameMs
  })
}

/** Next finding strictly after ``ms`` / last one strictly before it, in route order. */
export function adjacentFinding(findings: Finding[], ms: number, dir: 1 | -1): Finding | undefined {
  const sorted = [...findings].sort((a, b) => a.frame_ms - b.frame_ms)
  return dir === 1 ? sorted.find((f) => f.frame_ms > ms) : sorted.findLast((f) => f.frame_ms < ms)
}

function vttTime(ms: number): string {
  const h = Math.floor(ms / 3_600_000)
  const m = Math.floor(ms / 60_000) % 60
  const s = (ms % 60_000) / 1000
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${s.toFixed(3).padStart(6, '0')}`
}

/**
 * WebVTT captions naming each finding while its object is on screen. The clips
 * have no narration to caption, so this makes the findings readable in the
 * player itself (also full screen) without relying on the overlay colours.
 */
export function findingsVtt(
  findings: Finding[],
  tracks: Map<string, Track>,
  numberOf: Map<string, number>,
  frameMs: number,
  label: (f: Finding) => string,
): string {
  const cues = findings.map((f) => {
    const t = tracks.get(f.track_id)
    const start = t?.first_ms ?? f.frame_ms
    const end = (t?.last_ms ?? f.frame_ms) + frameMs
    return `${vttTime(start)} --> ${vttTime(end)}\n${numberOf.get(f.finding_id)}. ${label(f)}`
  })
  return ['WEBVTT', ...cues].join('\n\n') + '\n'
}
