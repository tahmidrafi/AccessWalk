import { useEffect, useState, type RefObject } from 'react'
import { snapToSamFrame } from './report'

/**
 * The video's current time, snapped to SAM frames (the overlay only changes once
 * per SAM frame, so this re-renders at most ~5 times a second while playing).
 * Read every animation frame during playback, and on seek/pause otherwise.
 */
export function useVideoClock(ref: RefObject<HTMLVideoElement | null>, frameMs: number): number {
  const [ms, setMs] = useState(0)
  useEffect(() => {
    const v = ref.current
    if (!v) return
    let raf = 0
    const read = () => setMs(snapToSamFrame(v.currentTime * 1000, frameMs))
    const loop = () => {
      read()
      raf = requestAnimationFrame(loop)
    }
    const onPlay = () => {
      cancelAnimationFrame(raf)
      loop()
    }
    const onStop = () => {
      cancelAnimationFrame(raf)
      read()
    }
    const stops = ['pause', 'ended'] as const
    const reads = ['seeked', 'timeupdate', 'loadedmetadata'] as const
    v.addEventListener('play', onPlay)
    for (const e of stops) v.addEventListener(e, onStop)
    for (const e of reads) v.addEventListener(e, read)
    return () => {
      cancelAnimationFrame(raf)
      v.removeEventListener('play', onPlay)
      for (const e of stops) v.removeEventListener(e, onStop)
      for (const e of reads) v.removeEventListener(e, read)
    }
  }, [ref, frameMs])
  return ms
}
