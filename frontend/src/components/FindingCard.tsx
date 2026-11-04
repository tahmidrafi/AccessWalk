import { CHECK_LABELS, SEVERITY_LABELS } from '../lib/labels'
import { findingAnchor } from '../lib/report'
import { TIER_TEXT, evidenceText, isTracked, tierOf } from '../lib/tier'
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
  inView: boolean
  /** Seek the video to this finding; absent when there is no video. */
  onShowInVideo?: () => void
}

/** "Confirmed: object and frame cited" / "Possible: verify on site", as text plus a shape. */
export function TierBadge({ finding }: { finding: Finding }) {
  const tier = tierOf(finding)
  const t = TIER_TEXT[tier]
  return (
    <span className={`badge badge-tier tier-${tier}`}>
      <span className="tier-shape" aria-hidden="true" />
      <span>
        <strong>{t.badge}:</strong> {t.detail}
      </span>
    </span>
  )
}

export function FindingCard({ finding: f, number, video, track, related, selected, inView, onShowInVideo }: Props) {
  const headingId = `${findingAnchor(f)}-title`
  const tier = tierOf(f)
  const tracked = isTracked(track)
  return (
    <article
      id={findingAnchor(f)}
      className={`finding tier-${tier} sev-${f.severity}${selected ? ' finding-selected' : ''}${inView ? ' finding-inview' : ''}`}
      aria-labelledby={headingId}
      tabIndex={-1}
    >
      <div className="finding-body">
        <header className="finding-header">
          <h3 id={headingId}>
            <span className="finding-number" aria-hidden="true">
              {number}
            </span>
            <span className="visually-hidden">
              Finding {number}, {TIER_TEXT[tier].badge.toLowerCase()}:{' '}
            </span>
            {f.title}
          </h3>
          <dl className="finding-facts">
            <div>
              <dt>Check</dt>
              <dd>{CHECK_LABELS[f.check_id]}</dd>
            </div>
            <div>
              <dt>Where</dt>
              <dd>
                {formatClock(f.frame_ms)} into the clip
                {f.location_tag && <>, {f.location_tag}</>}
              </dd>
            </div>
            <div>
              <dt>Confidence</dt>
              <dd>{Math.round(f.confidence * 100)}%</dd>
            </div>
          </dl>
          <ul className="finding-flags" aria-label="Flags">
            <li>
              <TierBadge finding={f} />
            </li>
            <li className={`badge badge-sev sev-${f.severity}`}>
              <span className="sev-shape" aria-hidden="true" />
              {SEVERITY_LABELS[f.severity]}
            </li>
            {f.verify_manually && tier === 'confirmed' && (
              <li className="badge badge-verify">
                <span aria-hidden="true">⚠ </span>Verify manually
              </li>
            )}
            {inView && (
              <li className="badge badge-inview no-print">
                <span aria-hidden="true">● </span>In view in the video
              </li>
            )}
          </ul>
        </header>

        <p className="finding-evidence">{evidenceText(f)}</p>

        {tier === 'possible' ? (
          <p className="finding-tier-note">
            <strong>Not confirmed.</strong> Seen by the raw-video pass only
            {tracked ? '' : ', with no tracked object behind it'}. It does not count toward the route verdict: check it
            on site before relying on it.
          </p>
        ) : (
          f.verify_manually && (
            <p className="finding-verify-note">
              Rests on depth, height or slope judged from video alone. Check it on site before relying on it.
            </p>
          )
        )}

        {f.reference && (
          <p className="finding-reference">
            <span className="label">For context:</span> {f.reference}
          </p>
        )}

        <div className="finding-foot">
          {onShowInVideo && (
            <button type="button" className="finding-seek no-print" onClick={onShowInVideo}>
              <span aria-hidden="true">▶ </span>Show in video at {formatClock(f.frame_ms)}
            </button>
          )}
          <p className="finding-cite">
            {tracked ? (
              <>
                Cited evidence: track <code>{f.track_id}</code> ({track.phrase}, seen {formatSeconds(track.first_ms)} to{' '}
                {formatSeconds(track.last_ms)} over {track.n_frames} frames), frame {f.frame_index}.
              </>
            ) : track ? (
              <>Evidence: frame {f.frame_index} only, with the area the raw-video pass named. No tracked object.</>
            ) : (
              <>
                Cited evidence: track <code>{f.track_id}</code>, frame {f.frame_index}.
              </>
            )}
          </p>
        </div>
      </div>
      <EvidenceFrame finding={f} video={video} track={track} related={related} />
    </article>
  )
}
