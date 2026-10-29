import { useState } from 'react'
import { boxOnFrame } from '../lib/report'
import { formatClock, formatSeconds } from '../lib/time'
import type { BBox, Finding, Track, VideoInfo } from '../types/report'

interface Props {
  finding: Finding
  video: VideoInfo
  track: Track | undefined
  related: Track[]
}

function Box({ b, kind }: { b: BBox; kind: 'cited' | 'related' }) {
  const props = { x: b.x1, y: b.y1, width: b.x2 - b.x1, height: b.y2 - b.y1 }
  // Two strokes (dark under light) so the box reads on any background.
  return (
    <g className={`box box-${kind}`}>
      <rect {...props} className="box-under" />
      <rect {...props} className="box-over" />
    </g>
  )
}

/**
 * The cited frame (sam.mp4 pixels, faces and plates already blurred by the
 * pipeline) with the finding's box drawn on top. Related tracks that are on the
 * same frame get a dashed box.
 */
export function EvidenceFrame({ finding, video, track, related }: Props) {
  const [failed, setFailed] = useState(!finding.frame_url)
  const phrase = track?.phrase ?? 'object'
  const relatedHere = related
    .map((t) => ({ t, b: boxOnFrame(t, finding.frame_index) }))
    .filter((r): r is { t: Track; b: NonNullable<typeof r.b> } => r.b !== undefined)
  const relatedElsewhere = related.filter((t) => !relatedHere.some((r) => r.t === t))
  const alt = `Video frame at ${formatClock(finding.frame_ms)} with the ${phrase} outlined. Faces and license plates are blurred.`

  return (
    <figure className="evidence">
      <div className="evidence-frame" style={{ aspectRatio: `${video.width} / ${video.height}` }}>
        {failed ? (
          <div className="evidence-missing">
            <span>Frame image not available</span>
          </div>
        ) : (
          <img src={finding.frame_url ?? undefined} alt={alt} onError={() => setFailed(true)} />
        )}
        <svg viewBox={`0 0 ${video.width} ${video.height}`} aria-hidden="true" focusable="false">
          {relatedHere.map(({ t, b }) => (
            <Box key={t.track_id} b={b} kind="related" />
          ))}
          <Box b={finding.bbox} kind="cited" />
        </svg>
      </div>
      <figcaption>
        Frame {finding.frame_index} at {formatSeconds(finding.frame_ms)}. Solid box: {phrase}
        {track && <> (track {track.track_id})</>}.
        {relatedHere.length > 0 && <> Dashed: {relatedHere.map(({ t }) => t.phrase).join(', ')}.</>}
        {relatedElsewhere.map((t) => (
          <span key={t.track_id}>
            {' '}
            Related: {t.phrase}, seen {formatSeconds(t.first_ms)} to {formatSeconds(t.last_ms)}.
          </span>
        ))}
      </figcaption>
    </figure>
  )
}
