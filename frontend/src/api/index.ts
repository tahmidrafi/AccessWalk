import type { ApiClient } from './client'
import { createHttpClient } from './httpClient'
import { createMockClient } from './mockClient'

/**
 * Which API the page talks to, fixed at build time:
 *   VITE_ACCESSWALK_API=http       the real API (fetch); anything else: the mock
 *   VITE_ACCESSWALK_API_BASE=...   API origin when it is not this page's origin;
 *                                  leave empty behind the dev proxy or in production
 */
// The env check is inline so a production build drops the client (and mock data)
// it does not use.
export const api: ApiClient =
  import.meta.env.VITE_ACCESSWALK_API === 'http'
    ? createHttpClient(import.meta.env.VITE_ACCESSWALK_API_BASE ?? '')
    : createMockClient()
