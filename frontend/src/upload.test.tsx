import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { createMockClient } from './api/mockClient'
import { UploadPage } from './components/UploadPage'
import { expectedProcessingText } from './lib/jobs'

describe('upload page', () => {
  const html = renderToStaticMarkup(<UploadPage api={createMockClient()} />)

  it('ties the expected processing time to the upload button', () => {
    expect(html).toContain('aria-describedby="upload-time"')
    expect(html).toContain(`id="upload-time"`)
    expect(html).toContain(expectedProcessingText())
  })

  it('holds a place for the sample route while the report list loads', () => {
    expect(html).toContain('No video to hand?')
    expect(html).toContain('Looking for a sample route')
  })
})
