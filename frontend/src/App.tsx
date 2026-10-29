import { useCallback, useEffect, useRef, useState } from 'react'
import { ChecksTable } from './components/ChecksTable'
import { FindingCard } from './components/FindingCard'
import { RoutePlayer } from './components/RoutePlayer'
import { RunDetails } from './components/RunDetails'
import { Timeline } from './components/Timeline'
import { Verdict } from './components/Verdict'
import {
  findingAnchor,
  findingsInRouteOrder,
  findingsInView,
  loadReport,
  samFrameMs,
  trackById,
} from './lib/report'
import { formatClock } from './lib/time'
import { useVideoClock } from './lib/useVideoClock'
import type { Finding } from './types/report'

const report = loadReport()
const findings = findingsInRouteOrder(report)
const tracks = trackById(report)
const numberOf = new Map(findings.map((f, i) => [f.finding_id, i + 1]))
const frameMs = samFrameMs(report.video)
// A shared link to one finding (#finding-f1) opens on that finding.
const linkedId = findings.find((f) => `#${findingAnchor(f)}` === window.location.hash)?.finding_id ?? null

function prefersReducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function scrollBehavior(animate = true): ScrollBehavior {
  return animate && !prefersReducedMotion() ? 'smooth' : 'instant'
}

// Move focus (not just scroll) so keyboard and screen-reader users land on the finding.
function focusFinding(findingId: string, animate = true) {
  const el = document.getElementById(`finding-${findingId}`)
  if (!el) return
  el.scrollIntoView({ behavior: scrollBehavior(animate), block: 'start' })
  el.focus({ preventScroll: true })
}

export default function App() {
  const [selectedId, setSelectedId] = useState<string | null>(linkedId)
  const [videoOk, setVideoOk] = useState(Boolean(report.video.proxy_url))
  const videoRef = useRef<HTMLVideoElement>(null)
  const nowMs = useVideoClock(videoRef, frameMs)
  const inView = videoOk ? findingsInView(findings, tracks, nowMs, frameMs) : []
  const inViewIds = new Set(inView.map((f) => f.finding_id))

  // Jump to a finding's evidence card.
  const goTo = useCallback((f: Finding) => {
    setSelectedId(f.finding_id)
    focusFinding(f.finding_id)
    history.replaceState(null, '', `#${findingAnchor(f)}`)
  }, [])

  // Pause the video on a finding's cited frame. Focus stays where it is (a timeline
  // mark, Previous/Next) unless asked to move to the video, e.g. from a finding card.
  const seekTo = useCallback(
    (f: Finding, focusVideo = false) => {
      const v = videoRef.current
      if (!v) {
        goTo(f)
        return
      }
      setSelectedId(f.finding_id)
      v.pause()
      v.currentTime = (f.frame_ms + 1) / 1000 // +1 ms so float rounding stays on this SAM frame
      v.scrollIntoView({ behavior: scrollBehavior(), block: 'nearest' })
      if (focusVideo) v.focus({ preventScroll: true })
    },
    [goTo],
  )

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

        <section aria-labelledby="route-heading">
          <h2 id="route-heading">Along the route</h2>
          {videoOk ? (
            <>
              <p className="section-intro" id="player-help">
                Play the walkthrough to see the object behind each finding outlined while it is in view. Select a
                numbered mark, or Previous / Next finding, to jump the video there. Captions (CC) name each finding.
              </p>
              <RoutePlayer
                video={report.video}
                findings={findings}
                tracks={tracks}
                numberOf={numberOf}
                videoRef={videoRef}
                nowMs={nowMs}
                frameMs={frameMs}
                inView={inView}
                onSeek={seekTo}
                onOpen={goTo}
                onUnavailable={() => setVideoOk(false)}
              />
            </>
          ) : (
            <p className="section-intro">
              {report.video.proxy_url && <>The walkthrough video is not available here. </>}
              Each mark is a finding at its point in the {formatClock(report.video.duration_ms)} clip, from start
              (left) to end (right). Select a mark to jump to its evidence.
            </p>
          )}
          <Timeline
            findings={findings}
            durationMs={report.video.duration_ms}
            numberOf={numberOf}
            selectedId={selectedId}
            inViewIds={inViewIds}
            nowMs={videoOk ? nowMs : null}
            onGo={videoOk ? seekTo : goTo}
          />
        </section>

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
                    inView={inViewIds.has(f.finding_id)}
                    onShowInVideo={videoOk ? () => seekTo(f, true) : undefined}
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
