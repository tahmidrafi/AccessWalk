import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { createMockClient } from './api/mockClient'
import { ReportPreview, StatTiles } from './components/LandingSections'
import { PasscodeField, UploadPage } from './components/UploadPage'
import { ERROR_HELP, expectedProcessingText, suggestsSample, uploadErrorHelp } from './lib/jobs'
import { reviewAgentLabel } from './lib/labels'

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

  it('has no sample entry when no report is pinned and the API is real', () => {
    const { mock: _mock, ...realApi } = createMockClient()
    expect(renderToStaticMarkup(<UploadPage api={realApi} />)).not.toContain('No video to hand?')
    expect(renderToStaticMarkup(<UploadPage api={realApi} sampleReportId="demo-route" />)).toContain('No video to hand?')
  })

  it('asks for no passcode until health says uploads need one', () => {
    expect(html).not.toContain('id="passcode"')
  })
})

describe('landing', () => {
  const html = renderToStaticMarkup(<UploadPage api={createMockClient()} />)

  it('leads with the headline, its underlined word and both actions', () => {
    expect(html).toContain('Accessibility, before you arrive')
    expect(html).toContain('Know the route <span class="hero-mark">before</span> you go.')
    expect(html).toContain('href="#upload"')
    expect(html).toContain('id="upload"')
  })

  it('shows the eval numbers with their caveat', () => {
    const stats = renderToStaticMarkup(<StatTiles />)
    for (const t of ['79%', 'of labelled barriers found', '97%', 'precision on 22 filmed routes', '8', 'accessibility checks'])
      expect(stats).toContain(t)
    expect(stats).toContain('indicative')
  })

  it('previews one confirmed and one possible finding', () => {
    const preview = renderToStaticMarkup(<ReportPreview sampleHref="/reports/x" />)
    expect(preview).toContain('<strong>Confirmed:</strong> object and frame cited')
    expect(preview).toContain('<strong>Possible:</strong> verify on site')
    expect(preview).toContain('href="/reports/x"')
    expect(renderToStaticMarkup(<ReportPreview />)).not.toContain('Open the full sample report')
  })

  it('keeps the sections in order: hero, stats, how it works, preview, upload', () => {
    const at = ['page-title', 'stats-heading', 'how-heading', 'preview-heading', 'upload-heading'].map((id) =>
      html.indexOf(`id="${id}"`),
    )
    expect(at.every((i) => i > -1)).toBe(true)
    expect([...at].sort((a, b) => a - b)).toEqual(at)
  })
})

describe('review agent label', () => {
  it('says open-weight only for the hosts that serve the open-weight model', () => {
    expect(reviewAgentLabel('baseten')).toBe('open-weight review agent')
    expect(reviewAgentLabel('fireworks')).toBe('open-weight review agent')
    expect(reviewAgentLabel('meta')).toBe('review agent')
  })
})

describe('upload passcode field', () => {
  const field = (props: Partial<Parameters<typeof PasscodeField>[0]> = {}) =>
    renderToStaticMarkup(<PasscodeField value="" error={null} onChange={() => {}} {...props} />)

  it('is a labelled password input with the judges hint, kept out of autofill', () => {
    const html = field()
    expect(html).toContain('<label for="passcode">Upload passcode</label>')
    expect(html).toMatch(/<input[^>]*id="passcode"[^>]*type="password"/)
    expect(html).toContain('aria-describedby="passcode-hint"')
    expect(html).toContain('id="passcode-hint"')
    expect(html).toContain('Judges: see the submission notes')
    expect(html).toContain('autoComplete="off"')
    expect(html).not.toContain('aria-invalid')
  })

  it('ties a client-side error to the input', () => {
    const html = field({ error: 'Enter the upload passcode.' })
    expect(html).toContain('aria-describedby="passcode-hint passcode-error"')
    expect(html).toContain('aria-invalid="true"')
    expect(html).toContain('Enter the upload passcode.')
  })

  it('marks the input invalid after a 403, without an inline error', () => {
    const html = field({ refused: true, value: 'wrong' })
    expect(html).toContain('aria-invalid="true"')
    expect(html).toContain('aria-describedby="passcode-hint"')
  })
})

describe('upload refusals', () => {
  it('explains a 403 forbidden and points at the submission notes and the sample route', () => {
    const help = uploadErrorHelp('forbidden')
    expect(help.title).toBe('The upload passcode was not accepted')
    expect(help.advice).toContain('submission notes')
    expect(help.advice).toContain('sample route')
    expect(suggestsSample('forbidden')).toBe(true)
  })

  it('reads over_budget at upload as the server budget, not the video cost', () => {
    const help = uploadErrorHelp('over_budget')
    expect(help.title).toBe('Uploads are paused on this server')
    expect(help.advice).toContain('used its model budget')
    expect(help.advice).toContain('sample route')
    expect(help).not.toEqual(ERROR_HELP.over_budget)
    expect(suggestsSample('over_budget')).toBe(true)
    expect(uploadErrorHelp('too_large')).toEqual(ERROR_HELP.too_large)
    expect(suggestsSample('too_large')).toBe(false)
  })
})
