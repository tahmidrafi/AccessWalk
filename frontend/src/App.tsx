import { useRef } from 'react'
import { api } from './api'
import { JobPage } from './components/JobPage'
import { Link } from './components/Link'
import { ReportRoute } from './components/ReportRoute'
import { UploadPage } from './components/UploadPage'
import { matchRoute, usePageEntry, usePathname } from './lib/router'

/** Brand mark: a route with a tracked box on it (decorative; the wordmark names the link). */
function Logo() {
  return (
    <svg className="logo" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="9" className="logo-bg" />
      <path d="M9 25 C 12 18, 20 18, 17 7" className="logo-route" />
      <rect x="13" y="4" width="9" height="8" rx="1.5" className="logo-box" />
    </svg>
  )
}

function NotFoundPage() {
  const headingRef = useRef<HTMLHeadingElement>(null)
  usePageEntry('Page not found - AccessWalk', headingRef)
  return (
    <div className="page-head">
      <h1 ref={headingRef} tabIndex={-1}>
        Page not found
      </h1>
      <p>
        <Link to="/">Go to the upload page</Link> to check a route.
      </p>
    </div>
  )
}

export default function App() {
  const route = matchRoute(usePathname())
  return (
    <>
      <a className="skip-link no-print" href="#main">
        Skip to main content
      </a>
      <header className="site-header">
        <div className="site-header-inner">
          <p className="brand">
            <Link to="/">
              <Logo />
              AccessWalk
            </Link>
          </p>
          <nav aria-label="Main" className="site-nav no-print">
            <ul>
              <li>
                <a href="/#how">How it works</a>
              </li>
              <li>
                <a href="/#upload">Check a route</a>
              </li>
            </ul>
          </nav>
          <p className="tagline print-only">Know before you go: accessibility report from a phone walkthrough</p>
        </div>
      </header>
      <main id="main" tabIndex={-1}>
        {route.name === 'upload' && <UploadPage api={api} />}
        {route.name === 'job' && <JobPage key={route.jobId} api={api} jobId={route.jobId} />}
        {route.name === 'report' && <ReportRoute api={api} reportId={route.reportId} />}
        {route.name === 'not_found' && <NotFoundPage />}
      </main>
    </>
  )
}
