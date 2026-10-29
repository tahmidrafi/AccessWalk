import mockReport from '../mock/report.json'
import type { BBox, Finding, Report, Track, TrackBox } from '../types/report'

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

const byFrame = new WeakMap<Track, TrackBox[]>()

function boxesByFrame(track: Track): TrackBox[] {
  let sorted = byFrame.get(track)
  if (!sorted) {
    sorted = [...track.boxes].sort((a, b) => a.frame_index - b.frame_index)
    byFrame.set(track, sorted)
  }
  return sorted
}

/** A box to draw at some video time, and the SAM box it starts from. */
export interface MovingBox {
  bbox: BBox
  from: TrackBox
}

/**
 * The track's box at video time ``ms``, moving smoothly: linear interpolation
 * between its SAM boxes on two consecutive SAM frames. Where the next SAM frame
 * has no box for this track (a gap, or the track's end) nothing is interpolated
 * or extrapolated: the last box holds for one SAM frame, as in ``boxAt``, then
 * the track is off screen until its next box.
 */
export function interpolatedBoxAt(track: Track, ms: number, frameMs: number): MovingBox | undefined {
  const boxes = boxesByFrame(track)
  let lo = 0
  let hi = boxes.length - 1
  let i = -1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (boxes[mid].frame_ms <= ms) {
      i = mid
      lo = mid + 1
    } else {
      hi = mid - 1
    }
  }
  if (i < 0) return undefined
  const a = boxes[i]
  const b = boxes[i + 1]
  if (b && b.frame_index === a.frame_index + 1) {
    const u = (ms - a.frame_ms) / (b.frame_ms - a.frame_ms)
    const lerp = (p: number, q: number) => p + (q - p) * u
    return { bbox: { x1: lerp(a.x1, b.x1), y1: lerp(a.y1, b.y1), x2: lerp(a.x2, b.x2), y2: lerp(a.y2, b.y2) }, from: a }
  }
  if (ms - a.frame_ms >= frameMs) return undefined
  return { bbox: { x1: a.x1, y1: a.y1, x2: a.x2, y2: a.y2 }, from: a }
}

/** What the player draws for one finding at video time ``ms``. */
export interface OverlayShape {
  finding: Finding
  n: number
  bbox: BBox
  /** The track's keyframe mask, drawn instead of the box during that SAM frame. */
  mask: string | null
}

export function overlayShapes(
  findings: Finding[],
  tracks: Map<string, Track>,
  numberOf: Map<string, number>,
  ms: number,
  frameMs: number,
): OverlayShape[] {
  return findings.flatMap((f) => {
    const t = tracks.get(f.track_id)
    const box = t && interpolatedBoxAt(t, ms, frameMs)
    if (!t || !box) return []
    const mask = t.mask_url && box.from.frame_index === t.keyframe_index ? t.mask_url : null
    return [{ finding: f, n: numberOf.get(f.finding_id) ?? 0, bbox: box.bbox, mask }]
  })
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
