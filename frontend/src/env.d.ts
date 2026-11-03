/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "http" for the real API; anything else (or unset) uses the mock. */
  readonly VITE_ACCESSWALK_API?: string
  /** API origin when it differs from the page's, e.g. http://127.0.0.1:8010. */
  readonly VITE_ACCESSWALK_API_BASE?: string
  /** report_id behind "Try a sample route". Unset with the real API: no sample entry. */
  readonly VITE_SAMPLE_REPORT_ID?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
