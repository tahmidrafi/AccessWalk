import type { AnchorHTMLAttributes } from 'react'
import { navigate } from '../lib/router'

/** An ordinary link that navigates in-app; modified clicks (new tab etc.) behave as usual. */
export function Link({ to, onClick, children, ...rest }: AnchorHTMLAttributes<HTMLAnchorElement> & { to: string }) {
  return (
    <a
      {...rest}
      href={to}
      onClick={(e) => {
        onClick?.(e)
        if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
        e.preventDefault()
        navigate(to)
      }}
    >
      {children}
    </a>
  )
}
