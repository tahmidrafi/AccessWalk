/** 12345 -> "0:12". Video time is stored in ms throughout the report. */
export function formatClock(ms: number): string {
  const total = Math.floor(ms / 1000)
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

/** 10800 -> "10.8 s". */
export function formatSeconds(ms: number): string {
  return `${(ms / 1000).toFixed(1)} s`
}

/** For screen readers: 72000 -> "1 minute 12 seconds". */
export function spokenTime(ms: number): string {
  const total = Math.round(ms / 1000)
  const m = Math.floor(total / 60)
  const s = total % 60
  const parts: string[] = []
  if (m) parts.push(`${m} ${m === 1 ? 'minute' : 'minutes'}`)
  if (s || !m) parts.push(`${s} ${s === 1 ? 'second' : 'seconds'}`)
  return parts.join(' ')
}
