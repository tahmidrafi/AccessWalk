import { useId } from 'react'
import type { BBox } from '../types/report'

/** A box in sam.mp4 pixels. Two strokes (dark under light) so it reads on any background. */
export function Box({ b, kind }: { b: BBox; kind: 'cited' | 'related' }) {
  const props = { x: b.x1, y: b.y1, width: b.x2 - b.x1, height: b.y2 - b.y1 }
  return (
    <g className={`box box-${kind}`}>
      <rect {...props} className="box-under" />
      <rect {...props} className="box-over" />
    </g>
  )
}

/**
 * A SAM mask PNG (transparent background, sam.mp4 size) drawn as a tinted fill
 * with the same dark-under-light outline as a box. The outline is grown from the
 * mask's alpha by an SVG filter, so any mask colour works.
 */
export function Mask({ url, width, height }: { url: string; width: number; height: number }) {
  const id = `mask-${useId().replace(/[^\w-]/g, '')}`
  return (
    <g className="mask">
      <filter id={id} x="0" y="0" width={width} height={height} filterUnits="userSpaceOnUse">
        <feMorphology in="SourceAlpha" operator="dilate" radius="14" result="outer" />
        <feMorphology in="SourceAlpha" operator="dilate" radius="7" result="inner" />
        <feFlood className="mask-under" result="dark" />
        <feComposite in="dark" in2="outer" operator="in" result="darkOuter" />
        <feComposite in="darkOuter" in2="inner" operator="out" result="darkRing" />
        <feFlood className="mask-over" result="light" />
        <feComposite in="light" in2="inner" operator="in" result="lightInner" />
        <feComposite in="lightInner" in2="SourceAlpha" operator="out" result="lightRing" />
        <feFlood className="mask-fill" result="tint" />
        <feComposite in="tint" in2="SourceAlpha" operator="in" result="fill" />
        <feMerge>
          <feMergeNode in="darkRing" />
          <feMergeNode in="lightRing" />
          <feMergeNode in="fill" />
        </feMerge>
      </filter>
      <image href={url} x="0" y="0" width={width} height={height} preserveAspectRatio="none" filter={`url(#${id})`} />
    </g>
  )
}

/** Finding number pinned to the top-left corner of its box. */
export function Tag({ b, n }: { b: BBox; n: number }) {
  const r = 30
  const cx = Math.max(r, b.x1 + r)
  const cy = Math.max(r, b.y1 + r)
  return (
    <g className="tag">
      <circle cx={cx} cy={cy} r={r} />
      <text x={cx} y={cy} dy="0.35em" textAnchor="middle">
        {n}
      </text>
    </g>
  )
}
