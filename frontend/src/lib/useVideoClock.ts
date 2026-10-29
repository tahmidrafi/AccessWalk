import { useEffect, useState, type RefObject } from 'react'

const exact = (ms: number) => ms

/**
 * The video's current time in ms, passed through ``snap`` (a stable function).
 * While playing it is read once per presented video frame (requestVideoFrameCallback,
 * or every animation frame where that is missing); otherwise on seek and pause.
 * React skips the re-render when the snapped value is unchanged, so snapping to
 * SAM frames keeps a caller to ~5 renders a second, while ``exact`` follows the
 * video's own frame rate.
 */
export function useVideoClock(ref: RefObject<HTMLVideoElement | null>, snap: (ms: number) => number = exact): number {
  const [ms, setMs] = useState(0)
  useEffect(() => {
    const v = ref.current
    if (!v) return
    const perFrame = 'requestVideoFrameCallback' in v
    let handle = 0
    const cancel = () => (perFrame ? v.cancelVideoFrameCallback(handle) : cancelAnimationFrame(handle))
    const read = () => setMs(snap(v.currentTime * 1000))
    const loop = () => {
      handle = perFrame
        ? v.requestVideoFrameCallback((_now, frame) => {
            setMs(snap(frame.mediaTime * 1000))
            loop()
          })
        : requestAnimationFrame(() => {
            read()
            loop()
          })
    }
    const onPlay = () => {
      cancel()
      loop()
    }
    const onStop = () => {
      cancel()
      read()
    }
    // During playback the frame loop is the clock; currentTime from timeupdate can
    // run ahead of the presented frame, so it only counts while paused.
    const onTimeUpdate = () => {
      if (v.paused) read()
    }
    const stops = ['pause', 'ended'] as const
    const reads = ['seeked', 'loadedmetadata'] as const
    v.addEventListener('play', onPlay)
    v.addEventListener('timeupdate', onTimeUpdate)
    for (const e of stops) v.addEventListener(e, onStop)
    for (const e of reads) v.addEventListener(e, read)
    if (!v.paused) loop()
    return () => {
      cancel()
      v.removeEventListener('play', onPlay)
      v.removeEventListener('timeupdate', onTimeUpdate)
      for (const e of stops) v.removeEventListener(e, onStop)
      for (const e of reads) v.removeEventListener(e, read)
    }
  }, [ref, snap])
  return ms
}
