import type { CSSProperties, RefObject } from 'react'
import { SEVERITY_LABELS } from '../lib/labels'
import { adjacentFinding, boxAt, findingAnchor, findingsVtt } from '../lib/report'
import { formatClock } from '../lib/time'
import type { Finding, Track, VideoInfo } from '../types/report'
import { Box, Mask, Tag } from './Overlay'

interface Props {
  video: VideoInfo
  findings: Finding[]
  tracks: Map<string, Track>
  numberOf: Map<string, number>
  videoRef: RefObject<HTMLVideoElement | null>
  nowMs: number
  frameMs: number
  inView: Finding[]
  onSeek: (f: Finding) => void
  onOpen: (f: Finding) => void
  onUnavailable: () => void
}

function captionLabel(f: Finding): string {
  return `${f.title} (${SEVERITY_LABELS[f.severity].toLowerCase()}${f.verify_manually ? ', verify manually' : ''})`
}

/**
 * The walkthrough video (proxy.mp4, faces blurred) with the objects behind the
 * findings drawn on top while they are on screen: the SAM mask on the track's
 * keyframe when the report has one, the tracked box otherwise.
 */
export function RoutePlayer({
  video,
  findings,
  tracks,
  numberOf,
  videoRef,
  nowMs,
  frameMs,
  inView,
  onSeek,
  onOpen,
  onUnavailable,
}: Props) {
  const vtt = findingsVtt(findings, tracks, numberOf, frameMs, captionLabel)
  const prev = adjacentFinding(findings, nowMs, -1)
  const next = adjacentFinding(findings, nowMs, 1)

  const shapes = inView.flatMap((f) => {
    const t = tracks.get(f.track_id)
    const b = t ? boxAt(t, nowMs, frameMs) : undefined
    if (!t || !b) return []
    const n = numberOf.get(f.finding_id) ?? 0
    const mask = t.mask_url && b.frame_index === t.keyframe_index ? t.mask_url : null
    return [{ f, b, n, mask }]
  })

  return (
    <div className="player" style={{ '--ar': video.width / video.height } as CSSProperties}>
      <div className="player-video" style={{ aspectRatio: `${video.width} / ${video.height}` }}>
        <video
          ref={videoRef}
          src={video.proxy_url ?? undefined}
          controls
          playsInline
          preload="metadata"
          aria-label="Route walkthrough video"
          aria-describedby="player-help"
          onError={onUnavailable}
        >
          <track kind="captions" srcLang="en" label="Findings" src={`data:text/vtt;charset=utf-8,${encodeURIComponent(vtt)}`} />
        </video>
        <svg viewBox={`0 0 ${video.width} ${video.height}`} aria-hidden="true" focusable="false">
          {shapes.map(({ f, b, mask }) =>
            mask ? (
              <Mask key={f.finding_id} url={mask} width={video.width} height={video.height} />
            ) : (
              <Box key={f.finding_id} b={b} kind="cited" />
            ),
          )}
          {shapes.map(({ f, b, n }) => (
            <Tag key={f.finding_id} b={b} n={n} />
          ))}
        </svg>
      </div>

      <div className="player-side">
        <p className="player-time">
          At <strong>{formatClock(nowMs)}</strong> of {formatClock(video.duration_ms)}
        </p>
        <div className="player-nav">
          <button type="button" disabled={!prev} onClick={() => prev && onSeek(prev)}>
            <span aria-hidden="true">◀ </span>Previous finding
          </button>
          <button type="button" disabled={!next} onClick={() => next && onSeek(next)}>
            Next finding<span aria-hidden="true"> ▶</span>
          </button>
        </div>
        <div className="player-now" aria-live="polite">
          <h3>In view now</h3>
          {inView.length === 0 ? (
            <p className="muted">No finding at this point of the route.</p>
          ) : (
            <ul>
              {inView.map((f) => (
                <li key={f.finding_id}>
                  <a
                    href={`#${findingAnchor(f)}`}
                    onClick={(e) => {
                      e.preventDefault()
                      onOpen(f)
                    }}
                  >
                    {numberOf.get(f.finding_id)}. {f.title}
                  </a>{' '}
                  <span className="muted">({SEVERITY_LABELS[f.severity].toLowerCase()})</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
