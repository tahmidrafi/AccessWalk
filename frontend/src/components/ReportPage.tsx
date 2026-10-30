import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ChecksTable } from './ChecksTable'
import { FindingCard } from './FindingCard'
import { PdfButton } from './PdfButton'
import { RoutePlayer } from './RoutePlayer'
import { RunDetails } from './RunDetails'
import { Timeline } from './Timeline'
import { Verdict } from './Verdict'
import {
  findingAnchor,
  findingsInRouteOrder,
  findingsInView,
  samFrameMs,
  snapToSamFrame,
  trackById,
} from '../lib/report'
import { formatClock } from '../lib/time'
import { useVideoClock } from '../lib/useVideoClock'
import { usePageEntry } from '../lib/router'
import type { Finding, Report } from '../types/report'

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

export function ReportPage({ report }: { report: Report }) {
  const findings = useMemo(() => findingsInRouteOrder(report), [report])
  const tracks = useMemo(() => trackById(report), [report])
  const numberOf = useMemo(() => new Map(findings.map((f, i) => [f.finding_id, i + 1])), [findings])
  const frameMs = samFrameMs(report.video)
  // Page state (in-view list, playhead) changes once per SAM frame; only the overlay
  // follows the video frame by frame (see RoutePlayer).
  const snapSam = useCallback((ms: number) => snapToSamFrame(ms, frameMs), [frameMs])
  // A shared link to one finding (#finding-f1) opens on that finding.
  const [linkedId] = useState(
    () => findings.find((f) => `#${findingAnchor(f)}` === window.location.hash)?.finding_id ?? null,
  )
  const [selectedId, setSelectedId] = useState<string | null>(linkedId)
  const headingRef = useRef<HTMLHeadingElement>(null)
  usePageEntry(`${report.title} - AccessWalk report`, headingRef)
  const [videoOk, setVideoOk] = useState(Boolean(report.video.proxy_url))
  const videoRef = useRef<HTMLVideoElement>(null)
  const nowMs = useVideoClock(videoRef, snapSam)
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
  }, [linkedId])

  return (
    <>
      <div className="report-title">
        <h1 ref={headingRef} tabIndex={-1}>
          {report.title}
        </h1>
        <p className="muted">
          {formatClock(report.video.duration_ms)} walkthrough clip
          {report.run.agent_provider === 'mock' && <> · sample report with hand-written findings</>}
        </p>
        <PdfButton report={report} />
      </div>

      <Verdict report={report} findings={findings} numberOf={numberOf} onGo={goTo} />

      {report.disclaimer && (
        <aside className="disclaimer" aria-label="About this report">
          <p>{report.disclaimer}</p>
        </aside>
      )}

      {/* Interactive only (video, seek links): left out of the PDF. */}
      <section aria-labelledby="route-heading" className="no-print">
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
    </>
  )
}
