import type { CSSProperties } from 'react'
import { SEVERITY_LABELS } from '../lib/labels'
import { findingAnchor, timelineRows } from '../lib/report'
import { formatClock, spokenTime } from '../lib/time'
import type { Finding } from '../types/report'

interface Props {
  findings: Finding[]
  durationMs: number
  numberOf: Map<string, number>
  selectedId: string | null
  inViewIds: Set<string>
  /** Video time for the playhead; null when there is no video. */
  nowMs: number | null
  onGo: (f: Finding) => void
}

/** Tick spacing that gives 3-6 labelled ticks for 15-60 s clips. */
function tickStep(durationMs: number): number {
  return durationMs <= 30_000 ? 5_000 : 10_000
}

/**
 * Where each finding sits along the clip. A navigation strip, not a chart: each
 * mark is a link to its finding, in route order, so keyboard and screen-reader
 * users get the same list in the same order. With a video, selecting a mark seeks
 * the video there; the playhead and the in-view ring follow playback.
 */
export function Timeline({ findings, durationMs, numberOf, selectedId, inViewIds, nowMs, onGo }: Props) {
  const rows = timelineRows(findings, durationMs)
  const nRows = Math.max(1, ...[...rows.values()].map((r) => r + 1))
  const step = tickStep(durationMs)
  const ticks: number[] = []
  for (let t = 0; t <= durationMs; t += step) ticks.push(t)
  const pct = (ms: number) => `${(100 * Math.min(ms, durationMs)) / durationMs}%`

  return (
    <>
      <p className="visually-hidden" id="timeline-help">
        Findings timeline, from the start of the {formatClock(durationMs)} clip to the end.
      </p>
      <div className="timeline" style={{ '--rows': nRows } as CSSProperties}>
        <div className="timeline-inner">
          <ol className="timeline-marks" aria-describedby="timeline-help">
            {findings.map((f) => {
              const n = numberOf.get(f.finding_id)
              const selected = f.finding_id === selectedId
              return (
                <li
                  key={f.finding_id}
                  className="timeline-mark"
                  style={{ left: pct(f.frame_ms), '--row': rows.get(f.finding_id) ?? 0 } as CSSProperties}
                >
                  <a
                    href={`#${findingAnchor(f)}`}
                    className={`mark sev-${f.severity}${f.verify_manually ? ' mark-verify' : ''}${inViewIds.has(f.finding_id) ? ' mark-inview' : ''}`}
                    aria-current={selected ? 'true' : undefined}
                    aria-label={`Finding ${n} at ${spokenTime(f.frame_ms)}: ${f.title}. ${SEVERITY_LABELS[f.severity]}${f.verify_manually ? ', verify manually' : ''}.`}
                    onClick={(e) => {
                      e.preventDefault()
                      onGo(f)
                    }}
                  >
                    {n}
                  </a>
                </li>
              )
            })}
          </ol>
          {nowMs !== null && <div className="playhead" style={{ left: pct(nowMs) }} aria-hidden="true" />}
          <div className="timeline-axis" aria-hidden="true">
            {ticks.map((t) => (
              <span key={t} className="tick" style={{ left: pct(t) }}>
                {formatClock(t)}
              </span>
            ))}
          </div>
        </div>
      </div>
      {findings.length === 0 && <p>No findings along this clip.</p>}
    </>
  )
}
