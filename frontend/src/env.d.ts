/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "http" for the real API; anything else (or unset) uses the mock. */
  readonly VITE_ACCESSWALK_API?: string
  /** API origin when it differs from the page's, e.g. http://127.0.0.1:8010. */
  readonly VITE_ACCESSWALK_API_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
