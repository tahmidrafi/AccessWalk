import { useRef } from 'react'
import { api } from './api'
import { JobPage } from './components/JobPage'
import { Link } from './components/Link'
import { ReportRoute } from './components/ReportRoute'
import { UploadPage } from './components/UploadPage'
import { matchRoute, usePageEntry, usePathname } from './lib/router'

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
        <p className="brand">
          <Link to="/">AccessWalk</Link>
        </p>
        <p className="tagline">Know before you go: accessibility report from a phone walkthrough</p>
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
