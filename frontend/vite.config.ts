import fs from 'node:fs'
import path from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv, type Plugin } from 'vite'

// Evidence frames live outside the repo (data/cache is git-ignored). In dev, serve
// /media/<sha256>/frames/<i>.jpg read-only from the local cache so the mock report
// shows real (face- and plate-blurred) frames. Nothing else under data/ is exposed.
// Set ACCESSWALK_MEDIA_DIR (env or frontend/.env.local) when the cache is not next
// to this checkout, e.g. in a git worktree.
const MEDIA_PATH = /^\/([0-9a-f]{64})\/frames\/(\d+)\.jpg$/

function devMedia(mediaRoot: string): Plugin {
  return {
    name: 'accesswalk-dev-media',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/media', (req, res) => {
        const m = MEDIA_PATH.exec((req.url ?? '').split('?')[0])
        const file = m && path.join(mediaRoot, m[1], 'frames', `${m[2]}.jpg`)
        if (!file || !fs.existsSync(file)) {
          res.statusCode = 404
          res.end()
          return
        }
        res.setHeader('Content-Type', 'image/jpeg')
        fs.createReadStream(file).pipe(res)
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
