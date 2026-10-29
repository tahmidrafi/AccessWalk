import { useEffect } from 'react'
import { pdfTitle } from '../lib/labels'
import type { Report } from '../types/report'

/**
 * "Download PDF" via the browser's own print-to-PDF, so the file keeps the
 * page's headings, alt text and table structure (Chrome and Edge write tagged
 * PDFs). The print stylesheet drops the video player and controls.
 */
export function PdfButton({ report }: { report: Report }) {
  useEffect(() => {
    let saved = document.title
    // Browsers name the saved PDF after the document title.
    const before = () => {
      saved = document.title
      document.title = pdfTitle(report)
    }
    const after = () => {
      document.title = saved
    }
    window.addEventListener('beforeprint', before)
    window.addEventListener('afterprint', after)
    return () => {
      window.removeEventListener('beforeprint', before)
      window.removeEventListener('afterprint', after)
    }
  }, [report])

  return (
    <div className="pdf-export no-print">
      <button type="button" aria-describedby="pdf-help" onClick={() => window.print()}>
        Download PDF
      </button>
      <p id="pdf-help" className="muted">
        Opens your browser's print dialog: choose "Save as PDF" as the printer. The PDF has the verdict, findings
        with their frames, the checks and how the report was made, without the video.
      </p>
    </div>
  )
}
