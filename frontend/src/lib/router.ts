import { useEffect, useSyncExternalStore, type RefObject } from 'react'

/**
 * A tiny History API router. Paths, not hash routes, so a report keeps its
 * #finding-f1 deep links. The dev server (and any static host with an SPA
 * fallback) serves index.html for these paths.
 */
export type Route =
  | { name: 'upload' }
  | { name: 'job'; jobId: string }
  | { name: 'report'; reportId: string }
  | { name: 'not_found' }

export function matchRoute(pathname: string): Route {
  const path = pathname.replace(/\/+$/, '') || '/'
  if (path === '/') return { name: 'upload' }
  let m = /^\/jobs\/([\w-]+)$/.exec(path)
  if (m) return { name: 'job', jobId: m[1] }
  m = /^\/reports\/([\w.-]+)$/.exec(path)
  if (m) return { name: 'report', reportId: m[1] }
  return { name: 'not_found' }
}

const EVENT = 'accesswalk:navigate'
// How many in-app navigations happened: pages move focus to their heading only
// after one (on first load the browser and screen reader start at the top anyway).
let navigations = 0

export function navigate(path: string, replace = false) {
  if (replace) history.replaceState(null, '', path)
  else history.pushState(null, '', path)
  navigations++
  window.dispatchEvent(new Event(EVENT))
  window.scrollTo(0, 0)
}

function subscribe(onChange: () => void) {
  const onPop = () => {
    navigations++
    onChange()
  }
  window.addEventListener('popstate', onPop)
  window.addEventListener(EVENT, onChange)
  return () => {
    window.removeEventListener('popstate', onPop)
    window.removeEventListener(EVENT, onChange)
  }
}

export function usePathname(): string {
  return useSyncExternalStore(subscribe, () => window.location.pathname)
}

/**
 * Page title, and focus on the page heading after an in-app navigation, so a
 * screen reader announces the new page.
 */
export function usePageEntry(title: string, heading: RefObject<HTMLElement | null>) {
  useEffect(() => {
    document.title = title
  }, [title])
  useEffect(() => {
    if (navigations > 0) heading.current?.focus()
  }, [heading])
}
