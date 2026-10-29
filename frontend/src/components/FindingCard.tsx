import { CHECK_LABELS, SEVERITY_LABELS } from '../lib/labels'
import { findingAnchor } from '../lib/report'
import { formatClock, formatSeconds } from '../lib/time'
import type { Finding, Track, VideoInfo } from '../types/report'
import { EvidenceFrame } from './EvidenceFrame'

interface Props {
  finding: Finding
  number: number
  video: VideoInfo
  track: Track | undefined
  related: Track[]
  selected: boolean
}

export function FindingCard({ finding: f, number, video, track, related, selected }: Props) {
  const headingId = `${findingAnchor(f)}-title`
  return (
    <article
      id={findingAnchor(f)}
      className={`finding sev-${f.severity}${selected ? ' finding-selected' : ''}`}
      aria-labelledby={headingId}
      tabIndex={-1}
    >
      <div className="finding-body">
        <header className="finding-header">
          <h3 id={headingId}>
            <span className="finding-number" aria-hidden="true">
              {number}
            </span>
            <span className="visually-hidden">Finding {number}: </span>
            {f.title}
          </h3>
          <ul className="finding-flags" aria-label="Flags">
            <li className={`badge badge-sev sev-${f.severity}`}>
              <span className="sev-shape" aria-hidden="true" />
              {SEVERITY_LABELS[f.severity]}
            </li>
            {f.verify_manually && (
              <li className="badge badge-verify">
                <span aria-hidden="true">⚠ </span>Verify manually
              </li>
            )}
          </ul>
        </header>

        <dl className="finding-facts">
          <div>
            <dt>Where</dt>
            <dd>
              {formatClock(f.frame_ms)} into the clip
              {f.location_tag && <>, {f.location_tag}</>}
            </dd>
          </div>
          <div>
            <dt>Check</dt>
            <dd>{CHECK_LABELS[f.check_id]}</dd>
          </div>
          <div>
            <dt>Confidence</dt>
            <dd>{Math.round(f.confidence * 100)}%</dd>
          </div>
        </dl>

        <p className="finding-evidence">{f.evidence_note}</p>
        {f.verify_manually && (
          <p className="finding-verify-note">
            Rests on depth, height or slope judged from video alone. Check it on site before relying on it.
          </p>
        )}
        {f.reference && (
          <p className="finding-reference">
            <span className="label">For context:</span> {f.reference}
          </p>
        )}
        <p className="finding-cite">
          Cited evidence: track <code>{f.track_id}</code>
          {track && (
            <>
              {' '}
              ({track.phrase}, seen {formatSeconds(track.first_ms)} to {formatSeconds(track.last_ms)} over{' '}
              {track.n_frames} frames)
            </>
          )}
          , frame {f.frame_index}.
        </p>
      </div>
      <EvidenceFrame finding={f} video={video} track={track} related={related} />
    </article>
  )
}
