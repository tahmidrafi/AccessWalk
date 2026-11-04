import { useEffect, useRef, useState } from 'react'
import { useReducedMotion } from '../lib/useReducedMotion'

/** Short looping clip of a report being made; served next to the evidence media. */
export const HERO_VIDEO = '/media/showcase/hero.mp4'

const CAPTIONS = `data:text/vtt;charset=utf-8,${encodeURIComponent(
  'WEBVTT\n\n00:00:00.000 --> 00:10:00.000\n[No sound] A walkthrough with each tracked object outlined.\n',
)}`

/**
 * The still shown until the clip plays, and instead of it when the clip is
 * missing: a walk toward an entrance with steps (a cited, solid box) and a curb
 * (a possible finding, dashed box), the way the report draws them.
 */
function HeroStill() {
  return (
    <svg className="hero-still" viewBox="0 0 360 640" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id="hero-sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#9fb7c9" />
          <stop offset="1" stopColor="#dfe6ea" />
        </linearGradient>
        <linearGradient id="hero-walk" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#b9b6ae" />
          <stop offset="1" stopColor="#8f8c85" />
        </linearGradient>
      </defs>
      <rect width="360" height="640" fill="url(#hero-sky)" />
      {/* house */}
      <rect x="70" y="150" width="220" height="180" fill="#8d4b3a" />
      <polygon points="50,155 180,80 310,155" fill="#4b3a34" />
      <rect x="98" y="190" width="44" height="44" fill="#c9d6de" stroke="#5b3428" strokeWidth="4" />
      <rect x="218" y="190" width="44" height="44" fill="#c9d6de" stroke="#5b3428" strokeWidth="4" />
      <rect x="160" y="236" width="40" height="78" fill="#2f3b45" />
      <circle cx="192" cy="278" r="3" fill="#d8c27a" />
      {/* lawn */}
      <polygon points="0,330 360,330 360,640 0,640" fill="#5f7d3e" />
      {/* steps */}
      <rect x="146" y="314" width="68" height="10" fill="#cfcac0" />
      <rect x="138" y="324" width="84" height="10" fill="#bdb8ae" />
      <rect x="130" y="334" width="100" height="10" fill="#aaa59b" />
      {/* walkway in perspective */}
      <polygon points="138,344 222,344 330,640 30,640" fill="url(#hero-walk)" />
      <g stroke="#7b786f" strokeWidth="2">
        <line x1="126" y1="390" x2="234" y2="390" />
        <line x1="110" y1="450" x2="252" y2="450" />
        <line x1="88" y1="530" x2="276" y2="530" />
      </g>
      {/* curb and street edge */}
      <rect x="0" y="600" width="360" height="40" fill="#3d3f42" />
      <rect x="0" y="592" width="360" height="12" fill="#c4c1b9" />
      {/* cited: steps, solid box */}
      <g fill="none">
        <rect x="122" y="306" width="116" height="46" stroke="#000" strokeWidth="7" />
        <rect x="122" y="306" width="116" height="46" stroke="#ffd400" strokeWidth="3.5" />
      </g>
      <g>
        <circle cx="122" cy="306" r="15" fill="#000" stroke="#ffd400" strokeWidth="3" />
        <text x="122" y="306" dy="0.35em" textAnchor="middle" fill="#ffd400" fontSize="17" fontWeight="700" fontFamily="system-ui, sans-serif">
          1
        </text>
      </g>
      {/* possible: curb, dashed box */}
      <g fill="none">
        <rect x="16" y="580" width="328" height="36" stroke="#000" strokeWidth="7" />
        <rect x="16" y="580" width="328" height="36" stroke="#ffd400" strokeWidth="3.5" strokeDasharray="12 8" />
      </g>
      <g>
        <circle cx="34" cy="580" r="15" fill="#000" stroke="#ffd400" strokeWidth="3" />
        <text x="34" y="580" dy="0.35em" textAnchor="middle" fill="#ffd400" fontSize="17" fontWeight="700" fontFamily="system-ui, sans-serif">
          2
        </text>
      </g>
    </svg>
  )
}

/**
 * Hero media: the showcase clip, muted and looping, when it exists and motion is
 * welcome; with reduced motion it waits for the Play button. Falls back to the
 * illustrated still when the clip is missing or cannot play. Never has sound.
 */
export function HeroMedia({ src = HERO_VIDEO }: { src?: string }) {
  const reduce = useReducedMotion()
  const ref = useRef<HTMLVideoElement>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'failed'>('loading')
  const [playing, setPlaying] = useState(false)
  // With reduced motion the still stays on top until the viewer presses Play.
  const [started, setStarted] = useState(false)

  useEffect(() => {
    const v = ref.current
    if (!v || state !== 'ready') return
    v.muted = true // property, not just the attribute: required for autoplay, and no sound ever
    if (reduce) v.pause()
    else v.play().catch(() => setPlaying(false))
  }, [reduce, state])

  const toggle = () => {
    const v = ref.current
    if (!v) return
    v.muted = true
    if (v.paused) v.play().catch(() => setPlaying(false))
    else v.pause()
  }

  const showStill = state !== 'ready' || (reduce && !started)

  return (
    <figure className="hero-media">
      <div className="hero-screen">
        {state !== 'failed' && (
          <video
            ref={ref}
            className={state === 'ready' ? undefined : 'hero-video-pending'}
            src={src}
            muted
            loop
            playsInline
            preload={reduce ? 'metadata' : 'auto'}
            aria-label="Preview: a walkthrough video with each tracked object outlined. No sound."
            onLoadedMetadata={() => setState('ready')}
            onError={() => setState('failed')}
            onPlay={() => {
              setPlaying(true)
              setStarted(true)
            }}
            onPause={() => setPlaying(false)}
          >
            <track kind="captions" srcLang="en" label="Description" src={CAPTIONS} />
          </video>
        )}
        {showStill && <HeroStill />}
      </div>
      <figcaption>
        {state === 'ready' && (
          <button type="button" className="hero-toggle" onClick={toggle}>
            <span aria-hidden="true">{playing ? '❚❚ ' : '▶ '}</span>
            {playing ? 'Pause preview' : 'Play preview'}
          </button>
        )}
        <span>
          {showStill
            ? 'Solid box: an object SAM 3.1 tracked and the agent cited. Dashed box: a possible barrier to check on site.'
            : 'SAM 3.1 tracking objects along a walk, faces blurred. No sound.'}
        </span>
      </figcaption>
    </figure>
  )
}
