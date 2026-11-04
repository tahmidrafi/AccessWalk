import { useState } from 'react'
import { boxOnFrame } from '../lib/report'
import { isTracked } from '../lib/tier'
import { formatClock, formatSeconds } from '../lib/time'
import type { Finding, Track, VideoInfo } from '../types/report'
import { Box, Mask } from './Overlay'

interface Props {
  finding: Finding
  video: VideoInfo
  track: Track | undefined
  related: Track[]
}

/**
 * The cited frame (sam.mp4 pixels, faces and plates already blurred by the
 * pipeline) with the finding's object drawn on top: its SAM mask when the
 * report has one for this frame (masks are rendered for the track's keyframe),
 * else its box. Related tracks that are on the same frame get a dashed box.
 */
export function EvidenceFrame({ finding, video, track, related }: Props) {
  const [failed, setFailed] = useState(!finding.frame_url)
  // A raw-video ("possible") finding usually has a pseudo-track, not a SAM object:
  // its box is the model's approximate area, drawn dashed and described as such.
  const tracked = isTracked(track)
  const phrase = tracked ? track.phrase : track ? 'area the raw-video pass named' : 'object'
  const relatedHere = related
    .map((t) => ({ t, b: boxOnFrame(t, finding.frame_index) }))
    .filter((r): r is { t: Track; b: NonNullable<typeof r.b> } => r.b !== undefined)
  const relatedElsewhere = related.filter((t) => !relatedHere.some((r) => r.t === t))
  const maskUrl = tracked && track.mask_url && track.keyframe_index === finding.frame_index ? track.mask_url : null
  const alt = `Video frame at ${formatClock(finding.frame_ms)} with the ${phrase} outlined${tracked || !track ? '' : ' (approximate)'}. Faces and license plates are blurred.`
  const boxText = maskUrl ? 'Outlined and tinted' : tracked || !track ? 'Solid box' : 'Dashed box (approximate)'

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
          {maskUrl ? (
            <Mask url={maskUrl} width={video.width} height={video.height} />
          ) : (
            <Box b={finding.bbox} kind={tracked || !track ? 'cited' : 'possible'} />
          )}
        </svg>
      </div>
      <figcaption>
        Frame {finding.frame_index} at {formatSeconds(finding.frame_ms)}. {boxText}: {phrase}
        {tracked && <> (track {track.track_id})</>}.
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
