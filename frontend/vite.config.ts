import fs from 'node:fs'
import path from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv, type Plugin } from 'vite'

// Evidence media live outside the repo (data/cache is git-ignored). In dev, serve
// /media/<sha256>/<...>.jpg|png (frames, masks) and /media/<sha256>/proxy.mp4
// read-only from the local cache so the mock report shows real (face-blurred)
// media. Path segments are [A-Za-z0-9_-] only, so nothing can climb out of a clip
// dir, and no other file type under data/ is exposed.
// Set ACCESSWALK_MEDIA_DIR (env or frontend/.env.local) when the cache is not next
// to this checkout, e.g. in a git worktree.
const MEDIA_PATH = /^\/([0-9a-f]{64})\/((?:[\w-]+\/)*[\w-]+\.(?:jpg|png)|proxy\.mp4)$/
const TYPES: Record<string, string> = { '.jpg': 'image/jpeg', '.png': 'image/png', '.mp4': 'video/mp4' }

function devMedia(mediaRoot: string): Plugin {
  return {
    name: 'accesswalk-dev-media',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/media', (req, res) => {
        const m = MEDIA_PATH.exec((req.url ?? '').split('?')[0])
        const file = m && path.join(mediaRoot, m[1], m[2])
        if (!file || !fs.existsSync(file)) {
          res.statusCode = 404
          res.end()
          return
        }
        const size = fs.statSync(file).size
        res.setHeader('Content-Type', TYPES[path.extname(file)])
        res.setHeader('Accept-Ranges', 'bytes')
        // Video seeking needs byte ranges (206); browsers send "bytes=<start>-[<end>]".
        const range = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range ?? '')
        if (!range) {
          res.setHeader('Content-Length', size)
          fs.createReadStream(file).pipe(res)
          return
        }
        const start = range[1] ? Number(range[1]) : Math.max(0, size - Number(range[2]))
        const end = range[1] && range[2] ? Math.min(Number(range[2]), size - 1) : size - 1
        if (start > end || start >= size) {
          res.statusCode = 416
          res.setHeader('Content-Range', `bytes */${size}`)
          res.end()
          return
        }
        res.statusCode = 206
        res.setHeader('Content-Range', `bytes ${start}-${end}/${size}`)
        res.setHeader('Content-Length', end - start + 1)
        fs.createReadStream(file, { start, end }).pipe(res)
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, import.meta.dirname, 'ACCESSWALK_')
  const mediaRoot = env.ACCESSWALK_MEDIA_DIR || path.resolve(import.meta.dirname, '../data/cache')
  return { plugins: [react(), devMedia(mediaRoot)] }
})
