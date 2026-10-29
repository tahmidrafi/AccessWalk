import { formatSeconds } from '../lib/time'
import type { Report } from '../types/report'

/** Provenance: which models produced this report (shown for open-weight checks). */
export function RunDetails({ report }: { report: Report }) {
  const { run, video } = report
  const created = new Date(run.created_at)
  return (
    <section aria-labelledby="run-heading" className="run">
      <h2 id="run-heading">How this report was made</h2>
      <dl className="run-facts">
        <div>
          <dt>Verification agent</dt>
          <dd>
            {run.agent_model} <span className="muted">via {run.agent_provider}</span>
          </dd>
        </div>
        <div>
          <dt>Object tracking</dt>
          <dd>{run.sam_model}</dd>
        </div>
        <div>
          <dt>Model calls</dt>
          <dd>
            {run.n_model_calls ?? 0}, cost ${(run.cost_usd ?? 0).toFixed(2)}
          </dd>
        </div>
        <div>
          <dt>Clip</dt>
          <dd>
            {formatSeconds(video.duration_ms)}, analysed at {video.sam_fps} fps,{' '}
            <span title={video.video_sha256}>
              video <code>{video.video_sha256.slice(0, 12)}</code>
            </span>
          </dd>
        </div>
        <div>
          <dt>Created</dt>
          <dd>
            <time dateTime={run.created_at}>
              {Number.isNaN(created.getTime()) ? run.created_at : created.toLocaleString()}
            </time>
          </dd>
        </div>
      </dl>
    </section>
  )
}
