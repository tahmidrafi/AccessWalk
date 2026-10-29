import { useCallback, useEffect, useState } from 'react'
import { ChecksTable } from './components/ChecksTable'
import { FindingCard } from './components/FindingCard'
import { RunDetails } from './components/RunDetails'
import { Timeline } from './components/Timeline'
import { Verdict } from './components/Verdict'
import { findingAnchor, findingsInRouteOrder, loadReport, trackById } from './lib/report'
import { formatClock } from './lib/time'
import type { Finding } from './types/report'

const report = loadReport()
const findings = findingsInRouteOrder(report)
const tracks = trackById(report)
const numberOf = new Map(findings.map((f, i) => [f.finding_id, i + 1]))
// A shared link to one finding (#finding-f1) opens on that finding.
const linkedId = findings.find((f) => `#${findingAnchor(f)}` === window.location.hash)?.finding_id ?? null

function prefersReducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

// Move focus (not just scroll) so keyboard and screen-reader users land on the finding.
function focusFinding(findingId: string, animate = true) {
  const el = document.getElementById(`finding-${findingId}`)
  if (!el) return
  el.scrollIntoView({ behavior: animate && !prefersReducedMotion() ? 'smooth' : 'instant', block: 'start' })
  el.focus({ preventScroll: true })
}

export default function App() {
  const [selectedId, setSelectedId] = useState<string | null>(linkedId)

  const goTo = useCallback((f: Finding) => {
    setSelectedId(f.finding_id)
    focusFinding(f.finding_id)
    history.replaceState(null, '', `#${findingAnchor(f)}`)
  }, [])

  useEffect(() => {
    if (linkedId) focusFinding(linkedId, false)
  }, [])

  return (
    <>
      <a className="skip-link" href="#findings-heading">
        Skip to findings
      </a>
      <header className="site-header">
        <p className="brand">AccessWalk</p>
        <p className="tagline">Know before you go: accessibility report from a phone walkthrough</p>
      </header>
      <main id="main">
        <div className="report-title">
          <h1>{report.title}</h1>
          <p className="muted">
            {formatClock(report.video.duration_ms)} walkthrough clip
            {report.run.agent_provider === 'mock' && <> · sample report with hand-written findings</>}
          </p>
        </div>

        <Verdict report={report} findings={findings} numberOf={numberOf} onGo={goTo} />

        {report.disclaimer && (
          <aside className="disclaimer" aria-label="About this report">
            <p>{report.disclaimer}</p>
          </aside>
        )}

        <Timeline
          findings={findings}
          durationMs={report.video.duration_ms}
          numberOf={numberOf}
          selectedId={selectedId}
          onGo={goTo}
        />

        <section aria-labelledby="findings-heading">
          <h2 id="findings-heading" tabIndex={-1}>
            Findings <span className="count">({findings.length})</span>
          </h2>
          <p className="section-intro">
            In the order you reach them along the route. Each one cites the tracked object and the video frame it
            rests on.
          </p>
          {findings.length === 0 ? (
            <p>No likely barriers were found on this clip.</p>
          ) : (
            <ol className="findings">
              {findings.map((f) => (
                <li key={f.finding_id}>
                  <FindingCard
                    finding={f}
                    number={numberOf.get(f.finding_id) ?? 0}
                    video={report.video}
                    track={tracks.get(f.track_id)}
                    related={(f.related_track_ids ?? []).flatMap((id) => tracks.get(id) ?? [])}
                    selected={f.finding_id === selectedId}
                  />
                </li>
              ))}
            </ol>
          )}
        </section>

        <ChecksTable checks={report.checks} />
        <RunDetails report={report} />
      </main>
    </>
  )
}
